"""CSV 上传导入服务：解析、校验、判重、商品冲突处理与事务追加。

规则依据 spec.md §4.1.1 与 api.md §4.2：
- 跳过重复销售（唯一键 product_id + quantity + sale_date）
- 拒绝商品信息冲突（不覆盖，保留库中现有信息）
- 整体以事务追加写入，不 DROP/TRUNCATE/ALTER，不删除现有数据
"""

import csv
import io
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException

from app.database import get_connection

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["product_id", "product_name", "category", "price", "quantity", "sale_date"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def import_csv(filename: str, content: bytes) -> dict:
    """解析 CSV 并事务追加到数据库，返回导入摘要。"""
    if not (filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="仅支持 .csv 文件")

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=422, detail="文件超过 10MB 限制")

    rows = _parse(content)

    # 商品维度：每个 product_id 取文件内首次出现的定义
    csv_products: dict = {}
    for row in rows:
        csv_products.setdefault(
            row["product_id"], (row["product_name"], row["category"], row["price"])
        )
    product_ids = list(csv_products.keys())

    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                existing_products = _load_products(cur, product_ids)
                existing_sales = _load_sale_keys(cur, product_ids)

                inserted_products, conflicts = _write_products(cur, csv_products, existing_products)
                # 冲突商品的销售记录一并跳过
                conflict_ids = {item["product_id"] for item in conflicts}
                inserted_sales, skipped = _write_sales(cur, rows, existing_sales, conflict_ids)

            conn.commit()
        except Exception:
            conn.rollback()
            raise

    summary = {
        "total_rows": len(rows),
        "inserted_products": inserted_products,
        "inserted_sales": inserted_sales,
        "skipped_duplicates": skipped,
        "rejected_conflicts": len(conflicts),
        "conflict_details": conflicts,
    }
    logger.info("CSV 导入完成: %s", summary)
    return summary


def _parse(content: bytes) -> list:
    """解码并逐行校验 CSV，返回合法行列表；任一行不合法即抛出 422。"""
    try:
        text = content.decode("utf-8-sig")  # 兼容并去除 UTF-8 BOM
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="文件编码必须为 UTF-8")

    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames or []
    missing = [col for col in REQUIRED_COLUMNS if col not in header]
    if missing:
        raise HTTPException(status_code=422, detail=f"缺少必需列: {', '.join(missing)}")

    rows = []
    for line_no, raw in enumerate(reader, start=2):  # 第 1 行为表头
        rows.append(_parse_row(raw, line_no))
    return rows


def _parse_row(raw: dict, line_no: int) -> dict:
    """校验单行并转为规范化的字典。"""

    def cell(name: str) -> str:
        return (raw.get(name) or "").strip()

    product_id, product_name, category = cell("product_id"), cell("product_name"), cell("category")
    if not product_id or not product_name or not category:
        raise HTTPException(
            status_code=422,
            detail=f"第 {line_no} 行: product_id / product_name / category 不能为空",
        )

    try:
        price = Decimal(cell("price"))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=422, detail=f"第 {line_no} 行: price 不是合法数值")
    if price <= 0:
        raise HTTPException(status_code=422, detail=f"第 {line_no} 行: price 必须大于 0")

    quantity_raw = cell("quantity")
    if not quantity_raw.isdigit() or int(quantity_raw) < 1:
        raise HTTPException(status_code=422, detail=f"第 {line_no} 行: quantity 必须为正整数")

    try:
        sale_date = datetime.strptime(cell("sale_date"), "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"第 {line_no} 行: sale_date 必须为 YYYY-MM-DD 格式"
        )

    return {
        "product_id": product_id,
        "product_name": product_name,
        "category": category,
        "price": price,
        "quantity": int(quantity_raw),
        "sale_date": sale_date,
    }


def _load_products(cur, product_ids: list) -> dict:
    """查询文件中涉及商品的现有信息：product_id -> (name, category, price)。"""
    if not product_ids:
        return {}
    placeholders = ",".join(["%s"] * len(product_ids))
    cur.execute(
        f"SELECT product_id, product_name, category, price FROM products "
        f"WHERE product_id IN ({placeholders})",
        product_ids,
    )
    return {row[0]: (row[1], row[2], row[3]) for row in cur.fetchall()}


def _load_sale_keys(cur, product_ids: list) -> set:
    """查询文件中涉及商品在库中已有的销售唯一键集合。"""
    if not product_ids:
        return set()
    placeholders = ",".join(["%s"] * len(product_ids))
    cur.execute(
        f"SELECT product_id, quantity, sale_date FROM sales "
        f"WHERE product_id IN ({placeholders})",
        product_ids,
    )
    return {(row[0], row[1], row[2]) for row in cur.fetchall()}


def _write_products(cur, csv_products: dict, existing_products: dict):
    """写入新增商品；与现有信息冲突的拒绝写入。返回 (新增数, 冲突列表)。"""
    inserted = 0
    conflicts = []
    for product_id, (name, category, price) in csv_products.items():
        if product_id not in existing_products:
            cur.execute(
                "INSERT INTO products (product_id, product_name, category, price) "
                "VALUES (%s, %s, %s, %s)",
                (product_id, name, category, price),
            )
            inserted += 1
            continue

        e_name, e_category, e_price = existing_products[product_id]
        # price 为 Decimal，按数值比较（12999 与 12999.00 视为相等）
        if e_name != name or e_category != category or e_price != price:
            conflicts.append({"product_id": product_id, "reason": "商品信息与现有记录不一致"})
    return inserted, conflicts


def _write_sales(cur, rows: list, existing_sales: set, conflict_ids: set):
    """批量写入非重复销售记录；所属商品冲突的行一并跳过。返回 (新增数, 跳过数)。"""
    inserted = 0
    skipped = 0
    seen = set()
    batch = []
    for row in rows:
        if row["product_id"] in conflict_ids:
            skipped += 1
            continue
        key = (row["product_id"], row["quantity"], row["sale_date"])
        if key in existing_sales or key in seen:
            skipped += 1
            continue
        seen.add(key)
        batch.append(key)

    if batch:
        cur.executemany(
            "INSERT INTO sales (product_id, quantity, sale_date) VALUES (%s, %s, %s)",
            batch,
        )
        inserted = len(batch)
    return inserted, skipped

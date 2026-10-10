"""查询服务：分类选项、商品列表、商品详情、销售明细。

统计口径见 spec.md §5：
- 销量 = SUM(quantity)；销售额 = SUM(price × quantity)；交易次数 = 记录数
- 日均销量 = 销量 ÷ 区间日历天数（含首尾日）
"""

import logging
from decimal import Decimal

from fastapi import HTTPException

from app.database import get_connection

logger = logging.getLogger(__name__)

_CENT = Decimal("0.01")


def _money(value) -> str:
    """金额统一为两位小数字符串，如 5999 -> '5999.00'。"""
    return str(Decimal(value or 0).quantize(_CENT))


def _validate_range(start_date, end_date) -> None:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date 不能晚于 end_date")


def list_categories() -> dict:
    """分类选项：去重分类名及其商品数，按分类名升序。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT category, COUNT(*) FROM products GROUP BY category ORDER BY category ASC"
            )
            rows = cur.fetchall()
    return {"categories": [{"category": c, "product_count": n} for c, n in rows]}


def list_products(page: int, page_size: int, category, name) -> dict:
    """商品分页列表，支持分类精确匹配、名称模糊筛选。"""
    conditions, params = [], []
    if category:
        conditions.append("category = %s")
        params.append(category)
    if name:
        conditions.append("product_name LIKE %s")
        params.append(f"%{name}%")
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM products{where}", params)
            total = cur.fetchone()[0]
            cur.execute(
                f"SELECT product_id, product_name, category, price FROM products{where} "
                f"ORDER BY product_id ASC LIMIT %s OFFSET %s",
                params + [page_size, (page - 1) * page_size],
            )
            rows = cur.fetchall()

    items = [
        {
            "product_id": row[0],
            "product_name": row[1],
            "category": row[2],
            "price": _money(row[3]),
        }
        for row in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_product_detail(product_id: str, start_date, end_date) -> dict:
    """商品详情：基础信息 + 区间统计指标。"""
    _validate_range(start_date, end_date)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT product_name, category, price FROM products WHERE product_id = %s",
                (product_id,),
            )
            product = cur.fetchone()
            if product is None:
                raise HTTPException(status_code=404, detail="商品不存在")

            # 缺省日期 → 回落到该商品自身销售跨度
            if start_date is None or end_date is None:
                cur.execute(
                    "SELECT MIN(sale_date), MAX(sale_date) FROM sales WHERE product_id = %s",
                    (product_id,),
                )
                span_min, span_max = cur.fetchone()
                if start_date is None:
                    start_date = span_min
                if end_date is None:
                    end_date = span_max

            volume, amount, transactions = 0, 0, 0
            if start_date is not None and end_date is not None:
                cur.execute(
                    "SELECT COALESCE(SUM(s.quantity), 0), "
                    "COALESCE(SUM(s.quantity * p.price), 0), COUNT(*) "
                    "FROM sales s JOIN products p ON s.product_id = p.product_id "
                    "WHERE s.product_id = %s AND s.sale_date BETWEEN %s AND %s",
                    (product_id, start_date, end_date),
                )
                volume, amount, transactions = cur.fetchone()

    days = (end_date - start_date).days + 1 if start_date and end_date else 0
    avg_daily = round(volume / days, 2) if days > 0 else 0

    return {
        "product_id": product_id,
        "product_name": product[0],
        "category": product[1],
        "price": _money(product[2]),
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "sales_volume": int(volume),
        "sales_amount": _money(amount),
        "transaction_count": int(transactions),
        "avg_daily_volume": float(avg_daily),
    }


def list_sales(page: int, page_size: int, product_id, start_date, end_date) -> dict:
    """销售明细分页，支持商品 ID 与日期闭区间筛选。"""
    _validate_range(start_date, end_date)

    conditions, params = [], []
    if product_id:
        conditions.append("s.product_id = %s")
        params.append(product_id)
    if start_date:
        conditions.append("s.sale_date >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("s.sale_date <= %s")
        params.append(end_date)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM sales s{where}", params)
            total = cur.fetchone()[0]
            cur.execute(
                "SELECT s.sale_id, s.product_id, p.product_name, s.quantity, s.sale_date, "
                "s.quantity * p.price "
                f"FROM sales s JOIN products p ON s.product_id = p.product_id{where} "
                "ORDER BY s.sale_id ASC LIMIT %s OFFSET %s",
                params + [page_size, (page - 1) * page_size],
            )
            rows = cur.fetchall()

    items = [
        {
            "sale_id": row[0],
            "product_id": row[1],
            "product_name": row[2],
            "quantity": row[3],
            "sale_date": row[4].isoformat(),
            "amount": _money(row[5]),
        }
        for row in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}

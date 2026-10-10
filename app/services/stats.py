"""统计服务：销售概况、分类统计、热销排行、日/月销售趋势。

统计口径见 spec.md §5：
- 销量 = SUM(quantity)；销售额 = SUM(price × quantity)；交易次数 = COUNT(*)
- product_count = 发生销售的去重商品数
- 趋势按闭区间生成完整时间轴、缺失补零，分组时各曲线共用同一时间轴
"""

import logging
from datetime import timedelta
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


def _date_where(start_date, end_date):
    """构造日期闭区间条件与参数（不传则不限制）。"""
    conditions, params = [], []
    if start_date:
        conditions.append("s.sale_date >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("s.sale_date <= %s")
        params.append(end_date)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    return where, params


def _full_span(cur):
    """全量销售日期跨度 (min, max)，无数据时为 (None, None)。"""
    cur.execute("SELECT MIN(sale_date), MAX(sale_date) FROM sales")
    return cur.fetchone()


def get_overview(start_date, end_date) -> dict:
    """销售概况：范围内总销量、总销售额、交易次数、发生销售的去重商品数。"""
    _validate_range(start_date, end_date)
    where, params = _date_where(start_date, end_date)

    with get_connection() as conn:
        with conn.cursor() as cur:
            # 缺省日期回显为全量跨度
            if start_date is None or end_date is None:
                span_min, span_max = _full_span(cur)
                if start_date is None:
                    start_date = span_min
                if end_date is None:
                    end_date = span_max

            cur.execute(
                "SELECT COALESCE(SUM(s.quantity), 0), "
                "COALESCE(SUM(s.quantity * p.price), 0), "
                "COUNT(*), COUNT(DISTINCT s.product_id) "
                "FROM sales s JOIN products p ON s.product_id = p.product_id" + where,
                params,
            )
            volume, amount, transactions, products = cur.fetchone()

    return {
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "sales_volume": int(volume),
        "sales_amount": _money(amount),
        "transaction_count": int(transactions),
        "product_count": int(products),
    }


def get_category_stats(start_date, end_date) -> dict:
    """分类统计：按商品分类分组的销量、销售额、交易次数、去重商品数。"""
    _validate_range(start_date, end_date)
    where, params = _date_where(start_date, end_date)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT p.category, COALESCE(SUM(s.quantity), 0), "
                "COALESCE(SUM(s.quantity * p.price), 0), "
                "COUNT(*), COUNT(DISTINCT s.product_id) "
                "FROM sales s JOIN products p ON s.product_id = p.product_id" + where +
                " GROUP BY p.category ORDER BY p.category ASC",
                params,
            )
            rows = cur.fetchall()

    items = [
        {
            "category": row[0],
            "sales_volume": int(row[1]),
            "sales_amount": _money(row[2]),
            "transaction_count": int(row[3]),
            "product_count": int(row[4]),
        }
        for row in rows
    ]
    return {"items": items}


def get_top_products(start_date, end_date, category, sort_by, limit) -> dict:
    """热销排行：按销量或销售额降序排名（sort_by: volume / amount）。"""
    _validate_range(start_date, end_date)

    conditions, params = [], []
    if start_date:
        conditions.append("s.sale_date >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("s.sale_date <= %s")
        params.append(end_date)
    if category:
        conditions.append("p.category = %s")
        params.append(category)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    # 排序字段取自白名单，避免拼接用户输入
    order_column = "amt" if sort_by == "amount" else "vol"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT p.product_id, p.product_name, p.category, "
                "COALESCE(SUM(s.quantity), 0) AS vol, "
                "COALESCE(SUM(s.quantity * p.price), 0) AS amt, "
                "COUNT(*) AS tx "
                "FROM sales s JOIN products p ON s.product_id = p.product_id" + where +
                " GROUP BY p.product_id, p.product_name, p.category"
                f" ORDER BY {order_column} DESC, p.product_id ASC LIMIT %s",
                params + [limit],
            )
            rows = cur.fetchall()

    items = [
        {
            "rank": index + 1,
            "product_id": row[0],
            "product_name": row[1],
            "category": row[2],
            "sales_volume": int(row[3]),
            "sales_amount": _money(row[4]),
            "transaction_count": int(row[5]),
        }
        for index, row in enumerate(rows)
    ]
    return {"items": items}


def _build_axis(start_date, end_date, granularity):
    """按闭区间生成完整时间轴（period 字符串列表）。"""
    periods = []
    if granularity == "month":
        year, month = start_date.year, start_date.month
        while (year, month) <= (end_date.year, end_date.month):
            periods.append(f"{year:04d}-{month:02d}")
            month += 1
            if month > 12:
                month, year = 1, year + 1
    else:
        current = start_date
        while current <= end_date:
            periods.append(current.isoformat())
            current += timedelta(days=1)
    return periods


def get_trend(start_date, end_date, granularity, group_by) -> dict:
    """日/月销售趋势：完整时间轴补零，可选按分类分组（各曲线周期一致）。"""
    _validate_range(start_date, end_date)

    with get_connection() as conn:
        with conn.cursor() as cur:
            # 缺省日期回落到全量数据跨度
            if start_date is None or end_date is None:
                span_min, span_max = _full_span(cur)
                if start_date is None:
                    start_date = span_min
                if end_date is None:
                    end_date = span_max

            # 全表无销售数据：返回空序列
            if start_date is None or end_date is None:
                empty = [] if group_by == "category" else [{"key": "all", "points": []}]
                return {
                    "granularity": granularity,
                    "start_date": None,
                    "end_date": None,
                    "series": empty,
                }

            periods = _build_axis(start_date, end_date, granularity)
            # 日粒度直接取日期列；月粒度截取到 YYYY-MM
            if granularity == "month":
                period_expr = "SUBSTRING(s.sale_date, 1, 7)"
                normalize = lambda value: value
            else:
                period_expr = "s.sale_date"
                normalize = lambda value: value.isoformat()

            where, params = _date_where(start_date, end_date)
            if group_by == "category":
                cur.execute(
                    f"SELECT p.category, {period_expr}, COALESCE(SUM(s.quantity), 0), "
                    "COALESCE(SUM(s.quantity * p.price), 0) "
                    "FROM sales s JOIN products p ON s.product_id = p.product_id" + where +
                    f" GROUP BY p.category, {period_expr}",
                    params,
                )
                rows = cur.fetchall()
            else:
                cur.execute(
                    f"SELECT {period_expr}, COALESCE(SUM(s.quantity), 0), "
                    "COALESCE(SUM(s.quantity * p.price), 0) "
                    "FROM sales s JOIN products p ON s.product_id = p.product_id" + where +
                    f" GROUP BY {period_expr}",
                    params,
                )
                rows = cur.fetchall()

    series = []
    if group_by == "category":
        grouped = {}
        for category, period_value, volume, amount in rows:
            grouped.setdefault(category, {})[normalize(period_value)] = (int(volume), _money(amount))
        for category in sorted(grouped):
            data = grouped[category]
            series.append({"key": category, "points": _pad(data, periods)})
    else:
        data = {normalize(period_value): (int(volume), _money(amount))
                for period_value, volume, amount in rows}
        series.append({"key": "all", "points": _pad(data, periods)})

    return {
        "granularity": granularity,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "series": series,
    }


def _pad(data, periods):
    """按统一时间轴补零，生成 points 列表。"""
    return [
        {
            "period": period,
            "sales_volume": data.get(period, (0, "0.00"))[0],
            "sales_amount": data.get(period, (0, "0.00"))[1],
        }
        for period in periods
    ]

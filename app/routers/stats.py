"""数据统计分析接口：销售概况、分类统计、热销排行、日/月销售趋势。"""

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Query

from app.services import stats

router = APIRouter(prefix="/api/stats", tags=["数据统计分析"])


@router.get("/overview")
def get_overview(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    """销售概况：范围内总销量、总销售额、交易次数与去重商品数。"""
    return stats.get_overview(start_date, end_date)


@router.get("/categories")
def get_category_stats(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    """分类统计：按商品分类分组汇总。"""
    return stats.get_category_stats(start_date, end_date)


@router.get("/top-products")
def get_top_products(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    category: Optional[str] = Query(None),
    sort_by: Literal["volume", "amount"] = Query("volume"),
    limit: int = Query(10, ge=1),
):
    """热销排行：默认按销量降序，可切换按销售额降序。"""
    return stats.get_top_products(start_date, end_date, category, sort_by, limit)


@router.get("/trend")
def get_trend(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    granularity: Literal["day", "month"] = Query("day"),
    group_by: Optional[Literal["category"]] = Query(None),
):
    """日/月销售趋势：完整时间轴补零，支持按分类分组。"""
    return stats.get_trend(start_date, end_date, granularity, group_by)

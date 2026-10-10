"""销售数据管理接口：分类选项、商品列表、商品详情、销售明细。"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from app.services import queries

router = APIRouter(prefix="/api", tags=["销售数据管理"])


@router.get("/categories")
def get_categories():
    """分类选项：返回去重分类及每类商品数。"""
    return queries.list_categories()


@router.get("/products")
def get_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    category: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
):
    """商品分页列表，支持分类精确匹配与名称模糊筛选。"""
    return queries.list_products(page, page_size, category, name)


@router.get("/products/{product_id}")
def get_product(
    product_id: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    """商品详情：基础信息与统计指标（销量、销售额、交易次数、日均销量）。"""
    return queries.get_product_detail(product_id, start_date, end_date)


@router.get("/sales")
def get_sales(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    product_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    """销售明细分页，支持商品 ID 与日期筛选。"""
    return queries.list_sales(page, page_size, product_id, start_date, end_date)

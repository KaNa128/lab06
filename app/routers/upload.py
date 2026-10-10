"""CSV 上传接口：POST /api/upload。"""

from fastapi import APIRouter, File, UploadFile

from app.services.importer import import_csv

router = APIRouter(prefix="/api", tags=["销售数据管理"])


@router.post("/upload")
async def upload_csv(csv_file: UploadFile = File(...)):
    """上传 CSV，事务追加商品与销售数据。

    - 成功：200，返回导入摘要（总行数、新增商品数、新增销售数、重复跳过数等）
    - 文件 / 行校验失败：422
    - 数据库不可用：503（由全局异常处理器统一返回）
    """
    content = await csv_file.read()
    return import_csv(csv_file.filename or "", content)

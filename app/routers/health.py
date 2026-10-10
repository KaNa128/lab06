"""健康检查接口：GET /health。"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.database import ping

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    """检查服务与数据库连接是否正常。

    - 正常：200，返回 status=ok、database=connected
    - 数据库不可用：503
    """
    try:
        connected = ping()
    except Exception:
        logger.exception("数据库连接检查失败")
        connected = False

    if not connected:
        return JSONResponse(status_code=503, content={"detail": "数据库连接失败"})

    return {"status": "ok", "database": "connected"}

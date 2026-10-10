"""销售数据分析后端 应用入口。"""

from fastapi import FastAPI

from app.routers import health

app = FastAPI(title="销售数据分析后端", version="0.1.0")

# 健康检查（不在 /api 前缀下）
app.include_router(health.router)

# 业务路由（后续阶段实现，统一以 /api 为前缀挂载）

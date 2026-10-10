"""销售数据分析后端 应用入口。"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pymysql import err as pymysql_err
from swagger_ui_bundle import swagger_ui_path

from app.routers import health, manage, upload

logger = logging.getLogger(__name__)

# 关闭默认 /docs（默认从公网 CDN 加载脚本，本机不可用），改用本地静态资源
app = FastAPI(title="销售数据分析后端", version="0.1.0", docs_url=None)

STATIC_SWAGGER = "/static/swagger-ui"
app.mount(STATIC_SWAGGER, StaticFiles(directory=swagger_ui_path), name="swagger-ui")


@app.get("/docs", include_in_schema=False)
def swagger_ui():
    """本地化的 Swagger UI 页面（离线可用）。

    同时加载 swagger-ui-bundle.js 与 swagger-ui-standalone-preset.js，
    以避免引用未定义的 SwaggerUIStandalonePreset。
    """
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{app.title} - Swagger UI</title>
    <link rel="shortcut icon" href="{STATIC_SWAGGER}/favicon-32x32.png">
    <link rel="stylesheet" type="text/css" href="{STATIC_SWAGGER}/swagger-ui.css">
    <style>
        html {{ box-sizing: border-box; overflow-y: scroll; }}
        *, *:before, *:after {{ box-sizing: inherit; }}
        body {{ margin: 0; background: #fafafa; }}
    </style>
</head>
<body>
<div id="swagger-ui"></div>
<script src="{STATIC_SWAGGER}/swagger-ui-bundle.js"></script>
<script src="{STATIC_SWAGGER}/swagger-ui-standalone-preset.js"></script>
<script>
    window.onload = function () {{
        window.ui = SwaggerUIBundle({{
            url: "{app.openapi_url}",
            dom_id: "#swagger-ui",
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIStandalonePreset
            ],
            layout: "StandaloneLayout"
        }});
    }};
</script>
</body>
</html>"""
    return HTMLResponse(html)


@app.exception_handler(pymysql_err.OperationalError)
async def handle_db_error(request: Request, exc: pymysql_err.OperationalError):
    """数据库连接失败：统一返回 503。"""
    logger.exception("数据库连接失败: %s", exc)
    return JSONResponse(status_code=503, content={"detail": "数据库连接失败"})


# 健康检查（不在 /api 前缀下）
app.include_router(health.router)

# 业务路由（统一以 /api 为前缀）
app.include_router(upload.router)
app.include_router(manage.router)

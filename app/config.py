"""应用配置：从项目根目录 .env 读取数据库连接信息。

账号、密码等敏感信息一律来源于 .env，不写入代码。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（app/ 的上一级）
BASE_DIR = Path(__file__).resolve().parent.parent

# 加载根目录 .env（不覆盖已存在的环境变量）
load_dotenv(BASE_DIR / ".env")


def db_config() -> dict:
    """返回 PyMySQL 连接参数；账号与密码仅来源于环境 / .env。"""
    return {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "database": os.getenv("DB_NAME", "sales"),
        "charset": "utf8mb4",
    }

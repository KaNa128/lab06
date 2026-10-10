"""数据库访问层：建立连接并提供连接上下文管理器。"""

from contextlib import contextmanager

import pymysql

from app.config import db_config


@contextmanager
def get_connection():
    """获取数据库连接，退出上下文时自动关闭，确保连接被释放。"""
    conn = pymysql.connect(**db_config())
    try:
        yield conn
    finally:
        conn.close()


def ping() -> bool:
    """检测数据库连接是否可用，可用返回 True。"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone()[0] == 1

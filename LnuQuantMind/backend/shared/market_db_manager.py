import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# ============================================================
# 行情专用 PostgreSQL 配置 (密码加密存储)
# ============================================================
_MARKET_DB_FERNET_KEY = b"Cfqb_ncv06D9FSIzna990Jrwv3QgYZr56epuuGCcexo="
_ENCRYPTED_MARKET_DB_PASSWORD = b"gAAAAABqGyFF3-Xp66XijJaQ38dlpQfXwAXObn-B9rTSpjLWkoOWCTgvlNUlYMNStjj0NDAyXGmZ4BehUZ0nF2tp5hJruwG9sA=="


def _decrypt_password(encrypted: bytes) -> str:
    """解密密码"""
    return Fernet(_MARKET_DB_FERNET_KEY).decrypt(encrypted).decode()


MARKET_DB_HOST = os.getenv("REMOTE_MARKET_DB_HOST", "106.53.100.144")
MARKET_DB_PORT = int(os.getenv("REMOTE_MARKET_DB_PORT", "5432"))
MARKET_DB_USER = os.getenv("REMOTE_MARKET_DB_USER", "quantmind_market")
MARKET_DB_PASSWORD = os.getenv("REMOTE_MARKET_DB_PASSWORD") or _decrypt_password(_ENCRYPTED_MARKET_DB_PASSWORD)
MARKET_DB_NAME = os.getenv("REMOTE_MARKET_DB_NAME", "quantmind")

MARKET_DB_URL = f"postgresql+asyncpg://{MARKET_DB_USER}:{MARKET_DB_PASSWORD}@{MARKET_DB_HOST}:{MARKET_DB_PORT}/{MARKET_DB_NAME}"

_market_engine: AsyncEngine | None = None
_market_session_factory: sessionmaker | None = None


def get_market_engine() -> AsyncEngine:
    """获取外部行情数据库的异步引擎"""
    global _market_engine, _market_session_factory
    if _market_engine is None:
        logger.info(f"Initializing external market DB engine connected to {MARKET_DB_HOST}:{MARKET_DB_PORT}")
        _market_engine = create_async_engine(
            MARKET_DB_URL,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False,
        )
        _market_session_factory = sessionmaker(
            _market_engine, class_=AsyncSession, expire_on_commit=False
        )
    return _market_engine


@asynccontextmanager
async def get_market_session() -> AsyncGenerator[AsyncSession, None]:
    """获取外部行情数据库会话"""
    get_market_engine()  # Ensure engine is initialized
    async with _market_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

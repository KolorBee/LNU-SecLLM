import logging
import os
from typing import Optional

from cryptography.fernet import Fernet
from redis import Redis

logger = logging.getLogger(__name__)

# ============================================================
# 远程 Redis 配置 (密码加密存储)
# ============================================================
_REDIS_FERNET_KEY = b"Cfqb_ncv06D9FSIzna990Jrwv3QgYZr56epuuGCcexo="
_ENCRYPTED_REDIS_PASSWORD = b"gAAAAABqGyFFI0vj9T7FncRDFMsS8IOKnmAqs8Cg_FWYpGGyok4ACizSm9RRDxIt_mVkeHRdJMpGt2HkSvFUHMjuTHVROS1LMQ=="


def _decrypt_redis_password() -> str:
    """解密 Redis 密码"""
    return Fernet(_REDIS_FERNET_KEY).decrypt(_ENCRYPTED_REDIS_PASSWORD).decode()


REMOTE_REDIS_HOST = os.getenv("REMOTE_QUOTE_REDIS_HOST", "106.53.100.144")
REMOTE_REDIS_PORT = int(os.getenv("REMOTE_QUOTE_REDIS_PORT", "6379"))
REMOTE_REDIS_USER = os.getenv("REMOTE_QUOTE_REDIS_USER", "readonly_monitor")
REMOTE_REDIS_PASSWORD = os.getenv("REMOTE_QUOTE_REDIS_PASSWORD") or _decrypt_redis_password()
REMOTE_REDIS_DB = 0


def get_remote_redis_client(db: int = None) -> Redis:
    """获取远程 Redis 客户端 (只读)"""
    if db is None:
        db = REMOTE_REDIS_DB
    return Redis(
        host=REMOTE_REDIS_HOST,
        port=REMOTE_REDIS_PORT,
        db=db,
        username=REMOTE_REDIS_USER,
        password=REMOTE_REDIS_PASSWORD,
        decode_responses=True,
    )

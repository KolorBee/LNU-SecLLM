import json
from pathlib import Path
from typing import List

from cryptography.fernet import Fernet
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"

# ============================================================
# 行情 Redis 硬编码配置 (quantmind-redis 访客只读用户)
# 密码使用 Fernet 对称加密存储，运行时解密
# ============================================================
_MARKET_REDIS_FERNET_KEY = b"Cfqb_ncv06D9FSIzna990Jrwv3QgYZr56epuuGCcexo="
_MARKET_REDIS_ENCRYPTED_PASSWORD = (
    b"gAAAAABqGyJNjS_S84D3PlQoRRPK7w8lYPAPXy2WFLJgRRGZ6iIqsoNFWOPFQHbK3bedGCR5cZCoF0HSi5aCqIqngPsG0ofMsw=="
)


def _decrypt_market_redis_password() -> str:
    """解密行情 Redis 密码"""
    return Fernet(_MARKET_REDIS_FERNET_KEY).decrypt(
        _MARKET_REDIS_ENCRYPTED_PASSWORD
    ).decode()


MARKET_REDIS_HOST = "106.53.100.144"
MARKET_REDIS_PORT = 6379
MARKET_REDIS_USER = "readonly_monitor"
MARKET_REDIS_PASSWORD = _decrypt_market_redis_password()
MARKET_REDIS_DB = 0


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(
        env_file=(str(ROOT_ENV), ".env"),
        case_sensitive=True,
        extra="ignore",
    )

    # Service
    SERVICE_NAME: str = "market-data-service"
    MARKET_DATA_HOST: str = "0.0.0.0"
    MARKET_DATA_PORT: int = 8003
    DEBUG: bool = False

    # 兼容旧代码引用的 HOST/PORT
    @property
    def HOST(self) -> str:
        return self.MARKET_DATA_HOST

    @property
    def PORT(self) -> int:
        return self.MARKET_DATA_PORT

    # Database (Unified Configuration)
    MARKET_DATA_DB_URL: str = Field(
        default="postgresql+psycopg2://postgres:@localhost:5432/quantmind",
        validation_alias=AliasChoices("MARKET_DATA_DB_URL", "DATABASE_URL"),
    )
    DB_DRIVER: str = "asyncpg"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "quantmind"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""

    @property
    def DATABASE_URL(self) -> str:
        return self.MARKET_DATA_DB_URL

    @model_validator(mode="after")
    def _ensure_database_url(self):
        # 若 DATABASE_URL 未显式配置，使用 DB_* 拼接，确保与根 .env 一致。
        current = (self.MARKET_DATA_DB_URL or "").strip()
        if current and "localhost:5432/quantmind" not in current:
            return self

        driver = (self.DB_DRIVER or "asyncpg").strip()
        user = (self.DB_USER or "postgres").strip()
        password = self.DB_PASSWORD or ""
        host = (self.DB_HOST or "localhost").strip()
        port = int(self.DB_PORT or 5432)
        db = (self.DB_NAME or "quantmind").strip()
        self.MARKET_DATA_DB_URL = (
            f"postgresql+{driver}://{user}:{password}@{host}:{port}/{db}"
        )
        return self

    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 30
    DB_ECHO: bool = False

    # Redis (Unified - OSS Edition)
    # 行情 Redis 硬编码为远程服务器，不受环境变量覆盖
    # 使用 _ 属性避免 pydantic-settings 从环境变量读取
    _REDIS_HOST_OVERRIDE: str = MARKET_REDIS_HOST
    _REDIS_PORT_OVERRIDE: int = MARKET_REDIS_PORT
    _REDIS_USER_OVERRIDE: str = MARKET_REDIS_USER
    _REDIS_PASSWORD_OVERRIDE: str = MARKET_REDIS_PASSWORD
    _REDIS_DB_OVERRIDE: int = MARKET_REDIS_DB

    @property
    def REDIS_HOST(self) -> str:
        return self._REDIS_HOST_OVERRIDE

    @property
    def REDIS_PORT(self) -> int:
        return self._REDIS_PORT_OVERRIDE

    @property
    def REDIS_USER(self) -> str:
        return self._REDIS_USER_OVERRIDE

    @property
    def REDIS_PASSWORD(self) -> str:
        return self._REDIS_PASSWORD_OVERRIDE

    @property
    def REDIS_DB(self) -> int:
        return self._REDIS_DB_OVERRIDE

    REDIS_USE_SENTINEL: bool = Field(default=False)
    REDIS_SENTINELS_RAW: str = Field(default="localhost:26379")
    REDIS_MASTER_NAME: str = "quantmind-master"

    # 远程行情快照 Redis (OSS: 使用统一 Redis)
    REMOTE_QUOTE_REDIS_HOST: str = Field(default=MARKET_REDIS_HOST)
    REMOTE_QUOTE_REDIS_PORT: int = Field(default=MARKET_REDIS_PORT)
    REMOTE_QUOTE_REDIS_PASSWORD: str = Field(default=MARKET_REDIS_PASSWORD)

    # 无订阅时的保活拉取标的，确保时序/落库链路持续有数据
    STREAM_WARMUP_SYMBOLS: str = "SZ000001,SH600000"

    # Cache TTL (seconds)
    CACHE_TTL_QUOTE: int = 1
    CACHE_TTL_KLINE: int = 60
    CACHE_TTL_SNAPSHOT: int = 5

    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30
    WS_MAX_CONNECTIONS: int = 1000

    # Data Sources
    # 生产环境禁止使用任何模拟/演示数据源；请配置真实数据源（如 ifind/tencent/sina）。
    DATA_SOURCES: list[str] = ["remote_redis", "ifind", "tencent", "sina"]
    DEFAULT_SOURCE: str = "remote_redis"

    @field_validator("DEFAULT_SOURCE")
    @classmethod
    def _validate_default_source(cls, v: str, info):  # type: ignore[override]
        data_sources = (
            (info.data.get("DATA_SOURCES") or []) if hasattr(info, "data") else []
        )
        if v and data_sources and v not in data_sources:
            raise ValueError(f"DEFAULT_SOURCE={v} 不在 DATA_SOURCES={data_sources} 中")
        return v

    @property
    def REDIS_SENTINELS(self) -> list[tuple]:
        text = (self.REDIS_SENTINELS_RAW or "").strip()
        if not text:
            return [("localhost", 26379)]
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                out = []
                for item in parsed:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        out.append((str(item[0]), int(item[1])))
                if out:
                    return out
        except Exception:
            pass
        pairs = []
        for item in text.split(","):
            seg = item.strip()
            if not seg:
                continue
            if ":" in seg:
                host, port = seg.split(":", 1)
                pairs.append((host.strip(), int(port.strip())))
            else:
                pairs.append((seg, 26379))
        return pairs or [("localhost", 26379)]

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 100

    # Monitoring
    METRICS_ENABLED: bool = True


settings = Settings()

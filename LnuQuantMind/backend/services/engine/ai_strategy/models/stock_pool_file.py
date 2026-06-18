"""股票池文件数据库模型"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class StockPoolFile(Base):
    """股票池文件表"""

    __tablename__ = "stock_pool_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), nullable=True, index=True, comment="租户ID")
    user_id = Column(String(50), nullable=False, index=True, comment="用户ID")
    pool_name = Column(String(200), nullable=True, comment="股票池名称")
    session_id = Column(String(100), index=True, comment="策略生成会话ID")
    file_key = Column(String(500), nullable=False, comment="COS文件Key")
    file_url = Column(String(1000), comment="文件URL")
    relative_path = Column(String(500), comment="相对路径")
    format = Column(String(10), default="csv", comment="文件格式")
    file_size = Column(Integer, comment="文件大小(字节)")
    code_hash = Column(String(64), comment="文件哈希值")
    stock_count = Column(Integer, comment="股票数量")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间"
    )
    is_active = Column(
        Boolean, default=True, index=True, comment="是否为当前活跃的股票池"
    )

    # 创建复合索引
    __table_args__ = (
        Index("idx_user_active", "user_id", "is_active"),
        Index("idx_tenant_user", "tenant_id", "user_id"),
        Index("idx_created_at", "created_at"),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "pool_name": self.pool_name,
            "session_id": self.session_id,
            "file_key": self.file_key,
            "file_url": self.file_url,
            "relative_path": self.relative_path,
            "format": self.format,
            "file_size": self.file_size,
            "code_hash": self.code_hash,
            "stock_count": self.stock_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_active": self.is_active,
        }

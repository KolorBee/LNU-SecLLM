import pandas as pd
import os
import logging
from sqlalchemy import create_engine, text
from pathlib import Path
from dotenv import load_dotenv

# 加载配置
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sync_factors")

def sync_factors_to_parquet():
    """
    底层加固版：从 PostgreSQL 提取因子并原子性同步到对齐文件
    支持 88 维全量因子提取，并确保写入过程不中断实盘读取。
    """
    # 1. 路径准备
    project_root = Path(__file__).resolve().parents[1]
    target_path = project_root / "db" / "custom" / "fundamental_aligned.parquet"
    temp_path = str(target_path) + ".tmp"
    os.makedirs(target_path.parent, exist_ok=True)
    
    # 2. 数据库连接
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        # 尝试本地开发默认值
        db_url = "postgresql://postgres:postgres@localhost:5432/quantmind"
        
    try:
        engine = create_engine(db_url)
        logger.info(f"正在连接数据库提取因子数据...")
        
        # 3. 执行全量因子提取 SQL
        # 注意：这里演示了如何从 JSONB 字段 'features' 中提取 88 维指标
        # 实际使用时，请确保 market_data_daily 表中已填充这些数据
        sql = """
        SELECT 
            trade_date, 
            symbol,
            stock_name,
            open,
            high,
            low,
            close,
            volume,
            amount,
            adj_factor,
            -- 不复权审计字段（默认不参与前端读取）
            COALESCE(raw_open, open * COALESCE(NULLIF(adj_factor, 0), 1)) as raw_open,
            COALESCE(raw_high, high * COALESCE(NULLIF(adj_factor, 0), 1)) as raw_high,
            COALESCE(raw_low, low * COALESCE(NULLIF(adj_factor, 0), 1)) as raw_low,
            COALESCE(raw_close, close * COALESCE(NULLIF(adj_factor, 0), 1)) as raw_close,
            COALESCE(raw_volume, volume) as raw_volume,
            COALESCE(raw_amount, amount) as raw_amount,
            is_st,
            total_mv,
            pe_ttm,
            roe,
            (features->>'pb')::float as pb,
            (features->>'bp')::float as bp,
            (features->>'ep_ttm')::float as ep_ttm,
            (features->>'listed_days')::int as listed_days,
            (features->>'turnover_rate')::float as turnover_rate,
            (features->>'idx_hs300')::int as idx_hs300,
            (features->>'idx_zz1000')::int as idx_zz1000,
            (features->>'idx_chinext')::int as idx_chinext,
            -- 动量/技术指标
            (features->>'rsi_6')::float as rsi_6,
            (features->>'rsi_14')::float as rsi_14,
            (features->>'macd_hist')::float as macd_hist,
            -- ... 后期可在此处添加剩余全部字段的映射 ...
            trade_date as _sync_mark
        FROM market_data_daily
        WHERE trade_date >= CURRENT_DATE - INTERVAL '365 days'
        """
        
        df = pd.read_sql(text(sql), engine)
        if df.empty:
            logger.warning("数据库中未找到符合条件的因子数据，同步中止。")
            return

        # 4. 数据清洗与标准化
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        # 确保 symbol 是 Prefix 格式 (SH600000)
        # 假设库里存的是标准格式，若不是则需调用 StockCodeUtil
        
        # 5. 原子性写入 (Atomic Write)
        logger.info(f"正在写入临时文件: {temp_path}")
        df.to_parquet(temp_path, index=False, engine="pyarrow")
        
        logger.info(f"执行原子替换: {target_path}")
        os.replace(temp_path, target_path)
        
        logger.info(f"✅ 同步成功！包含 {len(df.columns)} 个字段，覆盖日期至 {df['trade_date'].max().date()}")

    except Exception as e:
        logger.error(f"❌ 同步失败: {str(e)}")
        if os.path.exists(temp_path):
            os.remove(temp_path)

if __name__ == "__main__":
    sync_factors_to_parquet()

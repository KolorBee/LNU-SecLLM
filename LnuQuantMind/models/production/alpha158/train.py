#!/usr/bin/env python3
import os
import sys
import logging
import numpy as np
import pandas as pd
import lightgbm as lgb
from pathlib import Path
from datetime import datetime
from multiprocessing import Pool, cpu_count

# Pre-import restricts
os.environ["OMP_NUM_THREADS"] = str(cpu_count()) # Use all cores for training
os.environ["MKL_NUM_THREADS"] = "1"

from alpha158_calculator import Alpha158Calculator
from inference import QlibBinaryLoader

# 动态加入根路径以方便导入共享库
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
    
from backend.shared.inference_contract import build_daily_manifest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("Alpha158_Train")

# Global loader for worker processes
_worker_loader = None

def init_worker(path):
    global _worker_loader
    _worker_loader = QlibBinaryLoader(path)

def process_symbol(args):
    symbol, start_date, end_date = args
    try:
        # Use the worker-local loader
        df = _worker_loader.load_market_data([symbol], start_date, end_date)
        if df.empty or len(df) < 100: return None
        
        # Calculate features and labels
        feats = Alpha158Calculator.calculate(df)
        label = Alpha158Calculator.calculate_label(df)
        
        combined = pd.concat([feats, label], axis=1)
        # Drop rows where label is NaN (trailing days)
        combined = combined.dropna(subset=['LABEL0'])
        return combined
    except Exception as e:
        logger.error(f"Error processing {symbol}: {str(e)}")
        return None

def main():
    # Updated Time Ranges
    start_date = "2019-01-01"
    end_date = "2026-05-15"


    train_end_date = pd.Timestamp("2024-12-31")
    valid_end_date = pd.Timestamp("2025-08-15")
    
    model_output = str(Path(__file__).parent / "alpha158.bin")
    data_path = "/app/db/qlib_data"
    if not Path(data_path).exists():
        project_root = Path(__file__).resolve().parents[3]
        local_data_path = project_root / "db" / "qlib_data"
        if local_data_path.exists():
            data_path = str(local_data_path)
            logger.info("Using local qlib data path: %s", data_path)
    log_file = str(Path(__file__).parent / "train.log")
    
    # Also log to file
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(file_handler)

    logger.info("Starting Alpha158 V2 Training Pipeline")
    logger.info("Range: %s to %s", start_date, end_date)

    # Use a dummy loader just to get symbols
    main_loader = QlibBinaryLoader(data_path)
    symbols = [s for s in main_loader.all_symbols if not (s.startswith("BJ") or s.startswith("bj"))]
    logger.info("Total symbols after BJ filtering: %d (skipped %d)", len(symbols), len(main_loader.all_symbols) - len(symbols))

    # 1. Parallel Feature Engineering (increased cores to leverage 16-core 128GB hardware)
    cores = min(cpu_count(), 14)


    logger.info("Using %d cores for parallel feature extraction...", cores)

    tasks = [(sym, start_date, end_date) for sym in symbols]

    all_dfs = []
    with Pool(processes=cores, initializer=init_worker, initargs=(data_path,)) as p:
        for i, res in enumerate(p.imap_unordered(process_symbol, tasks, chunksize=20)):
            if res is not None:
                all_dfs.append(res)
            if (i + 1) % 100 == 0:
                logger.info("Processed %d/%d symbols (valid entries: %d)...", i+1, len(symbols), len(all_dfs))

    if not all_dfs:
        logger.error("No data collected. Check data path.")
        sys.exit(1)

    logger.info("Combining data from %d symbols...", len(all_dfs))

    # Combine in batches to reduce memory spike
    batch_size = 500
    combined_batches = []
    for i in range(0, len(all_dfs), batch_size):
        batch = all_dfs[i:i+batch_size]
        combined_batches.append(pd.concat(batch).sort_index())
        logger.info("Combined batch %d/%d...", (i//batch_size)+1, (len(all_dfs)+batch_size-1)//batch_size)

    full_df = pd.concat(combined_batches).sort_index()
    del all_dfs, combined_batches  # Free memory
    
    logger.info("Final dataset shape: %s", full_df.shape)
    
    # --- DUAL CROSS SECTIONAL NORMALIZATION ---
    logger.info("Applying cross-sectional percent rank normalization to features AND labels...")
    
    # We rank everything except possibly indices/non-feature cols, but here we rank everything in the columns
    # Every column (including LABEL0) is converted to a percentile rank (0.0-1.0) within its day
    full_df = full_df.groupby(level='datetime').rank(pct=True)
    
    logger.info("Dual cross-sectional rank normalization completed.")
    # ------------------------------------------

    # 2. Prepare Training/Validation/Testing split with Gaps to prevent look-ahead bias
    dt_values = full_df.index.get_level_values('datetime')
    unique_dates = pd.Series(sorted(dt_values.unique()))
    
    gap_days = 3  # Gap equals label look-ahead horizon (T+3)
    
    # Find indices for end dates in unique dates list
    train_end_idx = unique_dates[unique_dates <= train_end_date].index[-1]
    valid_end_idx = unique_dates[unique_dates <= valid_end_date].index[-1]
    
    # Validation starts gap_days after train_end
    valid_start_idx = train_end_idx + 1 + gap_days
    # Testing starts gap_days after valid_end
    test_start_idx = valid_end_idx + 1 + gap_days
    
    if valid_start_idx >= len(unique_dates) or test_start_idx >= len(unique_dates):
        logger.error("Dataset size too small to apply gaps. Reduce gap_days or check date ranges.")
        sys.exit(1)
        
    valid_start_date = unique_dates.iloc[valid_start_idx]
    test_start_date = unique_dates.iloc[test_start_idx]
    
    logger.info("Applying chronological gaps of %d trading days...", gap_days)
    logger.info("Train segment:      %s to %s", unique_dates.iloc[0].strftime("%Y-%m-%d"), train_end_date.strftime("%Y-%m-%d"))
    logger.info("Validation segment: %s to %s", valid_start_date.strftime("%Y-%m-%d"), valid_end_date.strftime("%Y-%m-%d"))
    logger.info("Testing segment:    %s to %s", test_start_date.strftime("%Y-%m-%d"), unique_dates.iloc[-1].strftime("%Y-%m-%d"))
    
    train_mask = dt_values <= train_end_date
    valid_mask = (dt_values >= valid_start_date) & (dt_values <= valid_end_date)
    test_mask  = dt_values >= test_start_date
    
    # Slice features and labels directly from full_df to save memory copies
    X_train = full_df.loc[train_mask].drop(columns=['LABEL0'])
    y_train = full_df.loc[train_mask, 'LABEL0']
    
    X_valid = full_df.loc[valid_mask].drop(columns=['LABEL0'])
    y_valid = full_df.loc[valid_mask, 'LABEL0']
    
    X_test  = full_df.loc[test_mask].drop(columns=['LABEL0'])
    y_test  = full_df.loc[test_mask, 'LABEL0']
    
    if X_train.empty or X_valid.empty or X_test.empty:
        logger.error("Empty split! Train: %d, Valid: %d, Test: %d", len(X_train), len(X_valid), len(X_test))
        sys.exit(1)
        
    logger.info("Train: %d, Valid: %d, Test: %d", len(y_train), len(y_valid), len(y_test))

    # Run garbage collection before LightGBM Dataset building to free temp objects
    import gc
    gc.collect()






    # 3. Training
    import yaml
    config_file = Path(__file__).parent / "config.yaml"
    if config_file.exists():
        logger.info("Loading LightGBM configuration from %s", config_file)
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        cfg_params = config.get("task", {}).get("model", {}).get("kwargs", {})
    else:
        logger.warning("config.yaml not found, using default parameters.")
        cfg_params = {}

    num_boost_round = cfg_params.pop("num_boost_round", 1000)
    early_stopping_rounds = cfg_params.pop("early_stopping_rounds", 50)

    params = {
        'boosting_type': 'gbdt',
        'objective': 'regression',
        'metric': {'l2'},
        'verbose': -1,
        'num_threads': cores
    }
    params.update(cfg_params)
    params['num_threads'] = cores  # Enforce restriction to respect CPU allocation and avoid excessive switching/memory


    # Handle metric set structure
    if 'metric' in params and isinstance(params['metric'], str):
        params['metric'] = {params['metric']}

    logger.info("Starting LightGBM training with params: %s", params)
    lgb_train = lgb.Dataset(X_train, y_train)
    lgb_eval = lgb.Dataset(X_valid, y_valid, reference=lgb_train)

    gbm = lgb.train(params,
                    lgb_train,
                    num_boost_round=num_boost_round,
                    valid_sets=lgb_eval,
                    callbacks=[
                        lgb.early_stopping(stopping_rounds=early_stopping_rounds),
                        lgb.log_evaluation(period=50)
                    ])

    # 4. Save Model
    logger.info("Saving model to %s", model_output)
    gbm.save_model(model_output)
    
    # 5. Evaluate IC on Multiple Segments (Optimized to accept feature matrix and label vector to save memory)
    def calculate_metrics(X_eval, y_eval, tag="Validation"):
        logger.info(f"Evaluating metrics on {tag} set...")
        preds = gbm.predict(X_eval)
        
        # Build minimal DataFrame for daily IC calculation to avoid keeping duplicate data in memory
        tmp = pd.DataFrame({
            'LABEL0': y_eval,
            'PRED': preds
        }, index=X_eval.index)
        daily_ic = tmp.groupby(level='datetime').apply(lambda x: x['PRED'].corr(x['LABEL0'], method='spearman'))
        
        mean_ic = daily_ic.mean()
        icir = mean_ic / daily_ic.std() if (daily_ic.std() != 0 and pd.notnull(daily_ic.std())) else 0.0
        logger.info("%s Mean IC: %.4f, ICIR: %.4f", tag, mean_ic, icir)
        return {"mean_ic": round(float(mean_ic), 4), "icir": round(float(icir), 4)}

    train_metrics = calculate_metrics(X_train, y_train, "Training")
    valid_metrics = calculate_metrics(X_valid, y_valid, "Validation")
    test_metrics = calculate_metrics(X_test, y_test, "Testing")



    # 6. Update metadata.json
    import json
    meta_path = Path(__file__).parent / "metadata.json"
    # feature_columns 在第8步构建 inference_contract 时才确定，
    # 此处先从 X_train 提取特征列名（X_train 与 X_full 列完全一致）
    _feature_columns = list(X_train.columns)
    _best_iteration = int(gbm.best_iteration) if hasattr(gbm, "best_iteration") and gbm.best_iteration else num_boost_round

    if meta_path.exists():
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
            
        if 'performance_metrics' not in meta:
            meta['performance_metrics'] = {}
            
        meta['performance_metrics']['train'] = train_metrics
        meta['performance_metrics']['valid'] = valid_metrics
        meta['performance_metrics']['test'] = test_metrics
        
        # Update labels in metadata
        meta['train_start'] = unique_dates.iloc[0].strftime("%Y-%m-%d")
        meta['train_end']   = train_end_date.strftime("%Y-%m-%d")
        meta['valid_start'] = valid_start_date.strftime("%Y-%m-%d")
        meta['valid_end']   = valid_end_date.strftime("%Y-%m-%d")
        meta['test_start']  = test_start_date.strftime("%Y-%m-%d")
        meta['test_end']    = unique_dates.iloc[-1].strftime("%Y-%m-%d")
        meta['trained_at']  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 写入特征列名和最佳迭代轮次，供推理预检（contract_precheck）使用
        # 必须与 inference_contract.json 中 frozen_inference_params 保持严格一致
        meta['feature_columns'] = _feature_columns
        meta['feature_count']   = len(_feature_columns)
        meta['best_iteration']  = _best_iteration
        
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
    logger.info(
        "metadata.json updated: feature_columns=%d, best_iteration=%d, 3-way split metrics written.",
        len(_feature_columns), _best_iteration,
    )
    
    # 7. Generate Full Prediction File (pred.pkl) for Backtesting
    logger.info("Generating full prediction file for backtesting...")
    X_full = full_df.drop(columns=['LABEL0'])
    full_preds = gbm.predict(X_full)
    
    # Create prediction DataFrame with standard Qlib index (datetime, symbol)
    pred_df = pd.DataFrame(
        {'score': full_preds}, 
        index=X_full.index
    ).reorder_levels(['datetime', 'symbol']).sort_index()
    
    pred_path = Path(__file__).parent / "pred.pkl"
    pred_df.to_pickle(str(pred_path))
    logger.info("Full prediction file saved to %s (Shape: %s)", pred_path, pred_df.shape)
    
    # 8. Generate inference contract for prechecking
    logger.info("Generating inference contract...")
    try:
        # Reset index to extract datetime & symbol as normal columns
        contract_df = X_full.reset_index().rename(columns={'datetime': 'trade_date', 'symbol': 'symbol'})
        feature_columns = list(X_full.columns)
        
        contract_daily_manifest, contract_manifest_hash = build_daily_manifest(
            contract_df,
            feature_columns,
            trade_date_col="trade_date",
            symbol_col="symbol"
        )
        
        contract_payload = {
            "contract_version": 1,
            "model_id": "alpha158",
            "run_id": "alpha158",
            "template_version": "inference_parquet_v1",
            "training_code_commit": "unknown",
            "frozen_inference_params": {
                "feature_columns": feature_columns,
                "fill_values": {},
                "best_iteration": int(gbm.best_iteration) if hasattr(gbm, "best_iteration") else num_boost_round,
                "target_horizon_days": 3
            },
            "data_manifest": {
                "daily": contract_daily_manifest,
                "manifest_hash": contract_manifest_hash,
                "pred_coverage_start": unique_dates.iloc[0].strftime("%Y-%m-%d"),
                "pred_coverage_end": unique_dates.iloc[-1].strftime("%Y-%m-%d")
            },
            "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f"),
            "contract_hash": contract_manifest_hash
        }

        
        contract_path = Path(__file__).parent / "inference_contract.json"
        with open(contract_path, "w", encoding="utf-8") as f:
            json.dump(contract_payload, f, ensure_ascii=False, indent=2)
        logger.info("Inference contract successfully saved to %s", contract_path)
    except Exception as e:
        logger.error("Failed to generate inference contract: %s", str(e), exc_info=True)



    logger.info("Training complete.")

if __name__ == "__main__":
    main()

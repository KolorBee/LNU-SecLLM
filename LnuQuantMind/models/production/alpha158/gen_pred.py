#!/usr/bin/env python3
"""Generate pred.pkl for alpha158 covering 2020-01-01 to 2026-05-20."""
import sys
sys.path.insert(0, "/app/models/production/alpha158")
sys.path.insert(0, "/app")

import pandas as pd
import numpy as np
import lightgbm as lgb
from pathlib import Path

alpha_dir = Path("/app/models/production/alpha158")
sys.path.insert(0, str(alpha_dir))

from inference import QlibBinaryLoader, _resolve_qlib_data_path
from alpha158_calculator import Alpha158Calculator

print("Loading data...")
data_path = _resolve_qlib_data_path("/app/db/qlib_data", str(alpha_dir / "alpha158.bin"))
loader = QlibBinaryLoader(data_path)
symbols = [s for s in loader.all_symbols if not (s.startswith("BJ") or s.startswith("bj"))]
print(f"Symbols: {len(symbols)}")

print("Loading market data 2020-01-01 to 2026-05-20...")
df = loader.load_market_data(symbols, "2020-01-01", "2026-05-20")
print(f"Data shape: {df.shape}")

print("Calculating Alpha158 features...")
features_df = Alpha158Calculator.calculate(df)
print(f"Features shape: {features_df.shape}")

print("Calculating label...")
label_df = Alpha158Calculator.calculate_label(df)

print("Applying cross-sectional rank normalization...")
full_df = features_df.copy()
full_df["LABEL0"] = label_df["LABEL0"]
full_df_ranked = full_df.groupby(level='datetime').rank(pct=True)

print("Loading model and predicting...")
booster = lgb.Booster(model_file=str(alpha_dir / "alpha158.bin"))
X_full = full_df_ranked.drop(columns=["LABEL0"])
full_preds = booster.predict(X_full.values.astype(np.float32), num_threads=1)

print("Generating pred.pkl...")
pred_df = pd.DataFrame(
    {"score": full_preds},
    index=X_full.index
).reorder_levels(["datetime", "symbol"]).sort_index()

pred_path = alpha_dir / "pred.pkl"
pred_df.to_pickle(str(pred_path))
print(f"pred.pkl saved: {pred_path}, shape={pred_df.shape}")

dates = pred_df.index.get_level_values("datetime")
print(f"Date range: {dates.min()} to {dates.max()}")
print(f"Total rows: {len(pred_df)}")

# Also update metadata pred_coverage
import json
meta_path = alpha_dir / "metadata.json"
meta = json.loads(meta_path.read_text(encoding="utf-8"))
meta["pred_coverage_start"] = str(dates.min().date())
meta["pred_coverage_end"] = str(dates.max().date())
meta["pred_rows"] = int(len(pred_df))
meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"metadata.json updated")

print("DONE")
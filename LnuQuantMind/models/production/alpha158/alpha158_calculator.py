import pandas as pd
import numpy as np


class Alpha158Calculator:
    """
    Full implementation of Qlib-standard Alpha158 features using pure Pandas.
    Matches the order and logic specified in LightGBM model metadata.
    Based on qlib/contrib/data/loader.py:Alpha158DL.get_feature_config()
    """

    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:
        """
        Input df MultiIndex (symbol, datetime), columns: [open, high, low, close, volume, vwap, factor]
        """
        # Ensure input columns exist
        for col in ['open', 'high', 'low', 'close', 'vwap']:
            if col not in df.columns:
                df[col] = df.get('close', 0.0)
        if 'volume' not in df.columns:
            df['volume'] = 0.0
        if 'factor' not in df.columns:
            df['factor'] = 1.0

        f = df['factor']
        o = df['open'] * f
        h = df['high'] * f
        l = df['low'] * f
        c = df['close'] * f
        v = df['volume']
        w = df['vwap'] * f

        # We'll collect all columns in a dictionary to avoid fragmentation
        feature_data = {}

        # 1. Kbar Features (9)
        feature_data['KMID'] = (c - o) / o
        feature_data['KLEN'] = (h - l) / o
        feature_data['KMID2'] = (c - o) / (h - l + 1e-12)
        feature_data['KUP'] = (h - np.maximum(o, c)) / o
        feature_data['KUP2'] = (h - np.maximum(o, c)) / (h - l + 1e-12)
        feature_data['KLOW'] = (np.minimum(o, c) - l) / o
        feature_data['KLOW2'] = (np.minimum(o, c) - l) / (h - l + 1e-12)
        feature_data['KSFT'] = (2 * c - h - l) / o
        feature_data['KSFT2'] = (2 * c - h - l) / (h - l + 1e-12)

        # 2. Price Ratios (4)
        feature_data['OPEN0'] = o / c
        feature_data['HIGH0'] = h / c
        feature_data['LOW0'] = l / c
        feature_data['VWAP0'] = w / c

        # 3. Rolling Windows
        windows = [5, 10, 20, 30, 60]

        # Precompute commonly needed series
        close_prev = c.groupby('symbol').shift(1)
        volume_prev = v.groupby('symbol').shift(1)
        close_diff = c - close_prev
        abs_close_diff = close_diff.abs()
        volume_diff = v - volume_prev
        abs_volume_diff = volume_diff.abs()
        log_vol = np.log1p(v)
        log_vol_diff = np.log1p(v / (volume_prev + 1e-12))
        pct_change = c / (close_prev + 1e-12) - 1

        # Precompute rolling sums for vectorized linear regression (BETA/RSQR/RESI)
        # For window d, xi = 0,1,...,d-1 (time index within window, 0=oldest)
        # x_mean = (d-1)/2, Sxx = d*(d^2-1)/12 (constant for fixed window)
        # Sxy = sum(xi*yi) - x_mean * sum(yi)
        # Syy = sum(yi^2) - sum(yi)^2 / d
        # beta = Sxy / Sxx, rsqr = Sxy^2 / (Sxx * Syy), resi = sqrt((Syy - Sxy^2/Sxx) / (d-2))
        #
        # sum_xiy(t) = sum_{j=0}^{d-1} j * y(t-d+1+j)  where j is position from oldest
        # Using identity: sum_{j=0}^{d-1} j * y(t-d+1+j) = t * S(t) - sum_{i=t-d+1}^{t} i * y(i)
        # where t is the absolute position counter per symbol
        pos = c.groupby('symbol').cumcount()  # 0,1,2,... per symbol
        pos_y = pos * c

        rolling_sums = {}
        rolling_sq_sums = {}
        rolling_sums_xiy = {}
        for win in windows:
            rolling_sums[win] = c.groupby('symbol').rolling(win).sum().reset_index(0, drop=True)
            rolling_sq_sums[win] = (c * c).groupby('symbol').rolling(win).sum().reset_index(0, drop=True)
            pos_y_rolling = pos_y.groupby('symbol').rolling(win).sum().reset_index(0, drop=True)
            # sum_xiy = sum_{j=0}^{d-1} j * y(t-d+1+j) = t * S(t) - sum_{i=t-d+1}^{t} i * y(i)
            rolling_sums_xiy[win] = pos * rolling_sums[win] - pos_y_rolling

        for win in windows:
            # --- ROC: Ref($close, d)/$close ---
            feature_data[f'ROC{win}'] = c.groupby('symbol').shift(win) / c - 1

            # --- MA: Mean($close, d)/$close ---
            feature_data[f'MA{win}'] = c.groupby('symbol').rolling(win).mean().reset_index(0, drop=True) / c

            # --- STD: Std($close, d)/$close ---
            feature_data[f'STD{win}'] = c.groupby('symbol').rolling(win).std().reset_index(0, drop=True) / c

            # --- BETA: Slope($close, d)/$close ---
            # Vectorized linear regression: beta = Sxy / Sxx
            d = win
            Sxx = d * (d * d - 1) / 12.0  # constant for fixed window
            x_mean = (d - 1) / 2.0
            Sxy = rolling_sums_xiy[win] - x_mean * rolling_sums[win]
            beta = Sxy / Sxx
            feature_data[f'BETA{win}'] = beta / c

            # --- RSQR: Rsquare($close, d) ---
            # R² = Sxy² / (Sxx * Syy)
            Syy = rolling_sq_sums[win] - rolling_sums[win] ** 2 / d
            rsqr = np.maximum(0.0, Sxy ** 2 / (Sxx * Syy + 1e-12))
            feature_data[f'RSQR{win}'] = rsqr

            # --- RESI: Resi($close, d)/$close ---
            # Residual std = sqrt((Syy - Sxy²/Sxx) / (d-2))
            resi = np.sqrt(np.maximum(0.0, (Syy - Sxy ** 2 / (Sxx + 1e-12)) / (d - 2 + 1e-12)))
            feature_data[f'RESI{win}'] = resi / c

            # --- MAX: Max($high, d)/$close ---
            feature_data[f'MAX{win}'] = h.groupby('symbol').rolling(win).max().reset_index(0, drop=True) / c

            # --- MIN: Min($low, d)/$close ---
            feature_data[f'MIN{win}'] = l.groupby('symbol').rolling(win).min().reset_index(0, drop=True) / c

            # --- QTLU: Quantile($close, d, 0.8)/$close ---
            feature_data[f'QTLU{win}'] = c.groupby('symbol').rolling(win).quantile(0.8).reset_index(0, drop=True) / c

            # --- QTLD: Quantile($close, d, 0.2)/$close ---
            feature_data[f'QTLD{win}'] = c.groupby('symbol').rolling(win).quantile(0.2).reset_index(0, drop=True) / c

            # --- RANK: Rank($close, d) ---
            rolling_min = c.groupby('symbol').rolling(win).min().reset_index(0, drop=True)
            rolling_max = c.groupby('symbol').rolling(win).max().reset_index(0, drop=True)
            feature_data[f'RANK{win}'] = (c - rolling_min) / (rolling_max - rolling_min + 1e-12)

            # --- RSV: ($close-Min($low,d))/(Max($high,d)-Min($low,d)+1e-12) ---
            min_l = l.groupby('symbol').rolling(win).min().reset_index(0, drop=True)
            max_h = h.groupby('symbol').rolling(win).max().reset_index(0, drop=True)
            feature_data[f'RSV{win}'] = (c - min_l) / (max_h - min_l + 1e-12)

            # --- IMAX: IdxMax($high, d)/d ---
            feature_data[f'IMAX{win}'] = h.groupby('symbol').rolling(win).apply(
                lambda arr: (len(arr) - 1 - np.argmax(arr)) / len(arr), raw=True
            ).reset_index(0, drop=True)

            # --- IMIN: IdxMin($low, d)/d ---
            feature_data[f'IMIN{win}'] = l.groupby('symbol').rolling(win).apply(
                lambda arr: (len(arr) - 1 - np.argmin(arr)) / len(arr), raw=True
            ).reset_index(0, drop=True)

            # --- IMXD: (IdxMax-IdxMin)/d ---
            feature_data[f'IMXD{win}'] = feature_data[f'IMAX{win}'] - feature_data[f'IMIN{win}']

            # --- CORR: Corr($close, Log($volume+1), d) ---
            feature_data[f'CORR{win}'] = Alpha158Calculator._rolling_corr(c, log_vol, win)

            # --- CORD: Corr($close/Ref($close,1), Log($volume/Ref($volume,1)+1), d) ---
            feature_data[f'CORD{win}'] = Alpha158Calculator._rolling_corr(pct_change, log_vol_diff, win)

            # --- CNTP: Mean($close>Ref($close,1), d) ---
            feature_data[f'CNTP{win}'] = (close_diff > 0).astype(float).groupby('symbol').rolling(win).mean().reset_index(0, drop=True)

            # --- CNTN: Mean($close<Ref($close,1), d) ---
            feature_data[f'CNTN{win}'] = (close_diff < 0).astype(float).groupby('symbol').rolling(win).mean().reset_index(0, drop=True)

            # --- CNTD: CNTP - CNTN ---
            feature_data[f'CNTD{win}'] = feature_data[f'CNTP{win}'] - feature_data[f'CNTN{win}']

            # --- SUMP: Sum(Greater($close-Ref($close,1),0), d)/(Sum(Abs($close-Ref($close,1)), d)+1e-12) ---
            pos_close_diff = np.maximum(close_diff, 0.0)
            feature_data[f'SUMP{win}'] = pos_close_diff.groupby('symbol').rolling(win).sum().reset_index(0, drop=True) / (abs_close_diff.groupby('symbol').rolling(win).sum().reset_index(0, drop=True) + 1e-12)

            # --- SUMN: Sum(Greater(Ref($close,1)-$close,0), d)/(Sum(Abs($close-Ref($close,1)), d)+1e-12) ---
            neg_close_diff = np.maximum(-close_diff, 0.0)
            feature_data[f'SUMN{win}'] = neg_close_diff.groupby('symbol').rolling(win).sum().reset_index(0, drop=True) / (abs_close_diff.groupby('symbol').rolling(win).sum().reset_index(0, drop=True) + 1e-12)

            # --- SUMD: SUMP - SUMN ---
            feature_data[f'SUMD{win}'] = feature_data[f'SUMP{win}'] - feature_data[f'SUMN{win}']

            # --- VMA: Mean($volume, d)/($volume+1e-12) ---
            feature_data[f'VMA{win}'] = v.groupby('symbol').rolling(win).mean().reset_index(0, drop=True) / (v + 1e-12)

            # --- VSTD: Std($volume, d)/($volume+1e-12) ---
            feature_data[f'VSTD{win}'] = v.groupby('symbol').rolling(win).std().reset_index(0, drop=True) / (v + 1e-12)

            # --- WVMA: Std(Abs($close/Ref($close,1)-1)*$volume, d)/(Mean(Abs($close/Ref($close,1)-1)*$volume, d)+1e-12) ---
            wvma_base = pct_change.abs() * v
            wvma_std = wvma_base.groupby('symbol').rolling(win).std().reset_index(0, drop=True)
            wvma_mean = wvma_base.groupby('symbol').rolling(win).mean().reset_index(0, drop=True)
            feature_data[f'WVMA{win}'] = wvma_std / (wvma_mean + 1e-12)

            # --- VSUMP: Sum(Greater($volume-Ref($volume,1),0), d)/(Sum(Abs($volume-Ref($volume,1)), d)+1e-12) ---
            pos_vol_diff = np.maximum(volume_diff, 0.0)
            feature_data[f'VSUMP{win}'] = pos_vol_diff.groupby('symbol').rolling(win).sum().reset_index(0, drop=True) / (abs_volume_diff.groupby('symbol').rolling(win).sum().reset_index(0, drop=True) + 1e-12)

            # --- VSUMN: Sum(Greater(Ref($volume,1)-$volume,0), d)/(Sum(Abs($volume-Ref($volume,1)), d)+1e-12) ---
            neg_vol_diff = np.maximum(-volume_diff, 0.0)
            feature_data[f'VSUMN{win}'] = neg_vol_diff.groupby('symbol').rolling(win).sum().reset_index(0, drop=True) / (abs_volume_diff.groupby('symbol').rolling(win).sum().reset_index(0, drop=True) + 1e-12)

            # --- VSUMD: VSUMP - VSUMN ---
            feature_data[f'VSUMD{win}'] = feature_data[f'VSUMP{win}'] - feature_data[f'VSUMN{win}']

        # Create DataFrame from accumulated dictionary
        res = pd.DataFrame(feature_data, index=df.index)

        # Ensure all columns exist and are in the correct order
        expected_cols = [
            "KMID", "KLEN", "KMID2", "KUP", "KUP2", "KLOW", "KLOW2", "KSFT", "KSFT2", "OPEN0", "HIGH0", "LOW0", "VWAP0",
            "ROC5", "ROC10", "ROC20", "ROC30", "ROC60", "MA5", "MA10", "MA20", "MA30", "MA60",
            "STD5", "STD10", "STD20", "STD30", "STD60", "BETA5", "BETA10", "BETA20", "BETA30", "BETA60",
            "RSQR5", "RSQR10", "RSQR20", "RSQR30", "RSQR60", "RESI5", "RESI10", "RESI20", "RESI30", "RESI60",
            "MAX5", "MAX10", "MAX20", "MAX30", "MAX60", "MIN5", "MIN10", "MIN20", "MIN30", "MIN60",
            "QTLU5", "QTLU10", "QTLU20", "QTLU30", "QTLU60", "QTLD5", "QTLD10", "QTLD20", "QTLD30", "QTLD60",
            "RANK5", "RANK10", "RANK20", "RANK30", "RANK60", "RSV5", "RSV10", "RSV20", "RSV30", "RSV60",
            "IMAX5", "IMAX10", "IMAX20", "IMAX30", "IMAX60", "IMIN5", "IMIN10", "IMIN20", "IMIN30", "IMIN60",
            "IMXD5", "IMXD10", "IMXD20", "IMXD30", "IMXD60", "CORR5", "CORR10", "CORR20", "CORR30", "CORR60",
            "CORD5", "CORD10", "CORD20", "CORD30", "CORD60", "CNTP5", "CNTP10", "CNTP20", "CNTP30", "CNTP60",
            "CNTN5", "CNTN10", "CNTN20", "CNTN30", "CNTN60", "CNTD5", "CNTD10", "CNTD20", "CNTD30", "CNTD60",
            "SUMP5", "SUMP10", "SUMP20", "SUMP30", "SUMP60", "SUMN5", "SUMN10", "SUMN20", "SUMN30", "SUMN60",
            "SUMD5", "SUMD10", "SUMD20", "SUMD30", "SUMD60", "VMA5", "VMA10", "VMA20", "VMA30", "VMA60",
            "VSTD5", "VSTD10", "VSTD20", "VSTD30", "VSTD60", "WVMA5", "WVMA10", "WVMA20", "WVMA30", "WVMA60",
            "VSUMP5", "VSUMP10", "VSUMP20", "VSUMP30", "VSUMP60", "VSUMN5", "VSUMN10", "VSUMN20", "VSUMN30", "VSUMN60",
            "VSUMD5", "VSUMD10", "VSUMD20", "VSUMD30", "VSUMD60"
        ]

        for col in expected_cols:
            if col not in res.columns:
                res[col] = 0.0

        return res[expected_cols].fillna(0).replace([np.inf, -np.inf], 0)

    @staticmethod
    def _rolling_corr(a: pd.Series, b: pd.Series, window: int) -> pd.Series:
        """Compute rolling correlation between two series per symbol group."""
        a_mean = a.groupby('symbol').rolling(window).mean().reset_index(0, drop=True)
        b_mean = b.groupby('symbol').rolling(window).mean().reset_index(0, drop=True)
        cov = ((a - a_mean) * (b - b_mean)).groupby('symbol').rolling(window).mean().reset_index(0, drop=True)
        a_std = a.groupby('symbol').rolling(window).std().reset_index(0, drop=True)
        b_std = b.groupby('symbol').rolling(window).std().reset_index(0, drop=True)
        return cov / (a_std * b_std + 1e-12)

    @staticmethod
    def calculate_label(df: pd.DataFrame) -> pd.DataFrame:
        """
        T+3 Qlib Label: Ref($close, -3) / Ref($close, -1) - 1
        This is the return from T+1 close to T+3 close.
        """
        f = df.get('factor', 1.0)
        adj_c = df['close'] * f
        label = adj_c.groupby('symbol').shift(-3) / adj_c.groupby('symbol').shift(-1) - 1
        return pd.DataFrame({'LABEL0': label}, index=df.index)

"""
Meteora DLMM Data-Driven Pair Screener and Strategy Backtester
1. Screens and ranks live pools from Meteora DLMM using quantitative criteria (V/TVL, Fee/LVR, Liquidity Depth).
2. Implements 3 Data-Driven strategies:
   - Dynamic ATR Volatility Bands
   - LST Drift Asymmetric DLMM
   - Regime Filter (Trend vs Ranging Choppiness Index)
3. Evaluates historical backtest metrics (Sharpe, Max Drawdown, Net APR over HODL).
"""

import urllib.request
import json
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

class MeteoraPairScreener:
    BASE_URL = "https://dlmm.datapi.meteora.ag"
    
    def __init__(self):
        pass
        
    def fetch_live_pools(self, limit=100):
        url = f"{self.BASE_URL}/pools?limit={limit}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                return data.get("data", [])
        except Exception as e:
            print(f"[!] Error consultando API de Meteora: {e}")
            return []
            
    def process_and_rank_pools(self, min_tvl_usd=50000.0, min_vol_usd=25000.0):
        raw_pools = self.fetch_live_pools(limit=100)
        records = []
        
        for p in raw_pools:
            tvl = float(p.get("tvl", 0.0))
            vol_24h = float(p.get("volume", {}).get("24h", 0.0))
            if tvl < min_tvl_usd or vol_24h < min_vol_usd:
                continue
                
            cfg = p.get("pool_config", {})
            base_fee = float(cfg.get("base_fee_pct", 0.1))
            dynamic_fee = float(p.get("dynamic_fee_pct", 0.0))
            total_fee = base_fee + dynamic_fee
            bin_step = cfg.get("bin_step", 10)
            
            # Key Quantitative Ratios
            # 1. Volume to TVL ratio (Capital turnover)
            v_tvl = vol_24h / max(tvl, 1.0)
            
            # 2. Daily Fee Generation Estimate ($)
            daily_fees = vol_24h * (total_fee / 100.0)
            fee_to_tvl_daily = (daily_fees / max(tvl, 1.0)) * 100.0
            
            # Categorization
            name = p.get("name", "UNKNOWN")
            is_lst = any(x in name.upper() for x in ["JITO", "BSOL", "MSOL", "INF", "JUPSOL", "BNSOL"]) and ("SOL" in name.upper())
            is_stable = ("USDC" in name.upper() and "USDT" in name.upper()) or ("EUR" in name.upper())
            is_major = ("SOL-USDC" in name.upper()) or ("CBBTC" in name.upper()) or ("ETH" in name.upper())
            
            if is_lst:
                category = "Correlated / LST"
                category_weight = 1.3 # lower IL risk premium
            elif is_stable:
                category = "Stable Pegged"
                category_weight = 1.25
            elif is_major:
                category = "Major Pair"
                category_weight = 1.15
            else:
                category = "Ecosystem / Beta"
                category_weight = 0.90 # penalty for tail dump risk
                
            # Composite DLMM Score:
            # Balances Fee Yield, Capital Turnover (V/TVL), and TVL Depth safety
            # Score = (V/TVL * 35) + (log10(TVL) * 15) + (Total_Fee * 20) * category_weight
            log_tvl = np.log10(max(tvl, 1000.0))
            score = (min(v_tvl, 10.0) * 35.0 + log_tvl * 12.0 + min(total_fee, 2.0) * 15.0) * category_weight
            
            records.append({
                "name": name,
                "address": p.get("address"),
                "category": category,
                "tvl": tvl,
                "volume_24h": vol_24h,
                "v_tvl_ratio": v_tvl,
                "bin_step": bin_step,
                "base_fee_pct": base_fee,
                "dynamic_fee_pct": dynamic_fee,
                "total_fee_pct": total_fee,
                "apy_reported": float(p.get("apy", 0.0)),
                "dlmm_score": score
            })
            
        df = pd.DataFrame(records)
        if not df.empty:
            df = df.sort_values(by="dlmm_score", ascending=False).reset_index(drop=True)
        return df


class DataDrivenStrategiesSimulator:
    """
    Backtester comparing 3 Data-Driven strategies against baseline
    """
    def __init__(self, days=90, dt_hours=1.0, initial_cap=10000.0):
        self.days = days
        self.dt_hours = dt_hours
        self.initial_cap = initial_cap
        self.n_steps = int(days * 24 / dt_hours)
        
    def generate_synthetic_market_data(self, s0=150.0, drift=0.1, vol=0.70):
        """Generates realistic High, Low, Close, and Volume series"""
        dt = self.dt_hours / (365.25 * 24.0)
        np.random.seed(42)
        
        # 1-hour returns
        z = np.random.normal(0, 1, self.n_steps)
        # Regime switches (volatility clustering)
        vol_regime = np.ones(self.n_steps) * vol
        # Introduce 2 high-volatility turbulence shock clusters
        vol_regime[int(self.n_steps*0.25):int(self.n_steps*0.40)] *= 1.8
        vol_regime[int(self.n_steps*0.70):int(self.n_steps*0.82)] *= 2.2
        
        log_ret = (drift - 0.5 * vol_regime**2) * dt + vol_regime * np.sqrt(dt) * z
        close = np.zeros(self.n_steps + 1)
        close[0] = s0
        close[1:] = s0 * np.exp(np.cumsum(log_ret))
        
        # Approximate High and Low within each 1-hour bar
        high = close * (1.0 + np.abs(np.random.normal(0, 0.005, len(close))))
        low = close * (1.0 - np.abs(np.random.normal(0, 0.005, len(close))))
        
        # Volume profile with volume spikes during high volatility
        base_vol_hourly = 1500000.0 # $1.5M/hr
        vol_regime_full = np.append(vol_regime, vol_regime[-1])
        volume = base_vol_hourly * (vol_regime_full / vol)**1.5 * np.random.uniform(0.7, 1.4, self.n_steps + 1)
        
        df = pd.DataFrame({
            "close": close,
            "high": high,
            "low": low,
            "volume": volume,
            "vol_regime": vol_regime_full
        })
        
        # Calculate Rolling Indicators
        # 1. Rolling ATR (24 hours)
        tr = np.maximum(df["high"] - df["low"], np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
        df["atr_24h"] = tr.rolling(24).mean().bfill()
        df["atr_pct"] = df["atr_24h"] / df["close"]
        
        # 2. Rolling Realized Volatility (24h)
        ret = df["close"].pct_change()
        df["realized_vol_24h"] = ret.rolling(24).std() * np.sqrt(365.25 * 24)
        df["realized_vol_24h"] = df["realized_vol_24h"].bfill()
        
        # 3. Choppiness Index (Trend vs Ranging detector)
        # CI = 100 * log10(Sum(TR, n) / (Max(High, n) - Min(Low, n))) / log10(n)
        n_ci = 24
        sum_tr = tr.rolling(n_ci).sum()
        max_h = df["high"].rolling(n_ci).max()
        min_l = df["low"].rolling(n_ci).min()
        ci = 100.0 * np.log10(sum_tr / np.maximum(max_h - min_l, 1e-4)) / np.log10(n_ci)
        df["choppiness_index"] = ci.fillna(50.0)
        
        return df

    def run_backtest(self, df):
        """
        Runs and compares 4 strategies over the synthetic data:
        1. Fixed Narrow Range (±3.0%)
        2. Fixed Moderate Range (±8.0%)
        3. Strategy A: Data-Driven Dynamic ATR Bands
        4. Strategy B: Data-Driven Regime Switching (ATR + Choppiness Index Filter)
        """
        prices = df["close"].values
        volumes = df["volume"].values
        atr_pcts = df["atr_pct"].values
        ci_vals = df["choppiness_index"].values
        
        pool_tvl = 40000000.0
        active_bin_tvl = pool_tvl * 0.08
        base_fee_pct = 0.0015 # 0.15%
        
        def simulate_strategy(strategy_type):
            capital = self.initial_cap
            accum_fees = 0.0
            rebalances = 0
            rebal_costs = 0.0
            
            p_entry = prices[0]
            
            # Initial half range
            if strategy_type == "fixed_narrow":
                half_range = 0.03
            elif strategy_type == "fixed_moderate":
                half_range = 0.08
            elif strategy_type == "dynamic_atr":
                half_range = float(np.clip(atr_pcts[0] * 2.2, 0.035, 0.14))
            elif strategy_type == "regime_switch":
                half_range = 0.05
                
            p_lower = p_entry * (1.0 - half_range)
            p_upper = p_entry * (1.0 + half_range)
            
            def get_L_and_tokens(cap, p, pa, pb):
                sp = np.sqrt(p)
                spa = np.sqrt(pa)
                spb = np.sqrt(pb)
                denom = (2.0 * sp - spa - p / spb)
                L = cap / denom
                x = L * (1.0 / sp - 1.0 / spb)
                y = L * (sp - spa)
                return L, x, y
                
            L, token_x, token_y = get_L_and_tokens(capital, p_entry, p_lower, p_upper)
            values_series = [capital]
            
            for t in range(1, len(prices)):
                p = prices[t]
                v_hr = volumes[t]
                
                # Update tokens
                sqrt_p = np.sqrt(p)
                sqrt_pa = np.sqrt(p_lower)
                sqrt_pb = np.sqrt(p_upper)
                
                if p <= p_lower:
                    token_x = L * (1.0 / sqrt_pa - 1.0 / sqrt_pb)
                    token_y = 0.0
                elif p >= p_upper:
                    token_x = 0.0
                    token_y = L * (sqrt_pb - sqrt_pa)
                else:
                    token_x = L * (1.0 / sqrt_p - 1.0 / sqrt_pb)
                    token_y = L * (sqrt_p - sqrt_pa)
                    
                pos_val = token_x * p + token_y
                
                # Check if in range to earn fees
                in_range = (p_lower <= p <= p_upper)
                if in_range:
                    user_share = min(pos_val / active_bin_tvl, 1.0)
                    # dynamic fee boost during high vol
                    dyn_mult = 1.0 + min(atr_pcts[t] * 15.0, 3.0)
                    step_fee = v_hr * (base_fee_pct * dyn_mult) * user_share * 0.88
                    accum_fees += step_fee
                    
                # Rebalance Condition Check
                dist_down = p_entry - p_lower
                dist_up = p_upper - p_entry
                
                if strategy_type == "regime_switch":
                    # If trending (CI < 38), be conservative and let range breathe (don't rebalance immediately)
                    thresh = 0.94 if ci_vals[t] < 38.0 else 0.88
                else:
                    thresh = 0.90
                    
                thresh_low = p_entry - thresh * dist_down
                thresh_high = p_entry + thresh * dist_up
                
                triggered = (p <= thresh_low or p >= thresh_high)
                
                if triggered:
                    # Execute Rebalance
                    x_val = token_x * p
                    target_x_val = pos_val / 2.0
                    swap_needed = abs(x_val - target_x_val)
                    cost = swap_needed * (0.0010 + 0.0005) + 0.04
                    rebal_costs += cost
                    rebalances += 1
                    
                    new_cap = max(pos_val - cost, 0.0)
                    p_entry = p
                    
                    # Adapt range according to strategy
                    if strategy_type == "dynamic_atr":
                        # Range expands in turbulent volatility, contracts in quiet range
                        half_range = float(np.clip(atr_pcts[t] * 2.5, 0.04, 0.15))
                    elif strategy_type == "regime_switch":
                        # If market is ranging (CI > 60), tighten range to 4% for max concentration
                        # If market is volatile/trending (CI < 40), expand range to 11%
                        if ci_vals[t] > 55.0:
                            half_range = 0.045
                        elif ci_vals[t] < 42.0:
                            half_range = 0.120
                        else:
                            half_range = float(np.clip(atr_pcts[t] * 2.2, 0.05, 0.10))
                            
                    p_lower = p_entry * (1.0 - half_range)
                    p_upper = p_entry * (1.0 + half_range)
                    L, token_x, token_y = get_L_and_tokens(new_cap, p_entry, p_lower, p_upper)
                    
                values_series.append(pos_val + accum_fees)
                
            final_total = values_series[-1]
            roi = (final_total - self.initial_cap) / self.initial_cap * 100.0
            apr = roi * (365.25 / self.days)
            
            # Risk Metrics: Max Drawdown and Sharpe Ratio
            v_arr = np.array(values_series)
            peak = np.maximum.accumulate(v_arr)
            dd = (v_arr - peak) / peak
            max_dd_pct = np.min(dd) * 100.0
            
            # Daily returns
            daily_vals = v_arr[::24]
            daily_returns = np.diff(daily_vals) / daily_vals[:-1]
            sharpe = (np.mean(daily_returns) / (np.std(daily_returns) + 1e-8)) * np.sqrt(365.25)
            
            return {
                "final_total": final_total,
                "fees": accum_fees,
                "rebalances": rebalances,
                "rebal_costs": rebal_costs,
                "roi_pct": roi,
                "apr_pct": apr,
                "max_drawdown_pct": max_dd_pct,
                "sharpe_ratio": sharpe,
                "series": v_arr
            }
            
        strats = {
            "Rango Fijo Estrecho (±3.0%)": "fixed_narrow",
            "Rango Fijo Moderado (±8.0%)": "fixed_moderate",
            "Data-Driven: Dynamic ATR Bands": "dynamic_atr",
            "Data-Driven: Regime Switching (ATR+CI)": "regime_switch"
        }
        
        results = {}
        for s_name, s_type in strats.items():
            results[s_name] = simulate_strategy(s_type)
            
        # HODL Benchmark
        sol_amt_50 = (self.initial_cap / 2.0) / prices[0]
        usdc_amt_50 = self.initial_cap / 2.0
        hodl_series = sol_amt_50 * prices + usdc_amt_50
        hodl_roi = (hodl_series[-1] - self.initial_cap) / self.initial_cap * 100.0
        
        peak_h = np.maximum.accumulate(hodl_series)
        dd_h = (hodl_series - peak_h) / peak_h
        
        daily_h = hodl_series[::24]
        ret_h = np.diff(daily_h) / daily_h[:-1]
        sharpe_h = (np.mean(ret_h) / (np.std(ret_h) + 1e-8)) * np.sqrt(365.25)
        
        results["HODL 50/50 (Benchmark)"] = {
            "final_total": hodl_series[-1],
            "fees": 0.0,
            "rebalances": 0,
            "rebal_costs": 0.0,
            "roi_pct": hodl_roi,
            "apr_pct": hodl_roi * (365.25 / self.days),
            "max_drawdown_pct": np.min(dd_h) * 100.0,
            "sharpe_ratio": sharpe_h,
            "series": hodl_series
        }
        
        return results


def main():
    print("=" * 85)
    print("   METEORA DLMM: SCREENER DE PARES Y BACKTESTING DE ESTRATEGIAS DATA-DRIVEN     ")
    print("=" * 85)
    
    out_dir = r"c:\Users\paodo\Desktop\CriptPool"
    
    # 1. Screen Live Pools from Meteora
    print("\n[*] 1. Consultando y Evaluando Pools en Vivo de Meteora DLMM...")
    screener = MeteoraPairScreener()
    ranked_df = screener.process_and_rank_pools(min_tvl_usd=100000.0, min_vol_usd=50000.0)
    
    print(f"[+] Total de pools evaluados y filtrados: {len(ranked_df)}")
    print("\n[TOP 10 POOLS CLASIFICADOS POR SCORE CUANTITATIVO DLMM]:")
    print(f"{'#':<3} | {'PAR':<16} | {'CATEGORÍA':<18} | {'TVL ($)':<12} | {'VOL 24H ($)':<12} | {'V/TVL':<6} | {'FEE':<5} | {'SCORE':<6}")
    print("-" * 88)
    for idx, row in ranked_df.head(10).iterrows():
        print(f"{idx+1:<3} | {row['name']:<16} | {row['category']:<18} | ${row['tvl']:>10,.0f} | ${row['volume_24h']:>10,.0f} | {row['v_tvl_ratio']:>5.2f}x | {row['total_fee_pct']:>4.2f}% | {row['dlmm_score']:>6.1f}")
        
    # Save ranked pools to CSV for inspection
    csv_path = os.path.join(out_dir, "ranking_pares_meteora.csv")
    ranked_df.to_csv(csv_path, index=False)
    print(f"\n[+] Tabla completa exportada a: {csv_path}")
    
    # Plot Pair Screener Distribution
    fig_screen, ax_s = plt.subplots(figsize=(10, 6))
    cat_colors = {
        "Correlated / LST": "#2ca02c",
        "Stable Pegged": "#1f77b4",
        "Major Pair": "#ff7f0e",
        "Ecosystem / Beta": "#9467bd"
    }
    
    for cat, group in ranked_df.groupby("category"):
        ax_s.scatter(
            group["tvl"] / 1e6,
            group["v_tvl_ratio"],
            s=group["dlmm_score"] * 3,
            color=cat_colors.get(cat, "gray"),
            alpha=0.75,
            edgecolors="black",
            linewidth=0.8,
            label=f"{cat} (n={len(group)})"
        )
        
    ax_s.set_xscale("log")
    ax_s.set_xlabel("TVL del Pool ($ Millones USD - Log)", fontsize=10, fontweight="bold")
    ax_s.set_ylabel("Capital Turnover (Volumen 24h / TVL)", fontsize=10, fontweight="bold")
    ax_s.set_title("Meteora DLMM: Mapa Cuantitativo de Selección de Pares\n(Tamaño de burbuja = DLMM Efficiency Score)", fontsize=11, fontweight="bold")
    ax_s.grid(True, which="both", linestyle=":", alpha=0.5)
    ax_s.legend(fontsize=9, loc="upper right")
    plt.tight_layout()
    chart_screener = os.path.join(out_dir, "screener_pares_meteora.png")
    plt.savefig(chart_screener, dpi=300)
    plt.close()
    print(f"[+] Gráfico del Screener guardado en: {chart_screener}")
    
    # 2. Run Strategy Backtester
    print("\n[*] 2. Ejecutando Backtesting de Estrategias Data-Driven...")
    sim = DataDrivenStrategiesSimulator(days=90, dt_hours=1.0, initial_cap=10000.0)
    market_df = sim.generate_synthetic_market_data(s0=150.0, drift=0.15, vol=0.68)
    backtest_results = sim.run_backtest(market_df)
    
    print("\n[RESULTADOS COMPARATIVOS DE ESTRATEGIAS (90 DÍAS)]:")
    print(f"{'ESTRATEGIA':<42} | {'FINAL ($)':<10} | {'FEES ($)':<9} | {'REB':<4} | {'MAX DD':<8} | {'SHARPE':<7} | {'ROI (%)':<8} | {'APR (%)'}")
    print("-" * 110)
    
    for s_name, res in backtest_results.items():
        print(f"{s_name:<42} | ${res['final_total']:9.2f} | ${res['fees']:8.2f} | {res['rebalances']:3d}  | {res['max_drawdown_pct']:>6.1f}% | {res['sharpe_ratio']:>6.2f} | {res['roi_pct']:>+7.2f}% | {res['apr_pct']:>+6.1f}%")
        
    # Plot Backtest Curves
    fig_bt, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), gridspec_kw={'height_ratios': [2.2, 1]})
    t_days = np.linspace(0, 90, len(market_df))
    
    colors_dict = {
        "HODL 50/50 (Benchmark)": ("#7f7f7f", "--", 1.5),
        "Rango Fijo Estrecho (±3.0%)": ("#d62728", "-", 1.8),
        "Rango Fijo Moderado (±8.0%)": ("#1f77b4", "-", 2.0),
        "Data-Driven: Dynamic ATR Bands": ("#2ca02c", "-", 2.2),
        "Data-Driven: Regime Switching (ATR+CI)": ("#9467bd", "-", 2.5)
    }
    
    for s_name, res in backtest_results.items():
        c, ls, lw = colors_dict.get(s_name, ("black", "-", 1.0))
        ax1.plot(t_days, res["series"], label=f"{s_name} (ROI: {res['roi_pct']:+.1f}%)", color=c, linestyle=ls, linewidth=lw)
        
    ax1.set_title("Backtesting Comparativo: Estrategias Fijas vs. Estrategias Data-Driven en Meteora DLMM", fontsize=11, fontweight="bold")
    ax1.set_ylabel("Valor de Cartera ($ USD)", fontsize=10, fontweight="bold")
    ax1.grid(True, linestyle=":", alpha=0.5)
    ax1.legend(fontsize=8.5, loc="upper left")
    
    # Subplot 2: Market price and Choppiness/Regimes
    ax2.plot(t_days, market_df["close"], color="black", linewidth=1.2, label="Precio SOL ($)")
    ax2.set_ylabel("Precio SOL ($)", fontsize=9, fontweight="bold")
    ax2.set_xlabel("Días de Operación", fontsize=10, fontweight="bold")
    ax2.grid(True, linestyle=":", alpha=0.5)
    
    ax2_twin = ax2.twinx()
    ax2_twin.plot(t_days, market_df["choppiness_index"], color="#e377c2", linestyle=":", alpha=0.7, label="Choppiness Index (Rango vs Tendencia)")
    ax2_twin.set_ylabel("Choppiness Index", fontsize=9, color="#e377c2", fontweight="bold")
    ax2_twin.axhline(61.8, color="#2ca02c", linestyle="--", alpha=0.4, label="Zona Rango (>61.8)")
    ax2_twin.axhline(38.2, color="#d62728", linestyle="--", alpha=0.4, label="Zona Tendencia (<38.2)")
    
    plt.tight_layout()
    chart_backtest = os.path.join(out_dir, "backtest_estrategias_datadriven.png")
    plt.savefig(chart_backtest, dpi=300)
    plt.close()
    print(f"\n[+] Gráfico de Backtest guardado en: {chart_backtest}")
    print("=" * 85)

if __name__ == "__main__":
    main()

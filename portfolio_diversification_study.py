"""
Portfolio Diversification Quantitative Study:
Solana (Meteora DLMM) + Ethereum L2 (Uniswap v3 / Aerodrome)
Compares:
  Portfolio 1: 100% SOL/USDC (Single-pool aggressive)
  Portfolio 2: 50% JitoSOL/SOL + 50% SOL/USDC (Solana-only balanced)
  Portfolio 3: 4-Way Diversified Cross-Chain:
               25% JitoSOL/SOL (Meteora)
               25% SOL/USDC (Meteora)
               25% wstETH/ETH (Uniswap v3 L2)
               25% ETH/USDC (Uniswap v3 L2)
  Portfolio 4: Passive HODL Benchmark (50% SOL + 50% ETH)
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os
import json

# Set seed for reproducibility
np.random.seed(42)

def simulate_portfolio_dynamics(days=365, initial_capital=10000.0):
    dt_days = 1.0 / 365.25
    n_days = days
    
    # 1. Market Asset Prices (Correlated Geometric Brownian Motion)
    # Annual parameters:
    mu_sol, sigma_sol = 0.20, 0.75 # SOL: 20% drift, 75% vol
    mu_eth, sigma_eth = 0.15, 0.52 # ETH: 15% drift, 52% vol
    rho = 0.72                     # Correlation SOL-ETH
    
    # Covariance Matrix
    cov = np.array([
        [1.0, rho],
        [rho, 1.0]
    ])
    chol = np.linalg.cholesky(cov)
    
    # Standard normal draws
    z_uncorr = np.random.normal(0, 1, (2, n_days))
    z_corr = chol @ z_uncorr
    
    # Prices
    ret_sol = (mu_sol - 0.5 * sigma_sol**2) * dt_days + sigma_sol * np.sqrt(dt_days) * z_corr[0]
    ret_eth = (mu_eth - 0.5 * sigma_eth**2) * dt_days + sigma_eth * np.sqrt(dt_days) * z_corr[1]
    
    sol_prices = np.zeros(n_days + 1)
    eth_prices = np.zeros(n_days + 1)
    sol_prices[0] = 150.0
    eth_prices[0] = 2800.0
    sol_prices[1:] = sol_prices[0] * np.exp(np.cumsum(ret_sol))
    eth_prices[1:] = eth_prices[0] * np.exp(np.cumsum(ret_eth))
    
    # Pegged ratios (drifting with staking yields)
    jitosol_ratio = 1.07 * np.exp(0.075 * np.linspace(0, days/365.25, n_days + 1))
    wsteth_ratio = 1.18 * np.exp(0.035 * np.linspace(0, days/365.25, n_days + 1))
    
    # 2. Daily Yield & Fee Generation Engine
    # Pool net daily fee rates (annualized rates converted to daily compounded):
    # - JitoSOL/SOL on Meteora: ~48% APR in SOL (micro range, almost 0 IL)
    # - SOL/USDC on Meteora: ~140% APR in USD (dynamic ATR bands, accounting for LVR)
    # - wstETH/ETH on L2: ~20% APR in ETH (tight range, 0 IL)
    # - ETH/USDC on L2: ~55% APR in USD (lower vol, fewer rebalances than SOL)
    
    daily_apr_jitosol = 0.48 / 365.25
    daily_apr_sol_usdc = 1.40 / 365.25
    daily_apr_wsteth = 0.20 / 365.25
    daily_apr_eth_usdc = 0.55 / 365.25
    
    # Tracking components for Portfolio 3 (Cross-Chain Diversified)
    cap_per_bucket = initial_capital / 4.0 # $2,500 each
    
    # Bucket 1: JitoSOL/SOL ($2,500 denominated in SOL)
    sol_b1 = cap_per_bucket / sol_prices[0]
    val_b1_series = np.zeros(n_days + 1)
    sol_b1_accum = sol_b1
    
    # Bucket 2: SOL/USDC ($2,500 in USD)
    val_b2 = cap_per_bucket
    val_b2_series = np.zeros(n_days + 1)
    
    # Bucket 3: wstETH/ETH ($2,500 denominated in ETH)
    eth_b3 = cap_per_bucket / eth_prices[0]
    val_b3_series = np.zeros(n_days + 1)
    eth_b3_accum = eth_b3
    
    # Bucket 4: ETH/USDC ($2,500 in USD)
    val_b4 = cap_per_bucket
    val_b4_series = np.zeros(n_days + 1)
    
    # Portfolio 1: 100% SOL/USDC
    val_p1 = initial_capital
    val_p1_series = np.zeros(n_days + 1)
    
    # Portfolio 2: 50% JitoSOL/SOL + 50% SOL/USDC (Solana Only)
    p2_sol_bucket = (initial_capital * 0.50) / sol_prices[0]
    p2_usdc_bucket = initial_capital * 0.50
    val_p2_series = np.zeros(n_days + 1)
    
    # Benchmark: HODL 50% SOL + 50% ETH (No LP, no fees)
    hodl_sol_qty = (initial_capital * 0.50) / sol_prices[0]
    hodl_eth_qty = (initial_capital * 0.50) / eth_prices[0]
    val_hodl_series = np.zeros(n_days + 1)
    
    for t in range(n_days + 1):
        p_sol = sol_prices[t]
        p_eth = eth_prices[t]
        
        # Benchmark HODL
        val_hodl_series[t] = hodl_sol_qty * p_sol + hodl_eth_qty * p_eth
        
        if t == 0:
            val_b1_series[0] = cap_per_bucket
            val_b2_series[0] = cap_per_bucket
            val_b3_series[0] = cap_per_bucket
            val_b4_series[0] = cap_per_bucket
            val_p1_series[0] = initial_capital
            val_p2_series[0] = initial_capital
            continue
            
        # Daily IL / price effect on CLMM LP positions:
        # For SOL/USDC: 50% delta to SOL price + IL drag when price moves
        sol_ret_day = ret_sol[t-1]
        eth_ret_day = ret_eth[t-1]
        
        # DLMM position value change: delta ~0.50 * underlying return - small daily divergence variance
        dlmm_sol_val_delta = 0.50 * (p_sol / sol_prices[t-1] - 1.0) - 0.0003
        dlmm_eth_val_delta = 0.50 * (p_eth / eth_prices[t-1] - 1.0) - 0.0002
        
        # Portfolio 1 (100% SOL/USDC)
        val_p1 = val_p1 * (1.0 + dlmm_sol_val_delta + daily_apr_sol_usdc)
        val_p1_series[t] = val_p1
        
        # Portfolio 2 (50% JitoSOL/SOL + 50% SOL/USDC)
        p2_sol_bucket *= (1.0 + daily_apr_jitosol)
        p2_usdc_bucket *= (1.0 + dlmm_sol_val_delta + daily_apr_sol_usdc)
        val_p2_series[t] = p2_sol_bucket * p_sol + p2_usdc_bucket
        
        # Portfolio 3 (Cross-Chain 4-Way Diversified)
        # Bucket 1: JitoSOL/SOL -> accumulates in SOL
        sol_b1_accum *= (1.0 + daily_apr_jitosol)
        val_b1_series[t] = sol_b1_accum * p_sol
        
        # Bucket 2: SOL/USDC
        val_b2 *= (1.0 + dlmm_sol_val_delta + daily_apr_sol_usdc)
        val_b2_series[t] = val_b2
        
        # Bucket 3: wstETH/ETH -> accumulates in ETH
        eth_b3_accum *= (1.0 + daily_apr_wsteth)
        val_b3_series[t] = eth_b3_accum * p_eth
        
        # Bucket 4: ETH/USDC
        val_b4 *= (1.0 + dlmm_eth_val_delta + daily_apr_eth_usdc)
        val_b4_series[t] = val_b4
        
    val_p3_series = val_b1_series + val_b2_series + val_b3_series + val_b4_series
    
    # Compute Metrics for Each Portfolio
    portfolios = {
        "100% SOL/USDC (Meteora Agresivo)": val_p1_series,
        "50% JitoSOL + 50% SOL/USDC (Solana Equilibrado)": val_p2_series,
        "Diversificado Cross-Chain (Solana + Ethereum L2)": val_p3_series,
        "HODL 50% SOL + 50% ETH (Pasivo Sin LP)": val_hodl_series
    }
    
    stats = {}
    for name, series in portfolios.items():
        final_val = series[-1]
        roi = (final_val - initial_capital) / initial_capital * 100.0
        apr = roi * (365.25 / days)
        
        # Daily returns
        d_ret = np.diff(series) / series[:-1]
        vol_annual = np.std(d_ret) * np.sqrt(365.25) * 100.0
        
        # Risk-free rate assumed at 4.5%
        rf = 0.045
        mean_ret_annual = np.mean(d_ret) * 365.25
        sharpe = (mean_ret_annual - rf) / (np.std(d_ret) * np.sqrt(365.25) + 1e-8)
        
        # Downside Deviation for Sortino
        neg_ret = d_ret[d_ret < 0]
        sortino = (mean_ret_annual - rf) / (np.std(neg_ret) * np.sqrt(365.25) + 1e-8) if len(neg_ret) > 0 else sharpe
        
        # Max Drawdown
        peak = np.maximum.accumulate(series)
        dd = (series - peak) / peak
        max_dd = np.min(dd) * 100.0
        
        stats[name] = {
            "final_val": final_val,
            "roi_pct": roi,
            "apr_pct": apr,
            "vol_annual_pct": vol_annual,
            "sharpe": sharpe,
            "sortino": sortino,
            "max_drawdown_pct": max_dd,
            "series": series
        }
        
    # Asset breakdown for Portfolio 3
    final_sol_qty = sol_b1_accum
    final_eth_qty = eth_b3_accum
    final_usd_cash = val_b2 + val_b4
    
    breakdown_p3 = {
        "sol_accumulated": final_sol_qty,
        "sol_initial": (cap_per_bucket / sol_prices[0]),
        "sol_gain_pct": ((final_sol_qty / (cap_per_bucket / sol_prices[0])) - 1.0) * 100.0,
        "eth_accumulated": final_eth_qty,
        "eth_initial": (cap_per_bucket / eth_prices[0]),
        "eth_gain_pct": ((final_eth_qty / (cap_per_bucket / eth_prices[0])) - 1.0) * 100.0,
        "usd_cash_total": final_usd_cash,
        "usd_cash_initial": cap_per_bucket * 2.0,
        "usd_gain_pct": ((final_usd_cash / (cap_per_bucket * 2.0)) - 1.0) * 100.0,
        "total_portfolio_usd": val_p3_series[-1]
    }
    
    return {
        "days": days,
        "prices_sol": sol_prices,
        "prices_eth": eth_prices,
        "stats": stats,
        "breakdown_p3": breakdown_p3,
        "p3_components": {
            "JitoSOL_SOL": val_b1_series,
            "SOL_USDC": val_b2_series,
            "wstETH_ETH": val_b3_series,
            "ETH_USDC": val_b4_series
        }
    }


def main():
    out_dir = r"c:\Users\paodo\Desktop\CriptPool"
    print("=" * 90)
    print("   ESTUDIO CUANTITATIVO DE DIVERSIFICACIÓN: SOLANA (METEORA) + ETHEREUM L2     ")
    print("=" * 90)
    
    sim_data = simulate_portfolio_dynamics(days=365, initial_capital=10000.0)
    stats = sim_data["stats"]
    b3 = sim_data["breakdown_p3"]
    
    print("\n[RESULTADOS DE CARTERA A 1 AÑO (CAPITAL INICIAL: $10,000 USD)]:")
    print(f"{'ESTRATEGIA / CARTERA':<48} | {'FINAL ($)':<11} | {'ROI (%)':<9} | {'VOL (%)':<8} | {'MAX DD':<8} | {'SHARPE':<7} | {'SORTINO':<7}")
    print("-" * 108)
    for name, s in stats.items():
        print(f"{name:<48} | ${s['final_val']:>10,.2f} | {s['roi_pct']:>+8.1f}% | {s['vol_annual_pct']:>7.1f}% | {s['max_drawdown_pct']:>7.1f}% | {s['sharpe']:>7.2f} | {s['sortino']:>7.2f}")
        
    print("\n" + "-" * 90)
    print(" [DESGLOSE POR ACTIVO DE LA CARTERA DIVERSIFICADA (4 PILARES)]:")
    print(f"  * Pilar 1 (JitoSOL/SOL):  Inició con {b3['sol_initial']:.2f} SOL  -> Finalizó con {b3['sol_accumulated']:.2f} SOL  (+{b3['sol_gain_pct']:.1f}% en SOL puro)")
    print(f"  * Pilar 2 (SOL/USDC):     Inició con $2,500 USD -> Finalizó con ${sim_data['p3_components']['SOL_USDC'][-1]:,.2f} USD")
    print(f"  * Pilar 3 (wstETH/ETH):   Inició con {b3['eth_initial']:.3f} ETH -> Finalizó con {b3['eth_accumulated']:.3f} ETH (+{b3['eth_gain_pct']:.1f}% en ETH puro)")
    print(f"  * Pilar 4 (ETH/USDC):     Inició con $2,500 USD -> Finalizó con ${sim_data['p3_components']['ETH_USDC'][-1]:,.2f} USD")
    print(f"  --------------------------------------------------------------------------------")
    print(f"  * VALOR TOTAL FINAL:      ${b3['total_portfolio_usd']:,.2f} USD (Retorno Neto: +{((b3['total_portfolio_usd']/10000.0)-1.0)*100:.1f}%)")
    print("-" * 90)
    
    # 2-Panel Plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), gridspec_kw={'height_ratios': [2.2, 1.2]})
    t_days = np.linspace(0, 365, len(sim_data["prices_sol"]))
    
    # Palette
    colors = {
        "100% SOL/USDC (Meteora Agresivo)": ("#d62728", "-.", 1.8),
        "50% JitoSOL + 50% SOL/USDC (Solana Equilibrado)": ("#ff7f0e", "--", 2.0),
        "Diversificado Cross-Chain (Solana + Ethereum L2)": ("#2ca02c", "-", 2.8),
        "HODL 50% SOL + 50% ETH (Pasivo Sin LP)": ("#7f7f7f", ":", 1.5)
    }
    
    for name, s in stats.items():
        c, ls, lw = colors.get(name, ("black", "-", 1.0))
        ax1.plot(t_days, s["series"], label=f"{name} (ROI: {s['roi_pct']:+.1f}%, Sharpe: {s['sharpe']:.2f})", color=c, linestyle=ls, linewidth=lw)
        
    ax1.set_title("Evolución de Capital: Cartera Monocadena vs. Cartera Diversificada Cross-Chain (1 Año)", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Valor Total ($ USD)", fontsize=10, fontweight="bold")
    ax1.grid(True, linestyle=":", alpha=0.5)
    ax1.legend(loc="upper left", frameon=True, facecolor="white", framealpha=0.9, fontsize=9)
    
    # Subplot 2: Stacked area of the 4 components in the Diversified Portfolio
    comp = sim_data["p3_components"]
    ax2.stackplot(
        t_days,
        comp["JitoSOL_SOL"],
        comp["SOL_USDC"],
        comp["wstETH_ETH"],
        comp["ETH_USDC"],
        labels=["JitoSOL/SOL (Acumula SOL)", "SOL/USDC (Flujo USD Alto)", "wstETH/ETH (Acumula ETH)", "ETH/USDC (Flujo USD Defensivo)"],
        colors=["#2ca02c", "#1f77b4", "#9467bd", "#e377c2"],
        alpha=0.8
    )
    ax2.set_title("Composición del Capital por Estrategia en la Cartera Diversificada", fontsize=11, fontweight="bold")
    ax2.set_xlabel("Días Transcurridos", fontsize=10, fontweight="bold")
    ax2.set_ylabel("Distribución ($ USD)", fontsize=10, fontweight="bold")
    ax2.grid(True, linestyle=":", alpha=0.5)
    ax2.legend(loc="upper left", frameon=True, facecolor="white", framealpha=0.9, fontsize=8.5)
    
    plt.tight_layout()
    chart_diversification = os.path.join(out_dir, "estudio_diversificacion_cartera.png")
    plt.savefig(chart_diversification, dpi=300)
    plt.close()
    print(f"\n[+] Gráfico guardado en: {chart_diversification}")
    
    # Save JSON summary
    export_data = {
        "days": 365,
        "initial_capital_usd": 10000.0,
        "portfolio_stats": {
            k: {
                "final_val": float(v["final_val"]),
                "roi_pct": float(v["roi_pct"]),
                "vol_annual_pct": float(v["vol_annual_pct"]),
                "sharpe": float(v["sharpe"]),
                "sortino": float(v["sortino"]),
                "max_drawdown_pct": float(v["max_drawdown_pct"])
            } for k, v in stats.items()
        },
        "diversified_breakdown": {
            "sol_accumulated": float(b3["sol_accumulated"]),
            "sol_gain_pct": float(b3["sol_gain_pct"]),
            "eth_accumulated": float(b3["eth_accumulated"]),
            "eth_gain_pct": float(b3["eth_gain_pct"]),
            "usd_gain_pct": float(b3["usd_gain_pct"])
        }
    }
    
    with open(os.path.join(out_dir, "estudio_diversificacion_resultados.json"), "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2)
        
    print(f"[+] Datos exportados a: {os.path.join(out_dir, 'estudio_diversificacion_resultados.json')}")
    print("=" * 90)

if __name__ == "__main__":
    main()

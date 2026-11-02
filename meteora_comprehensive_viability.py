"""
Meteora DLMM Comprehensive Quantitative Viability & Backtesting Simulator
Simulates real-world market microstructure on Solana for Concentrated Liquidity.
Models:
  1. Pegged / LST Pairs: JitoSOL / SOL
  2. Major Pair: SOL / USDC across 4 regimes (Crab, Bull, Bear, Whipsaw)
  3. High-Beta / Memecoin Pair
Evaluates Net ROI, LVR (Loss-Versus-Rebalancing), Gas/Priority fees, and Capital Scalability.
"""

import numpy as np
import matplotlib.pyplot as plt
import os
import json

# Set seed for reproducible deterministic tests
np.random.seed(42)

class DLMMSimulator:
    def __init__(self, initial_capital, p0, half_range_pct, fee_tier=0.0015, dynamic_fee_active=True,
                 rebalance_threshold=0.90, is_active_bot=True, name="DLMM_Pos"):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.p_entry = p0
        self.p_current = p0
        self.half_range_pct = half_range_pct
        self.base_fee_tier = fee_tier
        self.dynamic_fee_active = dynamic_fee_active
        self.rebalance_threshold = rebalance_threshold
        self.is_active_bot = is_active_bot
        self.name = name
        
        self.accumulated_fees = 0.0
        self.total_rebalances = 0
        self.total_rebalance_costs = 0.0
        self.hours_in_range = 0
        
        self._init_bounds(p0, half_range_pct)
        
    def _init_bounds(self, center_p, half_range):
        self.p_entry = center_p
        self.p_lower = center_p * (1.0 - half_range)
        self.p_upper = center_p * (1.0 + half_range)
        
        sqrt_p = np.sqrt(center_p)
        sqrt_pa = np.sqrt(self.p_lower)
        sqrt_pb = np.sqrt(self.p_upper)
        
        # DLMM / CLMM Liquidity invariant for centered position
        denom = (2.0 * sqrt_p - sqrt_pa - center_p / sqrt_pb)
        self.L = self.capital / denom
        self.token_x = self.L * (1.0 / sqrt_p - 1.0 / sqrt_pb) # Base asset
        self.token_y = self.L * (sqrt_p - sqrt_pa)             # Quote asset
        
        # Real-world DLMM concentration multiplier inside active band vs passive pool
        # In Meteora, an active range captures fees proportionally to active bin depth
        # Capital efficiency ratio C:
        self.concentration_mult = 1.0 / (1.0 - np.sqrt(self.p_lower / self.p_upper))
        
    def update_price(self, p_new):
        self.p_current = p_new
        sqrt_p = np.sqrt(p_new)
        sqrt_pa = np.sqrt(self.p_lower)
        sqrt_pb = np.sqrt(self.p_upper)
        
        if p_new <= self.p_lower:
            self.token_x = self.L * (1.0 / sqrt_pa - 1.0 / sqrt_pb)
            self.token_y = 0.0
        elif p_new >= self.p_upper:
            self.token_x = 0.0
            self.token_y = self.L * (sqrt_pb - sqrt_pa)
        else:
            self.token_x = self.L * (1.0 / sqrt_p - 1.0 / sqrt_pb)
            self.token_y = self.L * (sqrt_p - sqrt_pa)
            
    def get_pos_value(self):
        return self.token_x * self.p_current + self.token_y
        
    def is_in_range(self):
        return self.p_lower <= self.p_current <= self.p_upper
        
    def accrue_fees(self, hourly_pool_volume, active_bin_tvl, current_volatility_mult=1.0):
        if not self.is_in_range():
            return 0.0
            
        self.hours_in_range += 1
        pos_val = self.get_pos_value()
        
        # Meteora Dynamic Fee logic: base fee + volatility surge
        fee_rate = self.base_fee_tier
        if self.dynamic_fee_active and current_volatility_mult > 1.2:
            fee_rate = min(self.base_fee_tier * current_volatility_mult, 0.015) # capped at 1.5%
            
        # User share of active bin volume
        user_share = min(pos_val / max(active_bin_tvl, 1000.0), 1.0)
        
        # Net fee after 12% Meteora protocol cut
        step_fee = hourly_pool_volume * fee_rate * user_share * 0.88
        self.accumulated_fees += step_fee
        return step_fee
        
    def check_and_rebalance(self, new_half_range=None, swap_fee=0.001, slippage=0.0005, sol_gas_usd=0.04):
        if not self.is_active_bot:
            return False
            
        dist_down = self.p_entry - self.p_lower
        dist_up = self.p_upper - self.p_entry
        thresh_low = self.p_entry - self.rebalance_threshold * dist_down
        thresh_high = self.p_entry + self.rebalance_threshold * dist_up
        
        triggered = (self.p_current <= thresh_low or self.p_current >= thresh_high)
        if triggered:
            curr_val = self.get_pos_value()
            
            # Asset rebalance to 50/50 centered ratio
            current_x_val = self.token_x * self.p_current
            target_x_val = curr_val / 2.0
            swap_needed = abs(current_x_val - target_x_val)
            
            # Transaction friction (DEX swap fee + price impact + Solana priority fee)
            cost = swap_needed * (swap_fee + slippage) + sol_gas_usd
            self.total_rebalance_costs += cost
            self.capital = max(curr_val - cost, 0.0)
            self.total_rebalances += 1
            
            if new_half_range is not None:
                self.half_range_pct = new_half_range
                
            self._init_bounds(self.p_current, self.half_range_pct)
            return True
        return False


def simulate_market_regimes():
    """Simulates 4 market regimes for SOL/USDC over 90 days"""
    days = 90
    dt_hours = 1.0
    n_steps = int(days * 24 / dt_hours)
    dt = dt_hours / (365.25 * 24.0)
    
    # 1. Lateral / Crab Market (SOL oscillates between $135 - $165)
    t = np.linspace(0, days, n_steps + 1)
    np.random.seed(42)
    noise1 = np.random.normal(0, 0.008, n_steps + 1)
    p_crab = 150.0 + 12.0 * np.sin(2 * np.pi * t / 20.0) + 6.0 * np.cos(2 * np.pi * t / 7.0) + np.cumsum(noise1) * 20.0
    p_crab = np.clip(p_crab, 120.0, 180.0)
    
    # 2. Bull Market (SOL trends $150 -> $260)
    drift_bull = 1.2
    vol_bull = 0.60
    z_bull = np.random.normal(0, 1, n_steps)
    log_ret_bull = (drift_bull - 0.5 * vol_bull**2) * dt + vol_bull * np.sqrt(dt) * z_bull
    p_bull = np.zeros(n_steps + 1)
    p_bull[0] = 150.0
    p_bull[1:] = 150.0 * np.exp(np.cumsum(log_ret_bull))
    
    # 3. Bear Crash (SOL drops $150 -> $85)
    drift_bear = -1.1
    vol_bear = 0.75
    z_bear = np.random.normal(0, 1, n_steps)
    log_ret_bear = (drift_bear - 0.5 * vol_bear**2) * dt + vol_bear * np.sqrt(dt) * z_bear
    p_bear = np.zeros(n_steps + 1)
    p_bear[0] = 150.0
    p_bear[1:] = 150.0 * np.exp(np.cumsum(log_ret_bear))
    
    # 4. High-Volatility Whipsaw / Chop
    drift_chop = 0.05
    vol_chop = 1.05
    z_chop = np.random.normal(0, 1, n_steps)
    log_ret_chop = (drift_chop - 0.5 * vol_chop**2) * dt + vol_chop * np.sqrt(dt) * z_chop
    p_chop = np.zeros(n_steps + 1)
    p_chop[0] = 150.0
    p_chop[1:] = 150.0 * np.exp(np.cumsum(log_ret_chop))
    
    return {
        "Mercado Lateral (Crab)": {"prices": p_crab, "daily_vol_tvl": 1.4, "vol_mult": 1.0},
        "Mercado Alcista (Bull Run)": {"prices": p_bull, "daily_vol_tvl": 2.2, "vol_mult": 1.4},
        "Mercado Bajista (Bear Crash)": {"prices": p_bear, "daily_vol_tvl": 2.5, "vol_mult": 1.6},
        "Volatilidad Extrema (Whipsaw)": {"prices": p_chop, "daily_vol_tvl": 3.0, "vol_mult": 2.0}
    }


def run_benchmark_strategies(price_series, daily_vol_tvl, vol_mult, initial_cap=10000.0):
    """
    Executes multiple LP bot configurations on a given price trajectory
    """
    n_steps = len(price_series) - 1
    total_hours = n_steps
    days = total_hours / 24.0
    
    # Realistic Meteora SOL/USDC Pool metrics:
    # TVL = $40,000,000
    pool_tvl = 40000000.0
    daily_volume = pool_tvl * daily_vol_tvl
    hourly_volume = daily_volume / 24.0
    
    # In Meteora DLMM, the active bin band (e.g. within 2%) typically holds ~8% of total pool TVL
    active_bin_tvl_base = pool_tvl * 0.08
    
    # Setup strategies
    strategies = {
        "HODL 50/50 (Sin LP)": {
            "type": "hodl_50",
        },
        "HODL 100% SOL": {
            "type": "hodl_sol",
        },
        "Pasivo Amplio (±20%, sin rebalanceo)": {
            "type": "dlmm",
            "half_range": 0.20,
            "rebal_thresh": 1.0,
            "is_active": False,
            "dynamic_range": False
        },
        "Bot Estrecho Agresivo (±2.5%, rebalanceo 90%)": {
            "type": "dlmm",
            "half_range": 0.025,
            "rebal_thresh": 0.90,
            "is_active": True,
            "dynamic_range": False
        },
        "Bot Moderado Óptimo (±7.5%, rebalanceo 90%)": {
            "type": "dlmm",
            "half_range": 0.075,
            "rebal_thresh": 0.90,
            "is_active": True,
            "dynamic_range": False
        },
        "Bot Cuantitativo ATR Adaptativo": {
            "type": "dlmm",
            "half_range": 0.06,
            "rebal_thresh": 0.88,
            "is_active": True,
            "dynamic_range": True
        }
    }
    
    results = {}
    
    # Benchmark HODL series
    sol_amount_50 = (initial_cap / 2.0) / price_series[0]
    usdc_amount_50 = initial_cap / 2.0
    val_hodl_50 = sol_amount_50 * price_series + usdc_amount_50
    
    sol_amount_100 = initial_cap / price_series[0]
    val_hodl_100 = sol_amount_100 * price_series
    
    results["HODL 50/50 (Sin LP)"] = {
        "final_total": val_hodl_50[-1],
        "fees": 0.0,
        "rebalances": 0,
        "rebal_cost": 0.0,
        "roi_pct": (val_hodl_50[-1] - initial_cap) / initial_cap * 100.0,
        "apr_pct": ((val_hodl_50[-1] - initial_cap) / initial_cap * 100.0) * (365.25 / days),
        "series": val_hodl_50,
        "in_range_pct": 100.0
    }
    
    results["HODL 100% SOL"] = {
        "final_total": val_hodl_100[-1],
        "fees": 0.0,
        "rebalances": 0,
        "rebal_cost": 0.0,
        "roi_pct": (val_hodl_100[-1] - initial_cap) / initial_cap * 100.0,
        "apr_pct": ((val_hodl_100[-1] - initial_cap) / initial_cap * 100.0) * (365.25 / days),
        "series": val_hodl_100,
        "in_range_pct": 100.0
    }
    
    for s_name, s_cfg in strategies.items():
        if s_cfg["type"] != "dlmm":
            continue
            
        pos = DLMMSimulator(
            initial_capital=initial_cap,
            p0=price_series[0],
            half_range_pct=s_cfg["half_range"],
            fee_tier=0.0015, # 0.15% base Meteora fee
            dynamic_fee_active=True,
            rebalance_threshold=s_cfg["rebal_thresh"],
            is_active_bot=s_cfg["is_active"],
            name=s_name
        )
        
        series = [initial_cap]
        
        for t in range(1, len(price_series)):
            p = price_series[t]
            pos.update_price(p)
            
            # Estimate rolling volatility for dynamic range bot
            new_range = None
            if s_cfg.get("dynamic_range", False) and t >= 24:
                window_ret = np.diff(np.log(price_series[max(0, t-24):t+1]))
                roll_vol_annual = np.std(window_ret) * np.sqrt(365.25 * 24)
                # Adaptive range: target ~ 1.5 * daily expected move
                daily_move_est = roll_vol_annual / np.sqrt(365.25)
                new_range = np.clip(daily_move_est * 1.5, 0.035, 0.15)
                
            pos.accrue_fees(hourly_volume, active_bin_tvl_base, current_volatility_mult=vol_mult)
            pos.check_and_rebalance(new_half_range=new_range, swap_fee=0.001, slippage=0.0005, sol_gas_usd=0.04)
            
            series.append(pos.get_pos_value() + pos.accumulated_fees)
            
        final_val = pos.get_pos_value() + pos.accumulated_fees
        roi = (final_val - initial_cap) / initial_cap * 100.0
        apr = roi * (365.25 / days)
        
        results[s_name] = {
            "final_total": final_val,
            "fees": pos.accumulated_fees,
            "rebalances": pos.total_rebalances,
            "rebal_cost": pos.total_rebalance_costs,
            "roi_pct": roi,
            "apr_pct": apr,
            "series": np.array(series),
            "in_range_pct": (pos.hours_in_range / n_steps) * 100.0
        }
        
    return results


def simulate_correlated_pair(days=90):
    """
    Simulates JitoSOL / SOL (LST Pegged Pair)
    Characteristics:
      - Peg ratio drifts upward by ~7.5% APY (Solana Staking APY)
      - Micro price deviations: standard deviation ~0.15% - 0.35%
      - Extremely tight bin step (1-2 bps)
      - IL is virtually zero
    """
    hours = int(days * 24)
    dt = 1.0 / (365.25 * 24)
    drift = 0.075 # 7.5% annual staking appreciation of JitoSOL vs SOL
    micro_vol = 0.035 # 3.5% annualized micro-noise
    
    z = np.random.normal(0, 1, hours)
    log_ret = (drift - 0.5 * micro_vol**2) * dt + micro_vol * np.sqrt(dt) * z
    ratios = np.zeros(hours + 1)
    ratios[0] = 1.0700 # JitoSOL/SOL initial exchange rate
    ratios[1:] = ratios[0] * np.exp(np.cumsum(log_ret))
    
    initial_cap_sol = 100.0 # 100 SOL
    # DLMM on Meteora for JitoSOL/SOL: Range is narrow (+/- 1.2%)
    pos_lst = DLMMSimulator(
        initial_capital=initial_cap_sol,
        p0=ratios[0],
        half_range_pct=0.012, # +/- 1.2%
        fee_tier=0.0003,      # 3 bps fee tier
        dynamic_fee_active=False,
        rebalance_threshold=0.92,
        is_active_bot=True,
        name="LST_JitoSOL_SOL"
    )
    
    # TVL in JitoSOL/SOL pool ~$150M equivalent, high volume
    hourly_vol = (150.0 * initial_cap_sol * 0.8) / 24.0 # active volume
    active_tvl = 150.0 * initial_cap_sol * 0.15
    
    series_lst = [initial_cap_sol]
    for t in range(1, len(ratios)):
        r = ratios[t]
        pos_lst.update_price(r)
        pos_lst.accrue_fees(hourly_vol, active_tvl, current_volatility_mult=1.0)
        pos_lst.check_and_rebalance(swap_fee=0.0002, slippage=0.0001, sol_gas_usd=0.02)
        series_lst.append(pos_lst.get_pos_value() + pos_lst.accumulated_fees)
        
    final_sol = pos_lst.get_pos_value() + pos_lst.accumulated_fees
    net_sol_yield = (final_sol - initial_cap_sol) / initial_cap_sol * 100.0
    net_sol_apr = net_sol_yield * (365.25 / days)
    
    return {
        "days": days,
        "ratios": ratios,
        "initial_sol": initial_cap_sol,
        "final_sol": final_sol,
        "fees_sol": pos_lst.accumulated_fees,
        "rebalances": pos_lst.total_rebalances,
        "rebalance_costs_sol": pos_lst.total_rebalance_costs,
        "net_yield_pct": net_sol_yield,
        "net_apr_pct": net_sol_apr,
        "series": np.array(series_lst)
    }


def main():
    out_dir = r"c:\Users\paodo\Desktop\CriptPool"
    print("================================================================================")
    print("   INICIANDO SIMULACIÓN CUANTITATIVA DE VIABILIDAD METEORA DLMM (SOLANA)       ")
    print("================================================================================")
    
    # 1. Simulate SOL/USDC across 4 Regimes
    regimes = simulate_market_regimes()
    all_regime_results = {}
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    axes = axes.flatten()
    
    palette = {
        "HODL 50/50 (Sin LP)": ("#7f7f7f", "--", 1.5),
        "HODL 100% SOL": ("#bcbd22", ":", 1.5),
        "Pasivo Amplio (±20%, sin rebalanceo)": ("#1f77b4", "-.", 1.8),
        "Bot Estrecho Agresivo (±2.5%, rebalanceo 90%)": ("#d62728", "-", 2.0),
        "Bot Moderado Óptimo (±7.5%, rebalanceo 90%)": ("#2ca02c", "-", 2.2),
        "Bot Cuantitativo ATR Adaptativo": ("#9467bd", "-", 2.2),
    }
    
    for idx, (reg_name, reg_data) in enumerate(regimes.items()):
        prices = reg_data["prices"]
        res = run_benchmark_strategies(
            price_series=prices,
            daily_vol_tvl=reg_data["daily_vol_tvl"],
            vol_mult=reg_data["vol_mult"],
            initial_cap=10000.0
        )
        all_regime_results[reg_name] = res
        
        ax = axes[idx]
        t_days = np.linspace(0, 90, len(prices))
        
        for strat_name, s_data in res.items():
            color, ls, lw = palette.get(strat_name, ("black", "-", 1.0))
            ax.plot(t_days, s_data["series"], label=strat_name, color=color, linestyle=ls, linewidth=lw)
            
        ax.set_title(f"{reg_name}\n(Precio SOL: ${prices[0]:.0f} -> ${prices[-1]:.1f})", fontsize=11, fontweight='bold')
        ax.set_xlabel("Días", fontsize=9)
        ax.set_ylabel("Valor Portafolio ($ USD)", fontsize=9)
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.axhline(10000.0, color='gray', linestyle=':', alpha=0.5)
        
        if idx == 0:
            ax.legend(fontsize=7.5, loc='upper left')
            
    plt.tight_layout()
    plot_path_regimes = os.path.join(out_dir, "simulacion_regimenes_mercado.png")
    plt.savefig(plot_path_regimes, dpi=300)
    plt.close()
    print(f"[+] Gráfico comparativo de regímenes guardado: {plot_path_regimes}")
    
    # 2. Correlated Pair (JitoSOL / SOL) Simulation
    lst_res = simulate_correlated_pair(days=90)
    print("\n[+] Simulación de Par Correlacionado (JitoSOL / SOL):")
    print(f"  * Rendimiento Neto en 90 días: +{lst_res['net_yield_pct']:.2f}% en SOL")
    print(f"  * APR Anualizado equivalente: +{lst_res['net_apr_pct']:.2f}% APR (vs ~7.5% Staking pasivo)")
    print(f"  * Comisiones acumuladas: +{lst_res['fees_sol']:.3f} SOL")
    print(f"  * Rebalanceos ejecutados: {lst_res['rebalances']} veces (Coste total: {lst_res['rebalance_costs_sol']:.4f} SOL)")
    
    # 3. Capital Scalability Curve (Gas & Priority Fees impact vs Portfolio Size)
    capitals = [500, 1000, 2500, 5000, 10000, 25000, 50000, 100000]
    cap_rois_narrow = []
    cap_rois_mod = []
    
    # Run over Crab Market
    p_crab = regimes["Mercado Lateral (Crab)"]["prices"]
    for c in capitals:
        r_c = run_benchmark_strategies(
            price_series=p_crab,
            daily_vol_tvl=1.4,
            vol_mult=1.0,
            initial_cap=c
        )
        cap_rois_narrow.append(r_c["Bot Estrecho Agresivo (±2.5%, rebalanceo 90%)"]["roi_pct"])
        cap_rois_mod.append(r_c["Bot Moderado Óptimo (±7.5%, rebalanceo 90%)"]["roi_pct"])
        
    fig_cap, ax_cap = plt.subplots(figsize=(9, 5))
    ax_cap.plot(capitals, cap_rois_mod, marker='o', color='#2ca02c', linewidth=2.5, label="Bot Moderado Óptimo (±7.5%)")
    ax_cap.plot(capitals, cap_rois_narrow, marker='s', color='#d62728', linewidth=2, label="Bot Estrecho Agresivo (±2.5%)")
    ax_cap.set_xscale('log')
    ax_cap.set_xlabel("Capital Inicial ($ USD) - Escala Logarítmica", fontsize=10, fontweight='bold')
    ax_cap.set_ylabel("ROI Neto 90 Días (%)", fontsize=10, fontweight='bold')
    ax_cap.set_title("Efecto de Escala de Capital: Fricción Operativa (Gas/MEV) vs Rentabilidad", fontsize=11, fontweight='bold')
    ax_cap.grid(True, which="both", ls=":", alpha=0.6)
    ax_cap.legend(fontsize=9)
    plt.tight_layout()
    plot_path_cap = os.path.join(out_dir, "viabilidad_escala_capital.png")
    plt.savefig(plot_path_cap, dpi=300)
    plt.close()
    print(f"[+] Gráfico de escala de capital guardado: {plot_path_cap}")
    
    # 4. Print Summary Matrix
    print("\n" + "="*95)
    print(f"{'ESCENARIO / ESTRATEGIA':<42} | {'FINAL ($)':<10} | {'FEES ($)':<9} | {'REB':<4} | {'ROI (%)':<8} | {'APR (%)':<8}")
    print("="*95)
    
    export_json = {}
    for r_name, r_strats in all_regime_results.items():
        print(f"[{r_name}]")
        export_json[r_name] = {}
        for s_name, data in r_strats.items():
            print(f"  {s_name:<40} | ${data['final_total']:9.2f} | ${data['fees']:8.2f} | {data['rebalances']:3d}  | {data['roi_pct']:+7.2f}% | {data['apr_pct']:+7.1f}%")
            export_json[r_name][s_name] = {
                "final_total": float(data["final_total"]),
                "fees": float(data["fees"]),
                "rebalances": int(data["rebalances"]),
                "rebal_cost": float(data["rebal_cost"]),
                "roi_pct": float(data["roi_pct"]),
                "apr_pct": float(data["apr_pct"]),
                "in_range_pct": float(data["in_range_pct"])
            }
        print("-" * 95)
        
    export_json["JitoSOL_SOL"] = {
        "initial_sol": float(lst_res["initial_sol"]),
        "final_sol": float(lst_res["final_sol"]),
        "fees_sol": float(lst_res["fees_sol"]),
        "rebalances": int(lst_res["rebalances"]),
        "net_yield_pct": float(lst_res["net_yield_pct"]),
        "net_apr_pct": float(lst_res["net_apr_pct"])
    }
    
    export_json["Capital_Scalability"] = {
        "capitals": capitals,
        "rois_moderate": [float(x) for x in cap_rois_mod],
        "rois_narrow": [float(x) for x in cap_rois_narrow]
    }
    
    json_path = os.path.join(out_dir, "resultados_viabilidad_completa.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(export_json, f, indent=2)
        
    print(f"[+] Informe cuantitativo completo guardado en: {json_path}")
    print("================================================================================")

if __name__ == "__main__":
    main()

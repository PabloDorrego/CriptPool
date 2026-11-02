"""
Simulation and Viability Analysis of Meteora DLMM Concentrated Liquidity Bot
Evaluates CLMM profitability, Impermanent Loss, LVR (Loss-Versus-Rebalancing),
swap friction, and gas costs across market regimes and asset pairs.
"""

import numpy as np
import matplotlib.pyplot as plt
import os
import json

# Set seed for reproducible results
np.random.seed(42)

class DLMMPosition:
    def __init__(self, initial_capital, p_current, range_pct, fee_tier=0.002, rebalance_threshold=0.90):
        """
        initial_capital: USD capital deposited
        p_current: entry price of base asset (e.g. SOL in USDC)
        range_pct: half-width of range, e.g. 0.05 for +/- 5%
        fee_tier: pool fee rate (e.g. 0.002 = 0.20%)
        rebalance_threshold: fraction of boundary before rebalancing (e.g. 0.90 = at 90% of distance to edge)
        """
        self.p_entry = p_current
        self.p_current = p_current
        self.range_pct = range_pct
        self.fee_tier = fee_tier
        self.rebalance_threshold = rebalance_threshold
        
        self.p_lower = p_current * (1.0 - range_pct)
        self.p_upper = p_current * (1.0 + range_pct)
        
        self.capital = initial_capital
        self.accumulated_fees = 0.0
        self.total_rebalances = 0
        self.total_rebalance_costs = 0.0
        
        # Calculate initial liquidity L and token amounts
        self._setup_liquidity(initial_capital, p_current)
        
    def _setup_liquidity(self, capital, p):
        self.p_entry = p
        self.p_lower = p * (1.0 - self.range_pct)
        self.p_upper = p * (1.0 + self.range_pct)
        
        sqrt_p = np.sqrt(p)
        sqrt_pa = np.sqrt(self.p_lower)
        sqrt_pb = np.sqrt(self.p_upper)
        
        # Uniswap v3 / Meteora DLMM liquidity formula for centered position
        # capital = x * P + y
        # y = L * (sqrt_p - sqrt_pa)
        # x = L * (1/sqrt_p - 1/sqrt_pb)
        # value = x * P + y = L * [ (sqrt_p - P/sqrt_pb) + (sqrt_p - sqrt_pa) ] = L * [ 2*sqrt_p - sqrt_pa - P/sqrt_pb ]
        denom = (2.0 * sqrt_p - sqrt_pa - p / sqrt_pb)
        self.L = capital / denom
        self.token_x = self.L * (1.0 / sqrt_p - 1.0 / sqrt_pb) # SOL
        self.token_y = self.L * (sqrt_p - sqrt_pa)             # USDC
        
        # Concentration multiplier vs classic x*y=k (where range is 0 to inf)
        # Classic pool: value = 2 * L_v2 * sqrt_p -> L_v2 = capital / (2 * sqrt_p)
        L_v2 = capital / (2.0 * sqrt_p)
        self.concentration_mult = self.L / L_v2
        
    def update_position(self, p_new):
        """Update token amounts based on new price"""
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
            
    def get_position_value(self):
        """Current value of deposited tokens in USD"""
        return self.token_x * self.p_current + self.token_y
        
    def is_in_range(self):
        return self.p_lower <= self.p_current <= self.p_upper
        
    def check_rebalance_trigger(self):
        """Check if price reached the rebalance threshold (e.g. 90% towards edge or out of range)"""
        # Lower threshold: p_entry - threshold * (p_entry - p_lower)
        # Upper threshold: p_entry + threshold * (p_upper - p_entry)
        dist_down = self.p_entry - self.p_lower
        dist_up = self.p_upper - self.p_entry
        thresh_low = self.p_entry - self.rebalance_threshold * dist_down
        thresh_high = self.p_entry + self.rebalance_threshold * dist_up
        
        return self.p_current <= thresh_low or self.p_current >= thresh_high
        
    def execute_rebalance(self, swap_fee=0.001, swap_slippage=0.0005, solana_tx_fee_usd=0.04):
        """
        Close position, re-swap tokens to 50/50 value ratio at current price, pay fees, open new position centered at p_current
        """
        val = self.get_position_value()
        
        # Calculate imbalance: how much USD needs to be swapped
        # Ideal: 50% in SOL, 50% in USDC (approximately, for centered range)
        current_x_val = self.token_x * self.p_current
        current_y_val = self.token_y
        target_x_val = val / 2.0
        swap_val = abs(current_x_val - target_x_val)
        
        # Costs incurred during rebalance:
        # 1. Swap fee on the rebalanced amount
        # 2. Slippage on the rebalanced amount
        # 3. Fixed Solana priority / tx fee (approx 3 transactions: withdraw, swap, deposit = ~$0.04 - $0.10)
        rebalance_cost = swap_val * (swap_fee + swap_slippage) + solana_tx_fee_usd
        
        self.total_rebalance_costs += rebalance_cost
        new_capital = max(val - rebalance_cost, 0.0)
        
        self.total_rebalances += 1
        self._setup_liquidity(new_capital, self.p_current)


def generate_price_path(s0, dt_hours, total_hours, drift_annual, vol_annual, jumps=False):
    """Generate Geometric Brownian Motion (GBM) price path with optional jump diffusion"""
    n_steps = int(total_hours / dt_hours)
    dt = dt_hours / (365.25 * 24.0) # in years
    
    # Wiener process
    z = np.random.normal(0, 1, n_steps)
    mu = drift_annual
    sigma = vol_annual
    
    # Drift and diffusion terms
    log_ret = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * z
    
    if jumps:
        # Add Poisson jumps (market shock spikes)
        jump_intensity = 5.0 # ~5 shocks per year
        jump_prob = jump_intensity * dt
        jump_occurred = np.random.binomial(1, jump_prob, n_steps)
        jump_size = np.random.normal(-0.02, 0.05, n_steps) * jump_occurred
        log_ret += jump_size
        
    prices = np.zeros(n_steps + 1)
    prices[0] = s0
    prices[1:] = s0 * np.exp(np.cumsum(log_ret))
    return prices


def run_simulation(prices, dt_hours, initial_capital=10000.0,
                   v_tvl_ratio=1.5, pool_fee_rate=0.002, meteora_dynamic_mult=1.0,
                   protocol_fee_cut=0.12,
                   strategies=None):
    """
    Simulates different LP strategies over the price path.
    v_tvl_ratio: Daily Volume / TVL ratio of the pool
    pool_fee_rate: base swap fee of the pool
    """
    n_steps = len(prices) - 1
    total_hours = n_steps * dt_hours
    
    # Base daily fee rate = (V/TVL) * pool_fee_rate * (1 - protocol_fee_cut)
    daily_base_fee_yield = v_tvl_ratio * pool_fee_rate * (1.0 - protocol_fee_cut) * meteora_dynamic_mult
    hourly_base_fee_yield = daily_base_fee_yield / 24.0 * dt_hours
    
    results = {}
    for strat_name, strat in strategies.items():
        pos = DLMMPosition(
            initial_capital=initial_capital,
            p_current=prices[0],
            range_pct=strat['range_pct'],
            fee_tier=pool_fee_rate,
            rebalance_threshold=strat.get('rebalance_threshold', 0.95)
        )
        
        values = [initial_capital]
        fees_collected = [0.0]
        rebalances = 0
        in_range_steps = 0
        
        # Benchmark 1: HODL 50/50 (half SOL, half USDC, rebalanced never)
        # Benchmark 2: HODL 100% SOL
        for t in range(1, len(prices)):
            p = prices[t]
            pos.update_position(p)
            
            # Check fees if in range
            if pos.is_in_range():
                in_range_steps += 1
                # Fee earned in this step = Pos Value * hourly_base_fee_yield * concentration_mult
                fee = pos.get_position_value() * hourly_base_fee_yield * pos.concentration_mult
                pos.accumulated_fees += fee
                
            # Check rebalance
            if strat.get('auto_rebalance', False) and pos.check_rebalance_trigger():
                pos.execute_rebalance(
                    swap_fee=strat.get('swap_fee', 0.001),
                    swap_slippage=strat.get('swap_slippage', 0.0005),
                    solana_tx_fee_usd=0.04
                )
                
            total_val = pos.get_position_value() + pos.accumulated_fees
            values.append(total_val)
            fees_collected.append(pos.accumulated_fees)
            
        final_pos_val = pos.get_position_value()
        final_total = final_pos_val + pos.accumulated_fees
        net_profit = final_total - initial_capital
        roi = net_profit / initial_capital * 100.0
        apr = roi * (8766.0 / total_hours)
        
        results[strat_name] = {
            'final_total': final_total,
            'fees_collected': pos.accumulated_fees,
            'pos_value': final_pos_val,
            'rebalance_costs': pos.total_rebalance_costs,
            'rebalances': pos.total_rebalances,
            'time_in_range_pct': (in_range_steps / n_steps) * 100.0,
            'roi_pct': roi,
            'apr_pct': apr,
            'concentration_mult': pos.concentration_mult,
            'values_series': np.array(values),
            'fees_series': np.array(fees_collected)
        }
        
    # Benchmarks
    # 1. HODL 50/50 (half in SOL at p0, half in USDC)
    sol_amount_50 = (initial_capital / 2.0) / prices[0]
    usdc_amount_50 = initial_capital / 2.0
    hodl_50_50_series = sol_amount_50 * prices + usdc_amount_50
    
    # 2. HODL 100% SOL
    sol_amount_100 = initial_capital / prices[0]
    hodl_sol_series = sol_amount_100 * prices
    
    results['HODL 50/50 (No LP)'] = {
        'final_total': hodl_50_50_series[-1],
        'fees_collected': 0.0,
        'pos_value': hodl_50_50_series[-1],
        'rebalance_costs': 0.0,
        'rebalances': 0,
        'time_in_range_pct': 100.0,
        'roi_pct': (hodl_50_50_series[-1] - initial_capital) / initial_capital * 100.0,
        'apr_pct': ((hodl_50_50_series[-1] - initial_capital) / initial_capital * 100.0) * (8766.0 / total_hours),
        'concentration_mult': 1.0,
        'values_series': hodl_50_50_series,
        'fees_series': np.zeros(len(prices))
    }
    
    results['HODL 100% SOL'] = {
        'final_total': hodl_sol_series[-1],
        'fees_collected': 0.0,
        'pos_value': hodl_sol_series[-1],
        'rebalance_costs': 0.0,
        'rebalances': 0,
        'time_in_range_pct': 100.0,
        'roi_pct': (hodl_sol_series[-1] - initial_capital) / initial_capital * 100.0,
        'apr_pct': ((hodl_sol_series[-1] - initial_capital) / initial_capital * 100.0) * (8766.0 / total_hours),
        'concentration_mult': 1.0,
        'values_series': hodl_sol_series,
        'fees_series': np.zeros(len(prices))
    }
    
    return results


def main():
    print("================================================================================")
    print("   ANÁLISIS DE VIABILIDAD CUANTITATIVA - BOT METEORA DLMM (SOLANA)")
    print("================================================================================")
    
    # Output directory for plots and reports
    out_dir = os.path.dirname(os.path.abspath(__file__))
    
    # General Parameters
    s0 = 150.0            # SOL price = $150
    initial_cap = 10000.0 # $10,000 USD
    dt_hours = 1.0        # 1-hour resolution
    days = 90             # 90-day simulation
    total_hours = days * 24.0
    
    # Pool parameters for Meteora SOL/USDC
    v_tvl = 1.5           # Typical Meteora DLMM SOL/USDC volume-to-TVL ratio
    pool_fee = 0.002      # 0.20% fee tier
    
    # Define Strategies
    strategies = {
        "Pasivo Amplio (±25%, sin rebalanceo)": {
            "range_pct": 0.25,
            "auto_rebalance": False,
        },
        "Bot Activo Estrecho (±3%, rebalanceo 90%)": {
            "range_pct": 0.03,
            "auto_rebalance": True,
            "rebalance_threshold": 0.90,
            "swap_fee": 0.001,
            "swap_slippage": 0.0005,
        },
        "Bot Activo Moderado (±8%, rebalanceo 90%)": {
            "range_pct": 0.08,
            "auto_rebalance": True,
            "rebalance_threshold": 0.90,
            "swap_fee": 0.001,
            "swap_slippage": 0.0005,
        },
        "Bot Cuant Dinámico ATR (±5% a ±12%)": {
            "range_pct": 0.07,
            "auto_rebalance": True,
            "rebalance_threshold": 0.85,
            "swap_fee": 0.001,
            "swap_slippage": 0.0005,
        }
    }
    
    scenarios = [
        {
            "name": "Escenario 1: Mercado Lateral / Ranging (Crab Market)",
            "drift": 0.0,
            "vol": 0.50, # 50% annualized volatility, mean reverting
            "jumps": False,
            "v_tvl": 1.2
        },
        {
            "name": "Escenario 2: Mercado Alcista Fuerte (Bull Run +80%)",
            "drift": 1.2,
            "vol": 0.65,
            "jumps": False,
            "v_tvl": 2.2
        },
        {
            "name": "Escenario 3: Mercado Bajista Agudo (Bear Crash -50%)",
            "drift": -1.0,
            "vol": 0.80,
            "jumps": True,
            "v_tvl": 2.5
        },
        {
            "name": "Escenario 4: Alta Volatilidad Picada (Chop / Whip-Saw)",
            "drift": 0.1,
            "vol": 1.10, # 110% annualized volatility
            "jumps": True,
            "v_tvl": 3.0
        }
    ]
    
    all_scenario_results = {}
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    axes = axes.flatten()
    
    for idx, sc in enumerate(scenarios):
        prices = generate_price_path(
            s0=s0,
            dt_hours=dt_hours,
            total_hours=total_hours,
            drift_annual=sc['drift'],
            vol_annual=sc['vol'],
            jumps=sc['jumps']
        )
        
        res = run_simulation(
            prices=prices,
            dt_hours=dt_hours,
            initial_capital=initial_cap,
            v_tvl_ratio=sc['v_tvl'],
            pool_fee_rate=pool_fee,
            strategies=strategies
        )
        
        all_scenario_results[sc['name']] = {
            'prices': prices,
            'results': res
        }
        
        # Plot Scenario
        ax = axes[idx]
        t_days = np.linspace(0, days, len(prices))
        
        for strat_name, s_res in res.items():
            line_style = '-'
            alpha = 0.9
            width = 1.8
            if 'HODL' in strat_name:
                line_style = '--'
                width = 1.4
                alpha = 0.75
            ax.plot(t_days, s_res['values_series'], label=strat_name, linestyle=line_style, linewidth=width, alpha=alpha)
            
        ax.set_title(f"{sc['name']}\n(Precio SOL: ${prices[0]:.0f} -> ${prices[-1]:.1f})", fontsize=11, fontweight='bold')
        ax.set_xlabel("Días", fontsize=9)
        ax.set_ylabel("Valor Portafolio ($ USD)", fontsize=9)
        ax.grid(True, linestyle=":", alpha=0.5)
        ax.axhline(initial_cap, color='gray', linestyle=':', alpha=0.7)
        if idx == 0:
            ax.legend(fontsize=7.5, loc='upper left')
            
    plt.tight_layout()
    chart_path = os.path.join(out_dir, "simulacion_meteora_escenarios.png")
    plt.savefig(chart_path, dpi=300)
    plt.close()
    print(f"[+] Gráfico guardado en: {chart_path}")
    
    # Now let's do a Parametric Sensitivity Analysis:
    # 1. Range Width vs. Net Profit (finding the sweet spot)
    # 2. V/TVL ratio vs. Break-even
    # 3. Capital scale ($1k vs $10k vs $100k) to see gas friction impact
    print("\n[+] Ejecutando Barrido Paramétrico (Sensibilidad de Rango y Capital)...")
    
    range_sweep = np.linspace(0.015, 0.25, 20) # 1.5% to 25%
    avg_returns_narrow = []
    rebalances_count = []
    fees_list = []
    lvr_list = []
    
    # Test on realistic market (vol 0.65, drift 0.15) over 10 Monte Carlo runs
    n_mc = 15
    mc_results = {r: {'roi': [], 'fees': [], 'rebalances': [], 'costs': []} for r in range_sweep}
    
    for mc in range(n_mc):
        np.random.seed(100 + mc)
        p_mc = generate_price_path(s0=s0, dt_hours=dt_hours, total_hours=total_hours, drift_annual=0.15, vol_annual=0.65)
        
        for r in range_sweep:
            strat_test = {
                f"Range_{r:.3f}": {
                    "range_pct": r,
                    "auto_rebalance": True,
                    "rebalance_threshold": 0.90,
                    "swap_fee": 0.001,
                    "swap_slippage": 0.0005,
                }
            }
            res_test = run_simulation(
                prices=p_mc,
                dt_hours=dt_hours,
                initial_capital=initial_cap,
                v_tvl_ratio=1.6,
                pool_fee_rate=pool_fee,
                strategies=strat_test
            )
            key = f"Range_{r:.3f}"
            mc_results[r]['roi'].append(res_test[key]['roi_pct'])
            mc_results[r]['fees'].append(res_test[key]['fees_collected'])
            mc_results[r]['rebalances'].append(res_test[key]['rebalances'])
            mc_results[r]['costs'].append(res_test[key]['rebalance_costs'])
            
    fig2, ax2 = plt.subplots(1, 2, figsize=(14, 5.5))
    
    r_pcts = [r * 100 for r in range_sweep]
    mean_rois = [np.mean(mc_results[r]['roi']) for r in range_sweep]
    mean_fees = [np.mean(mc_results[r]['fees']) for r in range_sweep]
    mean_rebalances = [np.mean(mc_results[r]['rebalances']) for r in range_sweep]
    mean_costs = [np.mean(mc_results[r]['costs']) for r in range_sweep]
    
    ax2[0].plot(r_pcts, mean_rois, marker='o', color='#2ca02c', linewidth=2, label="ROI Neto 90 días (%)")
    ax2[0].set_xlabel("Anchura de Rango (± %)", fontsize=10, fontweight='bold')
    ax2[0].set_ylabel("Retorno Neto (%)", fontsize=10, fontweight='bold')
    ax2[0].set_title("Compromiso (Trade-off): Rango vs. ROI Neto", fontsize=11, fontweight='bold')
    ax2[0].grid(True, linestyle=":", alpha=0.6)
    ax2[0].axhline(0, color='red', linestyle='--', alpha=0.7)
    
    ax2_twin = ax2[0].twinx()
    ax2_twin.plot(r_pcts, mean_rebalances, marker='s', color='#d62728', linestyle='--', label="Nº Rebalanceos")
    ax2_twin.set_ylabel("Nº Rebalanceos en 90 días", fontsize=10, color='#d62728', fontweight='bold')
    
    # Second plot: Fees vs Rebalancing Drag
    ax2[1].plot(r_pcts, mean_fees, marker='^', color='#1f77b4', linewidth=2, label="Comisiones Brutas ($)")
    ax2[1].plot(r_pcts, mean_costs, marker='v', color='#ff7f0e', linewidth=2, label="Coste de Rebalanceo ($ Swap + Gas)")
    ax2[1].set_xlabel("Anchura de Rango (± %)", fontsize=10, fontweight='bold')
    ax2[1].set_ylabel("USD ($)", fontsize=10, fontweight='bold')
    ax2[1].set_title("Comisiones Generadas vs. Fricción Operativa", fontsize=11, fontweight='bold')
    ax2[1].grid(True, linestyle=":", alpha=0.6)
    ax2[1].legend()
    
    plt.tight_layout()
    sensitivity_chart_path = os.path.join(out_dir, "sensibilidad_rango_clmm.png")
    plt.savefig(sensitivity_chart_path, dpi=300)
    plt.close()
    print(f"[+] Gráfico de sensibilidad guardado en: {sensitivity_chart_path}")
    
    # 3. Capital Scale Feasibility (What is the minimum capital to be viable?)
    capitals = [500, 1000, 2500, 5000, 10000, 25000, 50000, 100000]
    cap_rois = []
    for cap in capitals:
        strat_cap = {
            "Bot": {
                "range_pct": 0.06,
                "auto_rebalance": True,
                "rebalance_threshold": 0.90,
                "swap_fee": 0.001,
                "swap_slippage": 0.0005,
            }
        }
        res_cap = run_simulation(
            prices=p_mc,
            dt_hours=dt_hours,
            initial_capital=cap,
            v_tvl_ratio=1.6,
            pool_fee_rate=pool_fee,
            strategies=strat_cap
        )
        cap_rois.append(res_cap["Bot"]['roi_pct'])
        
    print("\n--- RESUMEN DE RESULTADOS POR ESCENARIO ---")
    summary_data = {}
    for sc_name, data in all_scenario_results.items():
        print(f"\n>>> {sc_name}")
        summary_data[sc_name] = {}
        for strat_name, r in data['results'].items():
            print(f"  * {strat_name:38s} | Final: ${r['final_total']:9.2f} | Fees: ${r['fees_collected']:8.2f} | Rebal: {r['rebalances']:2d} (Cost: ${r['rebalance_costs']:6.2f}) | ROI: {r['roi_pct']:+6.2f}% | APR: {r['apr_pct']:+6.1f}%")
            summary_data[sc_name][strat_name] = {
                'final_total': float(r['final_total']),
                'fees_collected': float(r['fees_collected']),
                'rebalances': int(r['rebalances']),
                'rebalance_costs': float(r['rebalance_costs']),
                'roi_pct': float(r['roi_pct']),
                'apr_pct': float(r['apr_pct']),
                'in_range_pct': float(r['time_in_range_pct'])
            }
            
    summary_data['capital_scale'] = {
        'capitals': capitals,
        'rois': [float(x) for x in cap_rois]
    }
    summary_data['range_sensitivity'] = {
        'ranges_pct': r_pcts,
        'mean_rois': [float(x) for x in mean_rois],
        'mean_fees': [float(x) for x in mean_fees],
        'mean_rebalances': [float(x) for x in mean_rebalances],
        'mean_costs': [float(x) for x in mean_costs]
    }
    
    with open(os.path.join(out_dir, "simulacion_resultados.json"), "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)
        
    print(f"\n[+] Datos guardados en {os.path.join(out_dir, 'simulacion_resultados.json')}")
    print("================================================================================")

if __name__ == "__main__":
    main()

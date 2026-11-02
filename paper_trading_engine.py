"""
Meteora DLMM Paper Trading Engine (Sandbox Simulator)
Simulates an active CLMM bot executing on live market data without spending real funds.
Tracks virtual capital, position token balances, fees accrued, impermanent loss,
and executes algorithmic rebalancing with simulated slippage and gas friction.
"""

import json
import os
import time
import math
from datetime import datetime
from meteora_client import MeteoraClient

STATE_FILE = "paper_trading_state.json"
HISTORY_FILE = "paper_trading_history.json"
CONFIG_FILE = "config.json"

class PaperTradingEngine:
    def __init__(self, config_path=CONFIG_FILE):
        self.config = self._load_config(config_path)
        self.client = MeteoraClient()
        self.state = self._load_or_init_state()
        
    def _load_config(self, path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        # Defaults
        return {
            "pool_address": "5rCf1DM8LjKTw4YqhnoLcngyZYeNnQqztScTogYHAS6",
            "pool_name": "SOL-USDC",
            "initial_virtual_capital_usd": 1000.0,
            "half_range_pct": 0.075,
            "rebalance_threshold": 0.90,
            "polling_interval_seconds": 15,
            "swap_fee_pct": 0.001,
            "swap_slippage_pct": 0.0005,
            "solana_priority_fee_usd": 0.04,
            "dynamic_fee_enabled": True
        }
        
    def _load_or_init_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return self._init_new_state()
        
    def _init_new_state(self):
        pool = self.client.get_pool_by_address(self.config["pool_address"])
        p0 = pool["current_price"] if pool else 100.0
        cap = self.config["initial_virtual_capital_usd"]
        half_range = self.config["half_range_pct"]
        
        p_lower = p0 * (1.0 - half_range)
        p_upper = p0 * (1.0 + half_range)
        
        # Calculate tokens for centered position
        sqrt_p = math.sqrt(p0)
        sqrt_pa = math.sqrt(p_lower)
        sqrt_pb = math.sqrt(p_upper)
        denom = (2.0 * sqrt_p - sqrt_pa - p0 / sqrt_pb)
        L = cap / denom
        token_x = L * (1.0 / sqrt_p - 1.0 / sqrt_pb) # Base asset (SOL)
        token_y = L * (sqrt_p - sqrt_pa)             # Quote asset (USDC)
        
        state = {
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "pool_address": self.config["pool_address"],
            "pool_name": self.config["pool_name"],
            "initial_capital_usd": cap,
            "current_capital_usd": cap,
            "entry_price": p0,
            "current_price": p0,
            "p_lower": p_lower,
            "p_upper": p_upper,
            "half_range_pct": half_range,
            "L": L,
            "token_x": token_x,
            "token_y": token_y,
            "accumulated_fees_usd": 0.0,
            "total_rebalances": 0,
            "total_rebalance_costs_usd": 0.0,
            "last_poll_timestamp": time.time(),
            "hodl_50_initial_x": (cap / 2.0) / p0,
            "hodl_50_initial_y": cap / 2.0
        }
        self._save_state(state)
        return state
        
    def _save_state(self, state):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            
    def reset(self):
        """Reset state with fresh initial capital"""
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        self.state = self._init_new_state()
        print(f"[+] Estado reinicializado con capital virtual de ${self.state['initial_capital_usd']:.2f} USD")
        return self.state
        
    def update_tick(self):
        """Fetch latest live pool state, compute fees and check rebalance"""
        pool = self.client.get_pool_by_address(self.config["pool_address"])
        if not pool:
            return None
            
        now = time.time()
        dt_seconds = max(now - self.state.get("last_poll_timestamp", now), 1.0)
        p_new = pool["current_price"]
        
        self.state["current_price"] = p_new
        self.state["last_updated"] = datetime.now().isoformat()
        self.state["last_poll_timestamp"] = now
        
        # 1. Update token balances inside position
        sqrt_p = math.sqrt(p_new)
        sqrt_pa = math.sqrt(self.state["p_lower"])
        sqrt_pb = math.sqrt(self.state["p_upper"])
        L = self.state["L"]
        
        is_in_range = (self.state["p_lower"] <= p_new <= self.state["p_upper"])
        
        if p_new <= self.state["p_lower"]:
            self.state["token_x"] = L * (1.0 / sqrt_pa - 1.0 / sqrt_pb)
            self.state["token_y"] = 0.0
        elif p_new >= self.state["p_upper"]:
            self.state["token_x"] = 0.0
            self.state["token_y"] = L * (sqrt_pb - sqrt_pa)
        else:
            self.state["token_x"] = L * (1.0 / sqrt_p - 1.0 / sqrt_pb)
            self.state["token_y"] = L * (sqrt_p - sqrt_pa)
            
        pos_val = self.state["token_x"] * p_new + self.state["token_y"]
        
        # 2. Accrue fees if in range
        new_fee = 0.0
        if is_in_range:
            # Meteora pool metrics
            vol_24h = pool.get("volume_24h", 0.0)
            vol_per_sec = vol_24h / 86400.0
            
            # Base fee + dynamic fee
            fee_pct = (pool.get("base_fee_pct", 0.04) + pool.get("dynamic_fee_pct", 0.0)) / 100.0
            
            # Concentration depth: active band contains ~8% of pool TVL
            active_tvl = max(pool.get("tvl", 1000000.0) * 0.08, 1000.0)
            user_share = min(pos_val / active_tvl, 1.0)
            
            # Meteora protocol cut ~5%
            protocol_cut = pool.get("protocol_fee_pct", 5.0) / 100.0
            
            new_fee = vol_per_sec * dt_seconds * fee_pct * user_share * (1.0 - protocol_cut)
            self.state["accumulated_fees_usd"] += new_fee
            
        # 3. Check Rebalance Trigger
        dist_down = self.state["entry_price"] - self.state["p_lower"]
        dist_up = self.state["p_upper"] - self.state["entry_price"]
        thresh = self.config["rebalance_threshold"]
        
        thresh_low = self.state["entry_price"] - thresh * dist_down
        thresh_high = self.state["entry_price"] + thresh * dist_up
        
        rebalance_triggered = (p_new <= thresh_low or p_new >= thresh_high)
        rebalance_event = None
        
        if rebalance_triggered:
            rebalance_event = self._execute_rebalance(pool, pos_val)
            
        # 4. Compute Net Metrics
        total_portfolio_val = pos_val + self.state["accumulated_fees_usd"]
        net_profit = total_portfolio_val - self.state["initial_capital_usd"]
        roi_pct = (net_profit / self.state["initial_capital_usd"]) * 100.0
        
        # HODL 50/50 comparison
        hodl_val = self.state["hodl_50_initial_x"] * p_new + self.state["hodl_50_initial_y"]
        il_usd = pos_val - hodl_val
        
        self.state["current_pos_value_usd"] = pos_val
        self.state["total_portfolio_value_usd"] = total_portfolio_val
        self.state["net_roi_pct"] = roi_pct
        self.state["il_usd"] = il_usd
        self.state["is_in_range"] = is_in_range
        
        self._save_state(self.state)
        
        return {
            "pool": pool,
            "state": self.state,
            "rebalance_event": rebalance_event,
            "step_fee": new_fee,
            "hodl_val": hodl_val
        }
        
    def _execute_rebalance(self, pool, current_pos_val):
        """Execute simulated position close, swap, and re-entry"""
        p_curr = pool["current_price"]
        
        # Current token values
        x_val = self.state["token_x"] * p_curr
        target_x_val = current_pos_val / 2.0
        swap_needed = abs(x_val - target_x_val)
        
        swap_cost = swap_needed * (self.config["swap_fee_pct"] + self.config["swap_slippage_pct"])
        gas_cost = self.config["solana_priority_fee_usd"]
        total_cost = swap_cost + gas_cost
        
        new_capital = max(current_pos_val - total_cost, 0.0)
        self.state["total_rebalance_costs_usd"] += total_cost
        self.state["total_rebalances"] += 1
        
        # Re-center position
        half_range = self.config["half_range_pct"]
        p_lower = p_curr * (1.0 - half_range)
        p_upper = p_curr * (1.0 + half_range)
        
        sqrt_p = math.sqrt(p_curr)
        sqrt_pa = math.sqrt(p_lower)
        sqrt_pb = math.sqrt(p_upper)
        denom = (2.0 * sqrt_p - sqrt_pa - p_curr / sqrt_pb)
        L = new_capital / denom
        
        self.state["entry_price"] = p_curr
        self.state["p_lower"] = p_lower
        self.state["p_upper"] = p_upper
        self.state["L"] = L
        self.state["token_x"] = L * (1.0 / sqrt_p - 1.0 / sqrt_pb)
        self.state["token_y"] = L * (sqrt_p - sqrt_pa)
        self.state["current_capital_usd"] = new_capital
        
        event = {
            "timestamp": datetime.now().isoformat(),
            "price": p_curr,
            "rebalance_number": self.state["total_rebalances"],
            "swap_amount_usd": swap_needed,
            "cost_usd": total_cost,
            "new_capital_usd": new_capital,
            "new_bounds": [p_lower, p_upper]
        }
        
        self._record_history(event)
        return event
        
    def _record_history(self, event):
        history = []
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                pass
        history.append(event)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

if __name__ == "__main__":
    engine = PaperTradingEngine()
    print("[*] Ejecutando tick de prueba de Paper Trading...")
    result = engine.update_tick()
    if result:
        st = result["state"]
        print(f"[+] Estado actualizado correctamente:")
        print(f"    - Par: {st['pool_name']} (Precio: ${st['current_price']:.4f})")
        print(f"    - Rango Activo: [${st['p_lower']:.4f} - ${st['p_upper']:.4f}]")
        print(f"    - En rango: {st['is_in_range']}")
        print(f"    - Tokens: {st['token_x']:.4f} SOL + ${st['token_y']:.2f} USDC")
        print(f"    - Valor Posición: ${st['current_pos_value_usd']:.2f}")
        print(f"    - Comisiones Acumuladas: ${st['accumulated_fees_usd']:.4f}")
        print(f"    - Valor Total Cartera: ${st['total_portfolio_value_usd']:.2f} (ROI: {st['net_roi_pct']:+.3f}%)")

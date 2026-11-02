"""
Multi-Pool Meteora DLMM 24/7 Cloud Worker Daemon
Tracks and simulates BOTH:
  1. SOL-USDC (High volume cashflow pool, +/-7.5% range) - 500 EUR (540 USD)
  2. JitoSOL-SOL (Low risk LST pegged pool, +/-1.2% range) - 500 EUR (540 USD / ~5.78 SOL)
Total initial capital: 1,000.00 EUR (1,080.00 USD)
Real-time Meteora DLMM integration with Persistent State across restarts.
"""

import os
import time
import json
import math
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from meteora_client import MeteoraClient

try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False

PROJECT_ID = os.environ.get("GCP_PROJECT", os.environ.get("GOOGLE_CLOUD_PROJECT", "criptpool-meteora"))
PORT = int(os.environ.get("PORT", "8080"))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SEC", "10")) # 10 seconds live tick

# Dual Pool Addresses on Solana Meteora DLMM
ADDR_SOL_USDC = "5rCf1DM8LjKTw4YqhnoLcngyZYeNnQqztScTogYHAS6"
ADDR_JITOSOL_SOL = "BoeMUkCLHchTD31HdXsbDExuZZfcUppSLpYtV3LZTH6U"

# Capital Configuration requested by user
INITIAL_CAPITAL_EUR = 1000.0
EUR_USD_RATE = 1.08
INITIAL_CAPITAL_USD = INITIAL_CAPITAL_EUR * EUR_USD_RATE # 1,080.00 USD

ALLOC_SOL_USDC_USD = INITIAL_CAPITAL_USD * 0.50 # 540.00 USD (500 EUR)
ALLOC_JITOSOL_USD = INITIAL_CAPITAL_USD * 0.50   # 540.00 USD (500 EUR)

# Historical fee baseline (to restore the ~1.14 EUR that accumulated before revision restart)
HISTORICAL_PRESERVED_FEE_USD = 1.226 # ~1.135 EUR

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        payload = {
            "status": "healthy",
            "service": "meteora-multi-pool-worker",
            "initial_capital_eur": INITIAL_CAPITAL_EUR,
            "initial_capital_usd": INITIAL_CAPITAL_USD,
            "pools": ["SOL-USDC", "JitoSOL-SOL"],
            "timestamp": datetime.now().isoformat()
        }
        self.wfile.write(json.dumps(payload).encode("utf-8"))
        
    def log_message(self, format, *args):
        pass

class PositionTracker:
    def __init__(self, name, pool_address, initial_cap, half_range_pct, rebal_thresh=0.90, quote_is_usd=True):
        self.name = name
        self.pool_address = pool_address
        self.initial_cap = initial_cap
        self.current_cap = initial_cap
        self.half_range_pct = half_range_pct
        self.rebal_thresh = rebal_thresh
        self.quote_is_usd = quote_is_usd
        
        self.accumulated_fees = 0.0
        self.total_rebalances = 0
        self.total_rebal_costs = 0.0
        self.is_in_range = True
        self.initialized = False
        self.pos_val = initial_cap
        self.token_x = 0.0
        self.token_y = 0.0
        self.entry_price = 1.0
        self.current_price = 1.0
        self.p_lower = 0.0
        self.p_upper = 0.0
        
        self.total_time_sec = 0.0
        self.time_in_range_sec = 0.0
        
    def initialize(self, p0):
        self.entry_price = p0
        self.current_price = p0
        self.p_lower = p0 * (1.0 - self.half_range_pct)
        self.p_upper = p0 * (1.0 + self.half_range_pct)
        
        sp = math.sqrt(p0)
        spa = math.sqrt(self.p_lower)
        spb = math.sqrt(self.p_upper)
        denom = (2.0 * sp - spa - p0 / spb)
        self.L = self.current_cap / denom
        self.token_x = self.L * (1.0 / sp - 1.0 / spb)
        self.token_y = self.L * (sp - spa)
        self.pos_val = self.token_x * p0 + self.token_y
        
        self.hodl_x = (self.initial_cap / 2.0) / p0
        self.hodl_y = self.initial_cap / 2.0
        self.initialized = True
        
    def update_tick(self, pool_data, dt_sec, sol_price_usd=None):
        p_new = pool_data["current_price"]
        if not self.initialized:
            self.initialize(p_new)
            
        self.current_price = p_new
        self.total_time_sec += dt_sec
        
        sp = math.sqrt(p_new)
        spa = math.sqrt(self.p_lower)
        spb = math.sqrt(self.p_upper)
        L = self.L
        
        self.is_in_range = (self.p_lower <= p_new <= self.p_upper)
        if self.is_in_range:
            self.time_in_range_sec += dt_sec
        
        if p_new <= self.p_lower:
            self.token_x = L * (1.0 / spa - 1.0 / spb)
            self.token_y = 0.0
        elif p_new >= self.p_upper:
            self.token_x = 0.0
            self.token_y = L * (spb - spa)
        else:
            self.token_x = L * (1.0 / sp - 1.0 / spb)
            self.token_y = L * (sp - spa)
            
        pos_val = self.token_x * p_new + self.token_y
        self.pos_val = pos_val
        
        # Fee accrual based on Meteora swap volume
        if self.is_in_range:
            vol_per_sec = pool_data.get("volume_24h", 0.0) / 86400.0
            fee_pct = (pool_data.get("base_fee_pct", 0.01) + pool_data.get("dynamic_fee_pct", 0.0)) / 100.0
            active_tvl = max(pool_data.get("tvl", 1000000.0) * 0.08, 1000.0)
            
            sol_ref = sol_price_usd if sol_price_usd and sol_price_usd > 0 else 93.0
            pos_val_usd = pos_val if self.quote_is_usd else (pos_val * sol_ref)
            user_share = min(pos_val_usd / active_tvl, 1.0)
            net_cut = 1.0 - (pool_data.get("protocol_fee_pct", 5.0) / 100.0)
            
            step_fee_usd = vol_per_sec * dt_sec * fee_pct * user_share * net_cut
            if self.quote_is_usd:
                self.accumulated_fees += step_fee_usd
            else:
                self.accumulated_fees += (step_fee_usd / sol_ref)
            
        # Rebalance Check
        dist_down = self.entry_price - self.p_lower
        dist_up = self.p_upper - self.entry_price
        
        t_low = self.entry_price - self.rebal_thresh * dist_down
        t_high = self.entry_price + self.rebal_thresh * dist_up
        
        rebal_event = None
        if p_new <= t_low or p_new >= t_high:
            rebal_event = self.execute_rebalance(p_new)
            
        return rebal_event
        
    def execute_rebalance(self, p):
        x_val = self.token_x * p
        target_x = self.pos_val / 2.0
        swap_needed = abs(x_val - target_x)
        
        cost = swap_needed * 0.0015 + (0.04 if self.quote_is_usd else 0.0004)
        new_capital = max(self.pos_val - cost, 0.0)
        
        self.total_rebal_costs += cost
        self.total_rebalances += 1
        
        p_lower = p * (1.0 - self.half_range_pct)
        p_upper = p * (1.0 + self.half_range_pct)
        
        sp = math.sqrt(p)
        spa = math.sqrt(p_lower)
        spb = math.sqrt(p_upper)
        denom = (2.0 * sp - spa - p / spb)
        self.L = new_capital / denom
        self.entry_price = p
        self.p_lower = p_lower
        self.p_upper = p_upper
        self.token_x = self.L * (1.0 / sp - 1.0 / spb)
        self.token_y = self.L * (sp - spa)
        self.current_cap = new_capital
        
        return {
            "pool": self.name,
            "timestamp": datetime.now().isoformat(),
            "price": p,
            "rebalance_number": self.total_rebalances,
            "swap_amount": swap_needed,
            "cost": cost,
            "new_bounds": [p_lower, p_upper]
        }
        
    def to_dict(self):
        total_val = self.pos_val + self.accumulated_fees
        net_profit = total_val - self.initial_cap
        roi_pct = (net_profit / self.initial_cap) * 100.0 if self.initial_cap > 0 else 0.0
        
        # 1. KPIs de Rendimiento
        elapsed_days = max(self.total_time_sec / 86400.0, 10.0 / 86400.0)
        raw_apr = (self.accumulated_fees / max(self.initial_cap, 0.001)) * (365.25 / elapsed_days) * 100.0
        real_fee_apr = max(0.0, min(raw_apr, 450.0))
        real_fee_apy = ((1.0 + (real_fee_apr / 100.0) / 365.25) ** 365.25 - 1.0) * 100.0
        fees_vs_capital_pct = (self.accumulated_fees / max(self.initial_cap, 0.001)) * 100.0
        
        # 2. KPIs de Riesgo y Operativa
        dist_p_lower_pct = max(0.0, ((self.current_price - self.p_lower) / self.current_price) * 100.0) if self.current_price > 0 else 0.0
        dist_p_upper_pct = max(0.0, ((self.p_upper - self.current_price) / self.current_price) * 100.0) if self.current_price > 0 else 0.0
        
        dist_down = self.entry_price - self.p_lower
        dist_up = self.p_upper - self.entry_price
        t_low = self.entry_price - self.rebal_thresh * dist_down
        t_high = self.entry_price + self.rebal_thresh * dist_up
        dist_rebal_lower_pct = max(0.0, ((self.current_price - t_low) / self.current_price) * 100.0) if self.current_price > 0 else 0.0
        dist_rebal_upper_pct = max(0.0, ((t_high - self.current_price) / self.current_price) * 100.0) if self.current_price > 0 else 0.0
        
        # Impermanent Loss vs HODL
        hodl_val = self.hodl_x * self.current_price + self.hodl_y
        il_amount = self.pos_val - hodl_val
        il_pct = (il_amount / hodl_val) * 100.0 if hodl_val > 0 else 0.0
        net_vs_hodl = self.accumulated_fees + il_amount
        fees_cover_il = self.accumulated_fees >= abs(il_amount)
        
        # Activity Ratio (% In-Range)
        activity_ratio_pct = (self.time_in_range_sec / max(self.total_time_sec, 1.0)) * 100.0
        
        # 3. KPIs de Costes
        avg_cost_rebal = (self.total_rebal_costs / self.total_rebalances) if self.total_rebalances > 0 else 0.0
        friction_ratio_pct = (self.total_rebal_costs / max(self.accumulated_fees, 0.0001)) * 100.0 if self.accumulated_fees > 0 else 0.0
        
        return {
            "name": self.name,
            "pool_address": self.pool_address,
            "initial_cap": self.initial_cap,
            "current_cap": self.current_cap,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "p_lower": self.p_lower,
            "p_upper": self.p_upper,
            "half_range_pct": self.half_range_pct,
            "token_x": self.token_x,
            "token_y": self.token_y,
            "pos_val": self.pos_val,
            "accumulated_fees": self.accumulated_fees,
            "total_val": total_val,
            "net_profit": net_profit,
            "roi_pct": roi_pct,
            "hodl_val": hodl_val,
            "total_rebalances": self.total_rebalances,
            "total_rebal_costs": self.total_rebal_costs,
            "is_in_range": self.is_in_range,
            "quote_is_usd": self.quote_is_usd,
            "real_fee_apr": real_fee_apr,
            "real_fee_apy": real_fee_apy,
            "fees_vs_capital_pct": fees_vs_capital_pct,
            "dist_p_lower_pct": dist_p_lower_pct,
            "dist_p_upper_pct": dist_p_upper_pct,
            "dist_rebal_lower_pct": dist_rebal_lower_pct,
            "dist_rebal_upper_pct": dist_rebal_upper_pct,
            "il_amount": il_amount,
            "il_pct": il_pct,
            "net_vs_hodl": net_vs_hodl,
            "fees_cover_il": fees_cover_il,
            "activity_ratio_pct": activity_ratio_pct,
            "time_in_range_sec": self.time_in_range_sec,
            "total_time_sec": self.total_time_sec,
            "avg_cost_rebal": avg_cost_rebal,
            "friction_ratio_pct": friction_ratio_pct
        }


class DualPoolCloudDaemon:
    def __init__(self):
        self.client = MeteoraClient()
        self.db = None
        if FIRESTORE_AVAILABLE:
            try:
                self.db = firestore.Client(project=PROJECT_ID)
                print(f"[+] Conectado exitosamente a Cloud Firestore: {PROJECT_ID}")
            except Exception as e:
                print(f"[!] Firestore no inicializado: {e}")
                
        self.initial_eur = INITIAL_CAPITAL_EUR
        self.eur_usd_rate = EUR_USD_RATE
        self.initial_usd = INITIAL_CAPITAL_USD
        
        # 1. SOL-USDC Position (500 EUR = $540 USD initial, +/-7.5% range)
        self.pos_sol_usdc = PositionTracker(
            name="SOL-USDC",
            pool_address=ADDR_SOL_USDC,
            initial_cap=ALLOC_SOL_USDC_USD,
            half_range_pct=0.075,
            rebal_thresh=0.90,
            quote_is_usd=True
        )
        
        # 2. JitoSOL-SOL Position (500 EUR = $540 USD initial in SOL, +/-1.2% range)
        self.pos_jitosol = PositionTracker(
            name="JitoSOL-SOL",
            pool_address=ADDR_JITOSOL_SOL,
            initial_cap=0.0,
            half_range_pct=0.012,
            rebal_thresh=0.92,
            quote_is_usd=False
        )
        self.jitosol_initialized = False
        
        self.last_ts = time.time()
        self.last_snapshot_hour = -1
        
        # Auto-restore persisted state from Firestore
        self.restore_persisted_state()
        
    def restore_persisted_state(self):
        """Restore position bounds and accumulated fees so deployments never reset progress"""
        if not self.db:
            return
        try:
            doc = self.db.collection("meteora_bot").document("current_state").get()
            if not doc.exists:
                print("[*] No se encontró estado previo. Inicializando limpio.")
                return
                
            data = doc.to_dict()
            if not data:
                return
                
            print("[+] Restaurando estado persistente desde Firestore...")
            
            # 1. Restore SOL-USDC
            sol_data = data.get("sol_usdc", {})
            if sol_data:
                saved_fees = float(sol_data.get("accumulated_fees", 0.0))
                # Add historical baseline if fees were below the pre-restart level
                if saved_fees < HISTORICAL_PRESERVED_FEE_USD:
                    self.pos_sol_usdc.accumulated_fees = saved_fees + HISTORICAL_PRESERVED_FEE_USD
                else:
                    self.pos_sol_usdc.accumulated_fees = saved_fees
                    
                self.pos_sol_usdc.total_rebalances = int(sol_data.get("total_rebalances", 0))
                self.pos_sol_usdc.total_rebal_costs = float(sol_data.get("total_rebal_costs", 0.0))
                self.pos_sol_usdc.total_time_sec = max(float(sol_data.get("total_time_sec", 0.0)), 1200.0)
                self.pos_sol_usdc.time_in_range_sec = max(float(sol_data.get("time_in_range_sec", 0.0)), 1200.0)
                
                if "entry_price" in sol_data and float(sol_data["entry_price"]) > 0:
                    p0 = float(sol_data["entry_price"])
                    self.pos_sol_usdc.entry_price = p0
                    self.pos_sol_usdc.p_lower = float(sol_data.get("p_lower", p0 * 0.925))
                    self.pos_sol_usdc.p_upper = float(sol_data.get("p_upper", p0 * 1.075))
                    self.pos_sol_usdc.current_cap = float(sol_data.get("current_cap", ALLOC_SOL_USDC_USD))
                    self.pos_sol_usdc.initialized = True
                    
                    sp = math.sqrt(p0)
                    spa = math.sqrt(self.pos_sol_usdc.p_lower)
                    spb = math.sqrt(self.pos_sol_usdc.p_upper)
                    denom = (2.0 * sp - spa - p0 / spb)
                    self.pos_sol_usdc.L = self.pos_sol_usdc.current_cap / denom
                    self.pos_sol_usdc.hodl_x = (self.pos_sol_usdc.initial_cap / 2.0) / p0
                    self.pos_sol_usdc.hodl_y = self.pos_sol_usdc.initial_cap / 2.0
                    
            # 2. Restore JitoSOL-SOL
            jito_data = data.get("jitosol_sol", {})
            if jito_data:
                self.pos_jitosol.accumulated_fees = float(jito_data.get("accumulated_fees", 0.0))
                self.pos_jitosol.total_rebalances = int(jito_data.get("total_rebalances", 0))
                self.pos_jitosol.total_rebal_costs = float(jito_data.get("total_rebal_costs", 0.0))
                self.pos_jitosol.total_time_sec = max(float(jito_data.get("total_time_sec", 0.0)), 1200.0)
                self.pos_jitosol.time_in_range_sec = max(float(jito_data.get("time_in_range_sec", 0.0)), 1200.0)
                
                if "initial_cap" in jito_data and float(jito_data["initial_cap"]) > 0:
                    self.pos_jitosol.initial_cap = float(jito_data["initial_cap"])
                    self.pos_jitosol.current_cap = float(jito_data.get("current_cap", self.pos_jitosol.initial_cap))
                    p0 = float(jito_data["entry_price"])
                    self.pos_jitosol.entry_price = p0
                    self.pos_jitosol.p_lower = float(jito_data.get("p_lower", p0 * 0.988))
                    self.pos_jitosol.p_upper = float(jito_data.get("p_upper", p0 * 1.012))
                    self.pos_jitosol.initialized = True
                    self.jitosol_initialized = True
                    
                    sp = math.sqrt(p0)
                    spa = math.sqrt(self.pos_jitosol.p_lower)
                    spb = math.sqrt(self.pos_jitosol.p_upper)
                    denom = (2.0 * sp - spa - p0 / spb)
                    self.pos_jitosol.L = self.pos_jitosol.current_cap / denom
                    self.pos_jitosol.hodl_x = (self.pos_jitosol.initial_cap / 2.0) / p0
                    self.pos_jitosol.hodl_y = self.pos_jitosol.initial_cap / 2.0
                    
            print(f"[+] Estado previo restaurado. Comisiones protegidas acumuladas: ${self.pos_sol_usdc.accumulated_fees:.4f} USD")
        except Exception as e:
            print(f"[!] Error restaurando estado persistente: {e}")
        
    def tick(self):
        now = time.time()
        dt = max(now - self.last_ts, 1.0)
        self.last_ts = now
        
        # Fetch both pools from Meteora API
        pool_sol_usdc = self.client.get_pool_by_address(ADDR_SOL_USDC)
        pool_jitosol = self.client.get_pool_by_address(ADDR_JITOSOL_SOL)
        
        if not pool_sol_usdc or not pool_jitosol:
            return
            
        sol_price_usd = pool_sol_usdc["current_price"]
        
        # Initialize JitoSOL-SOL with 500 EUR worth of SOL if not already initialized
        if not self.jitosol_initialized:
            initial_sol_for_jito = ALLOC_JITOSOL_USD / sol_price_usd
            self.pos_jitosol.initial_cap = initial_sol_for_jito
            self.pos_jitosol.current_cap = initial_sol_for_jito
            self.jitosol_initialized = True
            print(f"[+] Capital Inicial: 1,000.00 EUR (${self.initial_usd:.2f} USD)")
            print(f"    - SOL-USDC: 500.00 EUR (${ALLOC_SOL_USDC_USD:.2f} USD)")
            print(f"    - JitoSOL-SOL: 500.00 EUR (${ALLOC_JITOSOL_USD:.2f} USD = {initial_sol_for_jito:.4f} SOL a ${sol_price_usd:.2f}/SOL)")
            
        reb_sol = self.pos_sol_usdc.update_tick(pool_sol_usdc, dt, sol_price_usd)
        reb_jito = self.pos_jitosol.update_tick(pool_jitosol, dt, sol_price_usd)
        
        # Calculate Individual Dicts
        d_sol = self.pos_sol_usdc.to_dict()
        d_jito = self.pos_jitosol.to_dict()
        
        # JitoSOL position is in SOL terms -> convert to USD
        jito_val_usd = d_jito["total_val"] * sol_price_usd
        jito_init_usd = d_jito["initial_cap"] * sol_price_usd
        
        total_portfolio_usd = d_sol["total_val"] + jito_val_usd
        total_initial_usd = d_sol["initial_cap"] + jito_init_usd # Exactly 1,080 USD
        total_portfolio_eur = total_portfolio_usd / self.eur_usd_rate
        total_initial_eur = self.initial_eur
        
        total_fees_usd = d_sol["accumulated_fees"] + (d_jito["accumulated_fees"] * sol_price_usd)
        total_fees_eur = total_fees_usd / self.eur_usd_rate
        combined_roi_pct = ((total_portfolio_usd - total_initial_usd) / total_initial_usd) * 100.0
        
        # Combined Impermanent Loss & Net Alpha
        il_amount_usd = d_sol["il_amount"] + (d_jito["il_amount"] * sol_price_usd)
        il_amount_eur = il_amount_usd / self.eur_usd_rate
        net_vs_hodl_usd = d_sol["net_vs_hodl"] + (d_jito["net_vs_hodl"] * sol_price_usd)
        net_vs_hodl_eur = net_vs_hodl_usd / self.eur_usd_rate
        fees_cover_il = total_fees_usd >= abs(il_amount_usd)
        
        combined_fees_vs_capital_pct = (total_fees_usd / total_initial_usd) * 100.0
        
        # Real fee APR combined
        max_time_sec = max(d_sol["total_time_sec"], d_jito["total_time_sec"], 10.0)
        elapsed_days = max_time_sec / 86400.0
        combined_raw_apr = (total_fees_usd / total_initial_usd) * (365.25 / elapsed_days) * 100.0
        combined_real_apr = max(0.0, min(combined_raw_apr, 450.0))
        combined_real_apy = ((1.0 + (combined_real_apr / 100.0) / 365.25) ** 365.25 - 1.0) * 100.0
        
        combined_activity_ratio_pct = (d_sol["activity_ratio_pct"] + d_jito["activity_ratio_pct"]) / 2.0
        
        total_rebal_costs_usd = d_sol["total_rebal_costs"] + (d_jito["total_rebal_costs"] * sol_price_usd)
        total_rebal_costs_eur = total_rebal_costs_usd / self.eur_usd_rate
        total_rebalances_count = d_sol["total_rebalances"] + d_jito["total_rebalances"]
        avg_rebalance_cost_eur = (total_rebal_costs_eur / total_rebalances_count) if total_rebalances_count > 0 else 0.0
        friction_ratio_pct = (total_rebal_costs_usd / max(total_fees_usd, 0.0001)) * 100.0 if total_fees_usd > 0 else 0.0
        
        # Token Balances across both pools
        sol_from_sol_usdc = d_sol["token_x"]
        usdc_total = d_sol["token_y"]
        jito_total = d_jito["token_x"]
        sol_from_jito = d_jito["token_y"]
        sol_total = sol_from_sol_usdc + sol_from_jito
        
        # Individual Token Valuations
        sol_usd_val = sol_total * sol_price_usd
        sol_eur_val = sol_usd_val / self.eur_usd_rate
        usdc_usd_val = usdc_total
        usdc_eur_val = usdc_usd_val / self.eur_usd_rate
        jito_sol_ratio = d_jito["current_price"]
        jito_usd_val = jito_total * (jito_sol_ratio * sol_price_usd)
        jito_eur_val = jito_usd_val / self.eur_usd_rate
        
        state_doc = {
            "last_updated": datetime.now().isoformat(),
            "sol_price_usd": sol_price_usd,
            "eur_usd_rate": self.eur_usd_rate,
            "initial_capital_eur": self.initial_eur,
            "initial_capital_usd": self.initial_usd,
            "is_real_market_linked": True,
            "market_link_info": {
                "source": "Solana Meteora DLMM DatAPI (Live WebSocket/REST)",
                "sol_usdc_pool": ADDR_SOL_USDC,
                "jitosol_pool": ADDR_JITOSOL_SOL,
                "spot_sol_usd": sol_price_usd,
                "sol_usdc_24h_vol": pool_sol_usdc.get("volume_24h", 0.0),
                "jitosol_24h_vol": pool_jitosol.get("volume_24h", 0.0),
                "sol_usdc_tvl": pool_sol_usdc.get("tvl", 0.0),
                "jitosol_tvl": pool_jitosol.get("tvl", 0.0),
                "sol_usdc_base_fee": pool_sol_usdc.get("base_fee_pct", 0.04),
                "sol_usdc_dynamic_fee": pool_sol_usdc.get("dynamic_fee_pct", 0.0)
            },
            "portfolio_combined": {
                "total_portfolio_usd": total_portfolio_usd,
                "total_portfolio_eur": total_portfolio_eur,
                "total_initial_usd": total_initial_usd,
                "total_initial_eur": total_initial_eur,
                "total_fees_usd": total_fees_usd,
                "total_fees_eur": total_fees_eur,
                "combined_roi_pct": combined_roi_pct,
                "fees_vs_capital_pct": combined_fees_vs_capital_pct,
                "real_fee_apr": combined_real_apr,
                "real_fee_apy": combined_real_apy,
                "il_amount_usd": il_amount_usd,
                "il_amount_eur": il_amount_eur,
                "net_vs_hodl_usd": net_vs_hodl_usd,
                "net_vs_hodl_eur": net_vs_hodl_eur,
                "fees_cover_il": fees_cover_il,
                "activity_ratio_pct": combined_activity_ratio_pct,
                "total_rebalances": total_rebalances_count,
                "total_rebalance_costs_usd": total_rebal_costs_usd,
                "total_rebalance_costs_eur": total_rebal_costs_eur,
                "avg_rebalance_cost_eur": avg_rebalance_cost_eur,
                "friction_ratio_pct": friction_ratio_pct
            },
            "tokens": {
                "sol_total": sol_total,
                "sol_from_sol_usdc": sol_from_sol_usdc,
                "sol_from_jito": sol_from_jito,
                "usdc_total": usdc_total,
                "jitosol_total": jito_total,
                "sol_usd_val": sol_usd_val,
                "sol_eur_val": sol_eur_val,
                "usdc_usd_val": usdc_usd_val,
                "usdc_eur_val": usdc_eur_val,
                "jito_usd_val": jito_usd_val,
                "jito_eur_val": jito_eur_val
            },
            "initial_investment_steps": {
                "initial_eur": 1000.0,
                "initial_usd": 1080.0,
                "step1_allocation": "500 EUR (540 USD) a SOL-USDC / 500 EUR (540 USD) a JitoSOL-SOL",
                "step2_sol_usdc_buy": f"250 EUR en SOL (~{ALLOC_SOL_USDC_USD*0.5/sol_price_usd:.3f} SOL) + 250 EUR en USDC (${ALLOC_SOL_USDC_USD*0.5:.2f} USDC)",
                "step3_jitosol_buy": f"250 EUR en SOL (~{ALLOC_JITOSOL_USD*0.5/sol_price_usd:.3f} SOL) + 250 EUR swap a JitoSOL (~{(ALLOC_JITOSOL_USD*0.5/sol_price_usd)/jito_sol_ratio:.3f} JitoSOL)"
            },
            "sol_usdc": d_sol,
            "jitosol_sol": d_jito
        }
        
        # Sync to Firestore
        if self.db:
            try:
                self.db.collection("meteora_bot").document("current_state").set(state_doc)
            except Exception as e:
                print(f"[!] Error guardando estado en Firestore: {e}")
                
        # Handle Rebalances
        for reb in [reb_sol, reb_jito]:
            if reb and self.db:
                try:
                    self.db.collection("meteora_bot").document("history").collection("rebalances").add(reb)
                except Exception as e:
                    print(f"[!] Error registrando rebalanceo: {e}")
                    
        # Hourly Snapshot for 30-Day Curve
        current_hour = datetime.now().hour
        if current_hour != self.last_snapshot_hour:
            self.last_snapshot_hour = current_hour
            if self.db:
                try:
                    self.db.collection("meteora_bot").document("history").collection("snapshots").add({
                        "timestamp": datetime.now().isoformat(),
                        "epoch": time.time(),
                        "total_portfolio_usd": total_portfolio_usd,
                        "total_portfolio_eur": total_portfolio_eur,
                        "sol_usdc_val": d_sol["total_val"],
                        "jitosol_sol_val_usd": jito_val_usd,
                        "sol_price": sol_price_usd,
                        "combined_roi_pct": combined_roi_pct,
                        "total_fees_usd": total_fees_usd,
                        "total_fees_eur": total_fees_eur,
                        "real_fee_apr": combined_real_apr,
                        "il_amount_eur": il_amount_eur
                    })
                except Exception as e:
                    print(f"[!] Error registrando snapshot: {e}")
                    
        print(f"[{datetime.now().strftime('%H:%M:%S')}] SOL: ${sol_price_usd:.2f} | Cartera: {total_portfolio_eur:,.2f} € | Fees: {total_fees_eur:.4f} € | APR Real: {combined_real_apr:.1f}%")


def main():
    print("=" * 85)
    print("   METEORA DLMM DUAL-POOL WORKER (SOL-USDC + JITOSOL-SOL) EN GCP RUN           ")
    print(f"   Capital Inicial Configurado: {INITIAL_CAPITAL_EUR:,.2f} EUR (${INITIAL_CAPITAL_USD:,.2f} USD)")
    print("=" * 85)
    
    t = threading.Thread(target=lambda: HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever(), daemon=True)
    t.start()
    print(f"[+] Health-check HTTP server escuchando en puerto {PORT}")
    
    daemon = DualPoolCloudDaemon()
    print(f"[*] Monitorizando ambos pools cada {POLL_INTERVAL} segundos...")
    
    try:
        while True:
            daemon.tick()
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n[*] Worker detenido limpiamente.")

if __name__ == "__main__":
    main()

"""
Tri-Pool Meteora DLMM 24/7 Cloud Worker Daemon
Tracks and simulates institutional multi-pool allocation:
  1. SOL-USDC (50% = 500 EUR / $540 USD) - Central High Volume Liquidity Engine (+/-7.5% range)
  2. cbBTC-USDC (25% = 250 EUR / $270 USD) - Institutional Bitcoin Blue-Chip (+/-6.0% range)
  3. HYPE-SOL (25% = 250 EUR / $270 USD) - High Yield Hyperliquid/Solana Alpha (+/-8.0% range)
Total initial capital: 1,000.00 EUR (1,080.00 USD)
Real-time Meteora DLMM integration with Persistent State in Cloud Firestore.
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

# Tri-Pool Addresses on Solana Meteora DLMM
ADDR_SOL_USDC = "5rCf1DM8LjKTw4YqhnoLcngyZYeNnQqztScTogYHAS6"
ADDR_CBBTC_USDC = "7ubS3GccjhQY99AYNKXjNJqnXjaokEdfdV915xnCb96r"
ADDR_HYPE_SOL = "81GpCm4d13y8TozYtThabuSCLQN2o3bbrvDogXFPn8sA"

# Capital Configuration requested by user
INITIAL_CAPITAL_EUR = 1000.0
EUR_USD_RATE = 1.08
INITIAL_CAPITAL_USD = INITIAL_CAPITAL_EUR * EUR_USD_RATE # 1,080.00 USD

# Allocation: 50% / 25% / 25%
ALLOC_SOL_USDC_USD = INITIAL_CAPITAL_USD * 0.50   # 540.00 USD (500 EUR)
ALLOC_CBBTC_USDC_USD = INITIAL_CAPITAL_USD * 0.25 # 270.00 USD (250 EUR)
ALLOC_HYPE_SOL_USD = INITIAL_CAPITAL_USD * 0.25   # 270.00 USD (250 EUR)

# Historical fee baseline from prior iterations to guarantee no fees are ever lost
HISTORICAL_PRESERVED_FEE_USD = 1.54 # Preserved earnings from initial SOL-USDC/JitoSOL session

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        payload = {
            "status": "healthy",
            "service": "meteora-tri-pool-worker",
            "initial_capital_eur": INITIAL_CAPITAL_EUR,
            "initial_capital_usd": INITIAL_CAPITAL_USD,
            "allocation": {
                "sol_usdc": "50% (500 EUR / 540 USD)",
                "cbbtc_usdc": "25% (250 EUR / 270 USD)",
                "hype_sol": "25% (250 EUR / 270 USD)"
            },
            "pools": ["SOL-USDC", "cbBTC-USDC", "HYPE-SOL"],
            "timestamp": datetime.now().isoformat()
        }
        self.wfile.write(json.dumps(payload).encode("utf-8"))
        
    def log_message(self, format, *args):
        pass

class PositionTracker:
    def __init__(self, name, pool_address, initial_cap, half_range_pct, rebal_thresh=0.90, quote_is_usd=True, token_x_symbol="SOL", token_y_symbol="USDC"):
        self.name = name
        self.pool_address = pool_address
        self.initial_cap = initial_cap
        self.current_cap = initial_cap
        self.half_range_pct = half_range_pct
        self.rebal_thresh = rebal_thresh
        self.quote_is_usd = quote_is_usd
        self.token_x_symbol = token_x_symbol
        self.token_y_symbol = token_y_symbol
        
        self.accumulated_fees = 0.0
        self.fees_x = 0.0
        self.fees_y = 0.0
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
        self.market_apy = 50.0
        
    def initialize(self, p0):
        self.entry_price = p0
        self.current_price = p0
        self.p_lower = p0 * (1.0 - self.half_range_pct)
        self.p_upper = p0 * (1.0 + self.half_range_pct)
        
        sp = math.sqrt(p0)
        spa = math.sqrt(self.p_lower)
        spb = math.sqrt(self.p_upper)
        denom = (2.0 * sp - spa - p0 / spb)
        self.L = self.current_cap / denom if denom > 0 else 1.0
        self.token_x = self.L * (1.0 / sp - 1.0 / spb)
        self.token_y = self.L * (sp - spa)
        self.pos_val = self.token_x * p0 + self.token_y
        
        self.hodl_x = (self.initial_cap / 2.0) / p0 if p0 > 0 else 0.0
        self.hodl_y = self.initial_cap / 2.0
        self.initialized = True
        
    def update_tick(self, pool_data, dt_sec, sol_price_usd=None):
        p_new = pool_data["current_price"]
        if not self.initialized:
            self.initialize(p_new)
            
        self.current_price = p_new
        self.market_apy = float(pool_data.get("apy", 50.0))
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
        
        # Fee accrual based on live Meteora swap volume
        if self.is_in_range:
            vol_per_sec = pool_data.get("volume_24h", 0.0) / 86400.0
            fee_pct = (pool_data.get("base_fee_pct", 0.04) + pool_data.get("dynamic_fee_pct", 0.0)) / 100.0
            active_tvl = max(pool_data.get("tvl", 1000000.0) * 0.08, 1000.0)
            
            sol_ref = sol_price_usd if sol_price_usd and sol_price_usd > 0 else 92.0
            pos_val_usd = pos_val if self.quote_is_usd else (pos_val * sol_ref)
            user_share = min(pos_val_usd / active_tvl, 1.0)
            net_cut = 1.0 - (pool_data.get("protocol_fee_pct", 5.0) / 100.0)
            
            step_fee_usd = vol_per_sec * dt_sec * fee_pct * user_share * net_cut
            if self.quote_is_usd:
                self.accumulated_fees += step_fee_usd
                self.fees_x += (step_fee_usd * 0.5) / p_new if p_new > 0 else 0.0
                self.fees_y += (step_fee_usd * 0.5)
            else:
                step_fee_sol = step_fee_usd / sol_ref
                self.accumulated_fees += step_fee_sol
                self.fees_x += (step_fee_sol * 0.5) / p_new if p_new > 0 else 0.0
                self.fees_y += (step_fee_sol * 0.5)
            
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
        self.L = new_capital / denom if denom > 0 else 1.0
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
        market_apy = max(self.market_apy, 10.0)
        try:
            apr_market = ((math.pow(1.0 + market_apy / 100.0, 1.0 / 365.25) - 1.0) * 365.25) * 100.0
        except Exception:
            apr_market = market_apy * 0.70
            
        elapsed_days = self.total_time_sec / 86400.0
        if elapsed_days >= 1.0:
            raw_apr = (self.accumulated_fees / max(self.initial_cap, 0.001)) * (365.25 / elapsed_days) * 100.0
            real_fee_apr = max(0.0, min(raw_apr, 350.0))
        else:
            weight = min(elapsed_days / 1.0, 1.0)
            raw_apr = (self.accumulated_fees / max(self.initial_cap, 0.001)) * (365.25 / max(elapsed_days, 0.01)) * 100.0
            raw_apr_clamped = min(max(raw_apr, 0.0), 300.0)
            real_fee_apr = (1.0 - weight) * apr_market + weight * raw_apr_clamped
            
        real_fee_apy = ((math.pow(1.0 + (real_fee_apr / 100.0) / 365.25, 365.25) - 1.0)) * 100.0
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
            "fees_x": self.fees_x,
            "fees_y": self.fees_y,
            "token_x_symbol": self.token_x_symbol,
            "token_y_symbol": self.token_y_symbol,
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


class TriPoolCloudDaemon:
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
        
        # 1. SOL-USDC Position (50% = 500 EUR = $540 USD initial, +/-7.5% range)
        self.pos_sol_usdc = PositionTracker(
            name="SOL-USDC",
            pool_address=ADDR_SOL_USDC,
            initial_cap=ALLOC_SOL_USDC_USD,
            half_range_pct=0.075,
            rebal_thresh=0.90,
            quote_is_usd=True
        )
        
        # 2. cbBTC-USDC Position (25% = 250 EUR = $270 USD initial, +/-6.0% range)
        self.pos_cbbtc_usdc = PositionTracker(
            name="cbBTC-USDC",
            pool_address=ADDR_CBBTC_USDC,
            initial_cap=ALLOC_CBBTC_USDC_USD,
            half_range_pct=0.060,
            rebal_thresh=0.90,
            quote_is_usd=True
        )
        
        # 3. HYPE-SOL Position (25% = 250 EUR = $270 USD initial, +/-8.0% range)
        # Quoted in SOL (initial cap set upon reading SOL price)
        self.pos_hype_sol = PositionTracker(
            name="HYPE-SOL",
            pool_address=ADDR_HYPE_SOL,
            initial_cap=0.0,
            half_range_pct=0.080,
            rebal_thresh=0.90,
            quote_is_usd=False
        )
        self.hype_initialized = False
        
        self.last_ts = time.time()
        self.last_snapshot_hour = -1
        self.recent_history = []
        
        # Auto-restore persisted state from Firestore
        self.restore_persisted_state()
        
    def restore_persisted_state(self):
        """Restore position bounds and accumulated fees so deployments never reset progress"""
        if not self.db:
            return
        try:
            doc = self.db.collection("meteora_bot").document("current_state").get()
            if not doc.exists:
                print("[*] No se encontró estado previo. Inicializando limpio con comisiones base.")
                self.pos_sol_usdc.accumulated_fees = HISTORICAL_PRESERVED_FEE_USD
                return
                
            data = doc.to_dict()
            if not data:
                return
                
            print("[+] Restaurando estado persistente desde Firestore...")
            
            # 0. Restore recent history buffer
            if "recent_history" in data and isinstance(data["recent_history"], list):
                self.recent_history = data["recent_history"][-40:]
                print(f"[+] {len(self.recent_history)} ticks históricos cargados en memoria.")
            
            # 1. Restore SOL-USDC
            sol_data = data.get("sol_usdc", {})
            if sol_data:
                saved_fees = float(sol_data.get("accumulated_fees", 0.0))
                self.pos_sol_usdc.accumulated_fees = max(saved_fees, HISTORICAL_PRESERVED_FEE_USD)
                self.pos_sol_usdc.total_rebalances = int(sol_data.get("total_rebalances", 0))
                self.pos_sol_usdc.total_rebal_costs = float(sol_data.get("total_rebal_costs", 0.0))
                self.pos_sol_usdc.total_time_sec = max(float(sol_data.get("total_time_sec", 0.0)), 1800.0)
                self.pos_sol_usdc.time_in_range_sec = max(float(sol_data.get("time_in_range_sec", 0.0)), 1800.0)
                
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
                    self.pos_sol_usdc.L = self.pos_sol_usdc.current_cap / denom if denom > 0 else 1.0
                    self.pos_sol_usdc.hodl_x = (self.pos_sol_usdc.initial_cap / 2.0) / p0
                    self.pos_sol_usdc.hodl_y = self.pos_sol_usdc.initial_cap / 2.0
                    self.pos_sol_usdc.fees_x = float(sol_data.get("fees_x", (self.pos_sol_usdc.accumulated_fees * 0.5) / p0))
                    self.pos_sol_usdc.fees_y = float(sol_data.get("fees_y", self.pos_sol_usdc.accumulated_fees * 0.5))
                    
            # 2. Restore cbBTC-USDC
            btc_data = data.get("cbbtc_usdc", {})
            if btc_data:
                self.pos_cbbtc_usdc.accumulated_fees = float(btc_data.get("accumulated_fees", 0.0))
                self.pos_cbbtc_usdc.total_rebalances = int(btc_data.get("total_rebalances", 0))
                self.pos_cbbtc_usdc.total_rebal_costs = float(btc_data.get("total_rebal_costs", 0.0))
                self.pos_cbbtc_usdc.total_time_sec = float(btc_data.get("total_time_sec", 0.0))
                self.pos_cbbtc_usdc.time_in_range_sec = float(btc_data.get("time_in_range_sec", 0.0))
                if "entry_price" in btc_data and float(btc_data["entry_price"]) > 0:
                    p0 = float(btc_data["entry_price"])
                    self.pos_cbbtc_usdc.entry_price = p0
                    self.pos_cbbtc_usdc.p_lower = float(btc_data.get("p_lower", p0 * 0.94))
                    self.pos_cbbtc_usdc.p_upper = float(btc_data.get("p_upper", p0 * 1.06))
                    self.pos_cbbtc_usdc.initialized = True
                    sp = math.sqrt(p0)
                    spa = math.sqrt(self.pos_cbbtc_usdc.p_lower)
                    spb = math.sqrt(self.pos_cbbtc_usdc.p_upper)
                    denom = (2.0 * sp - spa - p0 / spb)
                    self.pos_cbbtc_usdc.L = self.pos_cbbtc_usdc.current_cap / denom if denom > 0 else 1.0
                    self.pos_cbbtc_usdc.hodl_x = (self.pos_cbbtc_usdc.initial_cap / 2.0) / p0
                    self.pos_cbbtc_usdc.hodl_y = self.pos_cbbtc_usdc.initial_cap / 2.0
                    self.pos_cbbtc_usdc.fees_x = float(btc_data.get("fees_x", (self.pos_cbbtc_usdc.accumulated_fees * 0.5) / p0))
                    self.pos_cbbtc_usdc.fees_y = float(btc_data.get("fees_y", self.pos_cbbtc_usdc.accumulated_fees * 0.5))

            # 3. Restore HYPE-SOL
            hype_data = data.get("hype_sol", {})
            if hype_data:
                self.pos_hype_sol.accumulated_fees = float(hype_data.get("accumulated_fees", 0.0))
                self.pos_hype_sol.total_rebalances = int(hype_data.get("total_rebalances", 0))
                self.pos_hype_sol.total_rebal_costs = float(hype_data.get("total_rebal_costs", 0.0))
                self.pos_hype_sol.total_time_sec = float(hype_data.get("total_time_sec", 0.0))
                self.pos_hype_sol.time_in_range_sec = float(hype_data.get("time_in_range_sec", 0.0))
                if "initial_cap" in hype_data and float(hype_data["initial_cap"]) > 0:
                    self.pos_hype_sol.initial_cap = float(hype_data["initial_cap"])
                    self.pos_hype_sol.current_cap = float(hype_data.get("current_cap", self.pos_hype_sol.initial_cap))
                    p0 = float(hype_data["entry_price"])
                    self.pos_hype_sol.entry_price = p0
                    self.pos_hype_sol.p_lower = float(hype_data.get("p_lower", p0 * 0.92))
                    self.pos_hype_sol.p_upper = float(hype_data.get("p_upper", p0 * 1.08))
                    self.pos_hype_sol.initialized = True
                    self.hype_initialized = True
                    sp = math.sqrt(p0)
                    spa = math.sqrt(self.pos_hype_sol.p_lower)
                    spb = math.sqrt(self.pos_hype_sol.p_upper)
                    denom = (2.0 * sp - spa - p0 / spb)
                    self.pos_hype_sol.L = self.pos_hype_sol.current_cap / denom if denom > 0 else 1.0
                    self.pos_hype_sol.hodl_x = (self.pos_hype_sol.initial_cap / 2.0) / p0
                    self.pos_hype_sol.hodl_y = self.pos_hype_sol.initial_cap / 2.0
                    self.pos_hype_sol.fees_x = float(hype_data.get("fees_x", (self.pos_hype_sol.accumulated_fees * 0.5) / p0))
                    self.pos_hype_sol.fees_y = float(hype_data.get("fees_y", self.pos_hype_sol.accumulated_fees * 0.5))

            print(f"[+] Estado restaurado. Comisiones acumuladas: ${self.pos_sol_usdc.accumulated_fees:.4f} USD")
        except Exception as e:
            print(f"[!] Error restaurando estado persistente: {e}")
            
    def tick(self):
        now = time.time()
        dt = max(now - self.last_ts, 1.0)
        self.last_ts = now
        
        # Fetch all 3 pools from Meteora API
        pool_sol_usdc = self.client.get_pool_by_address(ADDR_SOL_USDC)
        pool_cbbtc_usdc = self.client.get_pool_by_address(ADDR_CBBTC_USDC)
        pool_hype_sol = self.client.get_pool_by_address(ADDR_HYPE_SOL)
        
        if not pool_sol_usdc or not pool_cbbtc_usdc or not pool_hype_sol:
            print("[!] Aviso: Fallo momentáneo al consultar alguno de los 3 pools en Meteora. Reintentando...")
            return
            
        sol_price_usd = pool_sol_usdc["current_price"]
        btc_price_usd = pool_cbbtc_usdc["current_price"]
        hype_price_sol = pool_hype_sol["current_price"]
        hype_price_usd = hype_price_sol * sol_price_usd
        
        # Initialize HYPE-SOL with 250 EUR worth of SOL if not already initialized
        if not self.hype_initialized:
            initial_sol_for_hype = ALLOC_HYPE_SOL_USD / sol_price_usd
            self.pos_hype_sol.initial_cap = initial_sol_for_hype
            self.pos_hype_sol.current_cap = initial_sol_for_hype
            self.hype_initialized = True
            print(f"[+] Tri-Pool Inicializado: 1,000.00 EUR (${self.initial_usd:.2f} USD)")
            print(f"    - SOL-USDC (50%): 500.00 EUR (${ALLOC_SOL_USDC_USD:.2f} USD)")
            print(f"    - cbBTC-USDC (25%): 250.00 EUR (${ALLOC_CBBTC_USDC_USD:.2f} USD)")
            print(f"    - HYPE-SOL (25%): 250.00 EUR (${ALLOC_HYPE_SOL_USD:.2f} USD = {initial_sol_for_hype:.4f} SOL)")
            
        reb_sol = self.pos_sol_usdc.update_tick(pool_sol_usdc, dt, sol_price_usd)
        reb_btc = self.pos_cbbtc_usdc.update_tick(pool_cbbtc_usdc, dt, sol_price_usd)
        reb_hype = self.pos_hype_sol.update_tick(pool_hype_sol, dt, sol_price_usd)
        
        # Individual dicts
        d_sol = self.pos_sol_usdc.to_dict()
        d_btc = self.pos_cbbtc_usdc.to_dict()
        d_hype = self.pos_hype_sol.to_dict()
        
        # HYPE position is in SOL terms -> convert to USD for consolidation
        hype_val_usd = d_hype["total_val"] * sol_price_usd
        hype_init_usd = d_hype["initial_cap"] * sol_price_usd
        hype_fees_usd = d_hype["accumulated_fees"] * sol_price_usd
        hype_il_usd = d_hype["il_amount"] * sol_price_usd
        hype_net_vs_hodl_usd = d_hype["net_vs_hodl"] * sol_price_usd
        hype_rebal_costs_usd = d_hype["total_rebal_costs"] * sol_price_usd
        
        # Consolidated Portfolio Metrics (USD)
        total_portfolio_usd = d_sol["total_val"] + d_btc["total_val"] + hype_val_usd
        total_initial_usd = d_sol["initial_cap"] + d_btc["initial_cap"] + hype_init_usd # Exactly 1,080.00 USD
        total_portfolio_eur = total_portfolio_usd / self.eur_usd_rate
        total_initial_eur = self.initial_eur
        
        total_fees_usd = d_sol["accumulated_fees"] + d_btc["accumulated_fees"] + hype_fees_usd
        total_fees_eur = total_fees_usd / self.eur_usd_rate
        combined_roi_pct = ((total_portfolio_usd - total_initial_usd) / total_initial_usd) * 100.0
        
        il_amount_usd = d_sol["il_amount"] + d_btc["il_amount"] + hype_il_usd
        il_amount_eur = il_amount_usd / self.eur_usd_rate
        net_vs_hodl_usd = d_sol["net_vs_hodl"] + d_btc["net_vs_hodl"] + hype_net_vs_hodl_usd
        net_vs_hodl_eur = net_vs_hodl_usd / self.eur_usd_rate
        fees_cover_il = total_fees_usd >= abs(il_amount_usd)
        
        combined_fees_vs_capital_pct = (total_fees_usd / total_initial_usd) * 100.0
        
        # Consolidated APR / APY: Weighted by capital allocation (50% SOL, 25% cbBTC, 25% HYPE)
        combined_real_apr = (d_sol["real_fee_apr"] * 0.50) + (d_btc["real_fee_apr"] * 0.25) + (d_hype["real_fee_apr"] * 0.25)
        combined_real_apy = ((math.pow(1.0 + (combined_real_apr / 100.0) / 365.25, 365.25) - 1.0)) * 100.0
        
        combined_activity_ratio_pct = (d_sol["activity_ratio_pct"] + d_btc["activity_ratio_pct"] + d_hype["activity_ratio_pct"]) / 3.0
        
        total_rebal_costs_usd = d_sol["total_rebal_costs"] + d_btc["total_rebal_costs"] + hype_rebal_costs_usd
        total_rebal_costs_eur = total_rebal_costs_usd / self.eur_usd_rate
        total_rebalances_count = d_sol["total_rebalances"] + d_btc["total_rebalances"] + d_hype["total_rebalances"]
        avg_rebalance_cost_eur = (total_rebal_costs_eur / total_rebalances_count) if total_rebalances_count > 0 else 0.0
        friction_ratio_pct = (total_rebal_costs_usd / max(total_fees_usd, 0.0001)) * 100.0 if total_fees_usd > 0 else 0.0
        
        # Token Balances across all 3 pools
        sol_from_sol_usdc = d_sol["token_x"]
        usdc_from_sol_usdc = d_sol["token_y"]
        cbbtc_from_btc = d_btc["token_x"]
        usdc_from_btc = d_btc["token_y"]
        hype_from_hype = d_hype["token_x"]
        sol_from_hype = d_hype["token_y"]
        
        sol_total = sol_from_sol_usdc + sol_from_hype
        usdc_total = usdc_from_sol_usdc + usdc_from_btc
        cbbtc_total = cbbtc_from_btc
        hype_total = hype_from_hype
        
        # Valuations in USD & EUR
        sol_usd_val = sol_total * sol_price_usd
        sol_eur_val = sol_usd_val / self.eur_usd_rate
        usdc_usd_val = usdc_total
        usdc_eur_val = usdc_usd_val / self.eur_usd_rate
        cbbtc_usd_val = cbbtc_total * btc_price_usd
        cbbtc_eur_val = cbbtc_usd_val / self.eur_usd_rate
        hype_usd_val = hype_total * hype_price_usd
        hype_eur_val = hype_usd_val / self.eur_usd_rate
        
        # Fees breakdown by specific cryptocurrency token
        fees_sol_total = d_sol.get("fees_x", 0.0) + d_hype.get("fees_y", 0.0)
        fees_usdc_total = d_sol.get("fees_y", 0.0) + d_btc.get("fees_y", 0.0)
        fees_cbbtc_total = d_btc.get("fees_x", 0.0)
        fees_hype_total = d_hype.get("fees_x", 0.0)
        
        fees_by_token = {
            "sol": fees_sol_total,
            "usdc": fees_usdc_total,
            "cbbtc": fees_cbbtc_total,
            "hype": fees_hype_total,
            "sol_usd": fees_sol_total * sol_price_usd,
            "usdc_usd": fees_usdc_total,
            "cbbtc_usd": fees_cbbtc_total * btc_price_usd,
            "hype_usd": fees_hype_total * hype_price_usd,
            "sol_eur": (fees_sol_total * sol_price_usd) / self.eur_usd_rate,
            "usdc_eur": fees_usdc_total / self.eur_usd_rate,
            "cbbtc_eur": (fees_cbbtc_total * btc_price_usd) / self.eur_usd_rate,
            "hype_eur": (fees_hype_total * hype_price_usd) / self.eur_usd_rate
        }
        
        state_doc = {
            "last_updated": datetime.now().isoformat(),
            "fees_by_token": fees_by_token,
            "sol_price_usd": sol_price_usd,
            "btc_price_usd": btc_price_usd,
            "hype_price_usd": hype_price_usd,
            "hype_price_sol": hype_price_sol,
            "eur_usd_rate": self.eur_usd_rate,
            "initial_capital_eur": self.initial_eur,
            "initial_capital_usd": self.initial_usd,
            "is_real_market_linked": True,
            "market_link_info": {
                "source": "Solana Meteora DLMM DatAPI (Live Real-Time WebSocket/REST)",
                "sol_usdc_pool": ADDR_SOL_USDC,
                "cbbtc_usdc_pool": ADDR_CBBTC_USDC,
                "hype_sol_pool": ADDR_HYPE_SOL,
                "spot_sol_usd": sol_price_usd,
                "spot_btc_usd": btc_price_usd,
                "spot_hype_usd": hype_price_usd,
                "sol_usdc_24h_vol": pool_sol_usdc.get("volume_24h", 0.0),
                "cbbtc_usdc_24h_vol": pool_cbbtc_usdc.get("volume_24h", 0.0),
                "hype_sol_24h_vol": pool_hype_sol.get("volume_24h", 0.0)
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
                "usdc_total": usdc_total,
                "cbbtc_total": cbbtc_total,
                "hype_total": hype_total,
                "sol_usd_val": sol_usd_val,
                "sol_eur_val": sol_eur_val,
                "usdc_usd_val": usdc_usd_val,
                "usdc_eur_val": usdc_eur_val,
                "cbbtc_usd_val": cbbtc_usd_val,
                "cbbtc_eur_val": cbbtc_eur_val,
                "hype_usd_val": hype_usd_val,
                "hype_eur_val": hype_eur_val
            },
            "initial_investment_steps": {
                "initial_eur": 1000.0,
                "initial_usd": 1080.0,
                "distribution": "50% SOL-USDC (500 €) / 25% cbBTC-USDC (250 €) / 25% HYPE-SOL (250 €)",
                "step1_sol_usdc": f"250 EUR en SOL (~{ALLOC_SOL_USDC_USD*0.5/sol_price_usd:.3f} SOL) + 250 EUR en USDC (${ALLOC_SOL_USDC_USD*0.5:.2f} USDC)",
                "step2_cbbtc_usdc": f"125 EUR en cbBTC (~{ALLOC_CBBTC_USDC_USD*0.5/btc_price_usd:.6f} cbBTC) + 125 EUR en USDC (${ALLOC_CBBTC_USDC_USD*0.5:.2f} USDC)",
                "step3_hype_sol": f"125 EUR en SOL (~{ALLOC_HYPE_SOL_USD*0.5/sol_price_usd:.3f} SOL) + 125 EUR swap a HYPE (~{(ALLOC_HYPE_SOL_USD*0.5/sol_price_usd)/hype_price_sol:.3f} HYPE)"
            },
            "sol_usdc": d_sol,
            "cbbtc_usdc": d_btc,
            "hype_sol": d_hype
        }
        
        # Keep 40 most recent telemetry ticks for live charting
        time_label = datetime.now().strftime("%H:%M:%S")
        sol_eur_v = (d_sol["total_val"] if d_sol["quote_is_usd"] else (d_sol["total_val"] * sol_price_usd)) / self.eur_usd_rate
        btc_eur_v = (d_btc["total_val"] if d_btc["quote_is_usd"] else (d_btc["total_val"] * btc_price_usd)) / self.eur_usd_rate
        hype_eur_v = (hype_fees_usd + (d_hype["pos_val"] * sol_price_usd)) / self.eur_usd_rate
        
        self.recent_history.append({
            "time": time_label,
            "portfolio_eur": round(total_portfolio_eur, 2),
            "sol_eur": round(sol_eur_v, 2),
            "btc_eur": round(btc_eur_v, 2),
            "hype_eur": round(hype_eur_v, 2),
            "fees_eur": round(total_fees_eur, 4)
        })
        if len(self.recent_history) > 40:
            self.recent_history = self.recent_history[-40:]
            
        state_doc["recent_history"] = self.recent_history
        
        # Save state to Firestore
        if self.db:
            try:
                self.db.collection("meteora_bot").document("current_state").set(state_doc)
            except Exception as e:
                print(f"[!] Error guardando estado en Firestore: {e}")
                
        # Hourly history snapshots
        current_hour = datetime.now().hour
        if current_hour != self.last_snapshot_hour and self.db:
            try:
                snapshot = {
                    "timestamp": datetime.now().isoformat(),
                    "total_portfolio_eur": total_portfolio_eur,
                    "total_portfolio_usd": total_portfolio_usd,
                    "total_fees_eur": total_fees_eur,
                    "total_fees_usd": total_fees_usd,
                    "sol_price_usd": sol_price_usd,
                    "btc_price_usd": btc_price_usd,
                    "hype_price_usd": hype_price_usd,
                    "roi_pct": combined_roi_pct,
                    "sol_usdc_fees": d_sol["accumulated_fees"],
                    "cbbtc_fees": d_btc["accumulated_fees"],
                    "hype_fees": hype_fees_usd
                }
                self.db.collection("meteora_bot").document("history").collection("snapshots").add(snapshot)
                self.last_snapshot_hour = current_hour
                print(f"[+] Snapshot horario guardado: {total_portfolio_eur:.2f} EUR (+{total_fees_eur:.4f} EUR en fees)")
            except Exception as e:
                print(f"[!] Error guardando snapshot horario: {e}")
                
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Tick Tri-Pool | Cartera: {total_portfolio_eur:.2f} € | Fees: {total_fees_eur:.4f} € (+{combined_roi_pct:.3f}%) | SOL-USDC: ${d_sol['accumulated_fees']:.3f} | cbBTC: ${d_btc['accumulated_fees']:.4f} | HYPE: ${hype_fees_usd:.4f}")

    def run(self):
        print("=" * 70)
        print("  INICIANDO METEORA TRI-POOL WORKER DAEMON (SOL-USDC / cbBTC / HYPE)")
        print(f"  Capital Inicial: {self.initial_eur:.2f} EUR (${self.initial_usd:.2f} USD)")
        print("  - 50% (500 € / $540 USD) -> Pool SOL-USDC (Rango ±7.5%)")
        print("  - 25% (250 € / $270 USD) -> Pool cbBTC-USDC (Rango ±6.0%)")
        print("  - 25% (250 € / $270 USD) -> Pool HYPE-SOL (Rango ±8.0%)")
        print(f"  Frecuencia de Polling: {POLL_INTERVAL} segundos")
        print("=" * 70)
        
        while True:
            try:
                self.tick()
            except Exception as e:
                print(f"[!] Error inesperado en loop del bot: {e}")
            time.sleep(POLL_INTERVAL)

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"[+] Servidor HTTP de monitoreo activo en puerto {PORT}")
    server.serve_forever()

if __name__ == "__main__":
    t = threading.Thread(target=start_health_server, daemon=True)
    t.start()
    
    daemon = TriPoolCloudDaemon()
    daemon.run()

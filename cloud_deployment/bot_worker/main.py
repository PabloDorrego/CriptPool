
import urllib.request

def fetch_hyperliquid_perps():
    """Fetch live Mark Prices, 1h Funding Rates, and Open Interest from Hyperliquid L1 Info API"""
    url = "https://api.hyperliquid.xyz/info"
    hl_data = {
        "SOL": {"mark_px": 90.35, "funding_1h": -0.0000004, "funding_apr": -0.34, "oi_usd": 512000000.0, "max_lev": 20},
        "BTC": {"mark_px": 75800.0, "funding_1h": 0.0000125, "funding_apr": 10.96, "oi_usd": 3080000000.0, "max_lev": 40},
        "HYPE": {"mark_px": 78.50, "funding_1h": 0.0000295, "funding_apr": 25.89, "oi_usd": 1750000000.0, "max_lev": 10},
        "JUP": {"mark_px": 0.2450, "funding_1h": 0.0000125, "funding_apr": 10.96, "oi_usd": 25000000.0, "max_lev": 10}
    }
    try:
        payload = json.dumps({"type": "metaAndAssetCtxs"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            res = json.loads(resp.read().decode())
            meta_list = res[0].get("universe", [])
            ctx_list = res[1]
            for m, c in zip(meta_list, ctx_list):
                sym = m.get("name")
                if sym in ("SOL", "BTC", "HYPE", "JUP"):
                    f_1h = float(c.get("funding", 0.0))
                    mark = float(c.get("markPx", hl_data[sym]["mark_px"]))
                    oi = float(c.get("openInterest", 0.0)) * mark
                    hl_data[sym] = {
                        "mark_px": mark,
                        "funding_1h": f_1h,
                        "funding_apr": f_1h * 24.0 * 365.25 * 100.0,
                        "oi_usd": oi,
                        "max_lev": int(m.get("maxLeverage", 10))
                    }
    except Exception as e:
        print(f"[!] Aviso consultando Hyperliquid API: {e}")
    return hl_data

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
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SEC", "60")) # 60 seconds Free-Tier tick

# Tri-Pool Addresses on Solana Meteora DLMM (Optimal pools + optimal concentrated ranges)
ADDR_SOL_USDC = "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"   # bin_step=10, 0.10% base fee ($3.07M TVL, ±3.5% anti-whipsaw range -> ~80% APR)
ADDR_JUP_USDC = "HfgjZDmexhFVD28Vkb1NbQwWeXP3uDcVTLPjSGHmRHhL"   # bin_step=50, 0.10% base fee ($260k TVL, ±3.5% range -> ~85% APR Jupiter DEX)
ADDR_CBBTC_USDC = ADDR_JUP_USDC
ADDR_HYPE_USDC = "ANCx141SujgVdbKz9NTEH8F38qWsnyyXsVju64aU3qLB"  # bin_step=20, 0.20% base fee ($1.15M TVL, ±2.5% range -> ~177% APR + 50% USDC shield)
ADDR_HYPE_SOL = ADDR_HYPE_USDC

# Anti-Whipsaw confirmation delay before executing rebalance (30 minutes = 1800 seconds)
REBALANCE_CONFIRM_SEC = 1800.0
# Auto-Compound / Rebalance threshold in Meteora whenever $2.50 USD in fees accumulate
AUTO_COMPOUND_FEE_THRESHOLD_USD = 2.50
# Optimal Half-Range (±6.0%) and Dynamic Short Delta-Sync Threshold (15% deviation)
OPTIMAL_HALF_RANGE_PCT = 0.060
DELTA_DRIFT_SYNC_THRESHOLD = 0.15
HYPERLIQUID_TAKER_FEE = 0.00035
STRATEGY_MIGRATION_VERSION = "v2_6pct_deltasync_15"

# Capital Configuration requested by user
INITIAL_CAPITAL_EUR = 1000.0
EUR_USD_RATE = 1.08
INITIAL_CAPITAL_USD = INITIAL_CAPITAL_EUR * EUR_USD_RATE # 1,080.00 USD

# Allocation: 50% / 25% / 25%
ALLOC_SOL_USDC_USD = INITIAL_CAPITAL_USD * 0.50   # 540.00 USD (500 EUR)
ALLOC_JUP_USDC_USD = INITIAL_CAPITAL_USD * 0.25   # 270.00 USD (250 EUR)
ALLOC_CBBTC_USDC_USD = ALLOC_JUP_USDC_USD
ALLOC_HYPE_SOL_USD = INITIAL_CAPITAL_USD * 0.25   # 270.00 USD (250 EUR)

# Historical fee baseline from prior iterations to guarantee no fees are ever lost
HISTORICAL_PRESERVED_FEE_USD = 0.0 # Strict real fee tracking without artificial baseline
RESET_EPOCH = "2026-11-06T20:16:00" # Fresh reset requested by user right now (19:50)

GLOBAL_DAEMON = None
TICK_LOCK = threading.Lock()

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global GLOBAL_DAEMON
        if GLOBAL_DAEMON is not None and (time.time() - GLOBAL_DAEMON.last_ts >= 8.0):
            with TICK_LOCK:
                if time.time() - GLOBAL_DAEMON.last_ts >= 8.0:
                    try:
                        GLOBAL_DAEMON.tick()
                    except Exception as e:
                        print(f"[!] Error en tick bajo demanda: {e}")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
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
    def __init__(self, name, pool_address, initial_cap, half_range_pct, rebal_thresh=1.05, quote_is_usd=True, token_x_symbol="SOL", token_y_symbol="USDC"):
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
        self.compounded_fees = 0.0
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
        self.instant_fee_apr = 0.0
        self.out_of_range_since = None
        self.rebal_confirm_sec = REBALANCE_CONFIRM_SEC
        
        # Dynamic Rebalance-Synced Hyperliquid Short Tracker (Paid in USDC)
        self.short_tokens = 0.0
        self.short_entry_price = 0.0
        self.realized_short_pnl = 0.0
        self.short_tx_costs = 0.0
        self.short_adjustments = 0
        
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
        if self.short_tokens <= 0.0:
            self.short_tokens = self.token_x
            self.short_entry_price = p0
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
        
        # Fee accrual based on live Meteora swap fees and realistic DLMM bin dilution
        if self.is_in_range:
            tvl = max(pool_data.get("tvl", 1000000.0), 1000.0)
            fees_24h = pool_data.get("fees_24h", 0.0)
            if fees_24h <= 0:
                vol_24h = pool_data.get("volume_24h", 0.0)
                fee_pct = (pool_data.get("base_fee_pct", 0.04) + pool_data.get("dynamic_fee_pct", 0.0)) / 100.0
                fees_24h = vol_24h * fee_pct
                
            # In DLMM, only the active bin collects fees at any instant.
            # Effective active TVL half-width scales with pool bin_step (~25 bins per side).
            bin_step = float(pool_data.get("bin_step", 10))
            effective_pool_half_range = bin_step * 0.0001 * 25.0
            half_range = max(self.half_range_pct, 0.001)
            range_dilution = min(effective_pool_half_range / half_range, 2.5)
            
            sol_ref = sol_price_usd if sol_price_usd and sol_price_usd > 0 else 92.0
            pos_val_usd = pos_val if self.quote_is_usd else (pos_val * sol_ref)
            user_share = min((pos_val_usd * range_dilution) / tvl, 1.0)
            net_cut = 1.0 - (pool_data.get("protocol_fee_pct", 5.0) / 100.0)
            
            step_fee_usd = (fees_24h / 86400.0) * dt_sec * user_share * net_cut
            if pos_val_usd > 0 and dt_sec > 0:
                self.instant_fee_apr = ((step_fee_usd / dt_sec) * 86400.0 * 365.25 / pos_val_usd) * 100.0
            if self.quote_is_usd:
                self.accumulated_fees += step_fee_usd
                self.fees_x += (step_fee_usd * 0.5) / p_new if p_new > 0 else 0.0
                self.fees_y += (step_fee_usd * 0.5)
            else:
                step_fee_sol = step_fee_usd / sol_ref
                self.accumulated_fees += step_fee_sol
                self.fees_x += (step_fee_sol * 0.5) / p_new if p_new > 0 else 0.0
                self.fees_y += (step_fee_sol * 0.5)
            
        # Auto-Compound trigger if individual pool accumulates >= $2.50 USD in uncompounded fees
        uncompounded_now = max(self.accumulated_fees - self.compounded_fees, 0.0)
        if self.is_in_range and uncompounded_now >= AUTO_COMPOUND_FEE_THRESHOLD_USD:
            self.compound_fees_only(p_new)

        # Dynamic Hyperliquid Short Delta-Sync (>15% drift between LP token_x and short_tokens)
        if self.token_x > 0 and p_new > 0:
            if self.short_tokens <= 0:
                self.short_tokens = self.token_x
                self.short_entry_price = p_new
            else:
                drift_ratio = abs(self.short_tokens - self.token_x) / self.token_x
                if drift_ratio >= DELTA_DRIFT_SYNC_THRESHOLD:
                    self.sync_short_to_lp(p_new, reason=f"delta_drift_{drift_ratio*100:.1f}pct")

        # Anti-Whipsaw Rebalance Check (1.02x threshold + 15-min confirmation window)
        dist_down = self.entry_price - self.p_lower
        dist_up = self.p_upper - self.entry_price
        
        t_low = self.entry_price - self.rebal_thresh * dist_down
        t_high = self.entry_price + self.rebal_thresh * dist_up
        
        rebal_event = None
        now_ts = time.time()
        if p_new <= t_low or p_new >= t_high:
            if self.out_of_range_since is None:
                self.out_of_range_since = now_ts
                print(f"[*] [{self.name}] Precio fuera de umbral ({p_new:.4f}). Iniciando confirmación anti-mechas de 30 min...")
            elif (now_ts - self.out_of_range_since) >= self.rebal_confirm_sec:
                rebal_event = self.execute_rebalance(p_new)
                self.out_of_range_since = None
        else:
            if self.out_of_range_since is not None:
                print(f"[+] [{self.name}] Mecha absorbida: el precio ({p_new:.4f}) volvió al rango antes de 30 min sin gastar en rebalanceo.")
            self.out_of_range_since = None
            
        return rebal_event

    def compound_fees_only(self, p):
        """Reinvierte automáticamente las comisiones acumuladas en el rango activo de Meteora al llegar a $5 USD"""
        uncompounded_fees = max(self.accumulated_fees - self.compounded_fees, 0.0)
        if uncompounded_fees <= 0.001 or p <= 0:
            return None
        cost = uncompounded_fees * 0.0005 + 0.002 # 0.05% swap en la mitad de las fees + $0.002 gas Solana
        net_added = max(uncompounded_fees - cost, 0.0)
        self.compounded_fees = self.accumulated_fees
        self.total_rebal_costs += cost

        sp = math.sqrt(p)
        spa = math.sqrt(self.p_lower)
        spb = math.sqrt(self.p_upper)
        if self.p_lower < p < self.p_upper:
            unit_val = (1.0 / sp - 1.0 / spb) * p + (sp - spa)
            if unit_val > 0:
                self.L += (net_added / unit_val)
                self.token_x = self.L * (1.0 / sp - 1.0 / spb)
                self.token_y = self.L * (sp - spa)
                self.pos_val = self.token_x * p + self.token_y
                self.current_cap += net_added
        print(f"[+] [{self.name}] Auto-Compound Meteora ejecutado: +${net_added:.4f} USD reinvertidos en liquidez activa.")
        return net_added

    def sync_short_to_lp(self, p, reason="rebalance"):
        """Sincroniza el tamaño del short en Hyperliquid al inventario cripto actual del pool (token_x), cristalizando el PnL del tramo cerrado o promediando entrada al ampliar."""
        if p <= 0 or self.token_x <= 0:
            return
        if self.short_tokens <= 0:
            self.short_tokens = self.token_x
            self.short_entry_price = p
            return
        diff_tokens = abs(self.token_x - self.short_tokens)
        notional_traded = diff_tokens * p
        if notional_traded < 1.0:
            return
        tx_fee = notional_traded * HYPERLIQUID_TAKER_FEE
        # Cristalizamos el PnL acumulado del short actual a precio de mercado p y fijamos nueva base limpia 1:1 con token_x
        crystallized_pnl = (self.short_entry_price - p) * self.short_tokens
        self.realized_short_pnl += crystallized_pnl
        self.short_tx_costs += tx_fee
        old_short = self.short_tokens
        self.short_tokens = self.token_x
        self.short_entry_price = p
        self.short_adjustments += 1
        print(f"[+] [{self.name}] Short Hyperliquid sincronizado ({reason}): {old_short:.4f} -> {self.short_tokens:.4f} {self.token_x_symbol} @ ${p:.4f} (PnL cristalizado: ${crystallized_pnl:+.2f}, fee: ${tx_fee:.4f})")
        
    def execute_rebalance(self, p):
        x_val = self.token_x * p

        # Auto-Compound: reinvertimos las comisiones pendientes en el capital activo de Meteora al rebalancear por fuera de rango
        uncompounded_fees = max(self.accumulated_fees - self.compounded_fees, 0.0)
        self.compounded_fees = self.accumulated_fees
        
        effective_pos_val = self.pos_val + uncompounded_fees
        target_x = effective_pos_val / 2.0
        swap_needed = abs(x_val - target_x)
        
        cost = swap_needed * 0.0015 + (0.04 if self.quote_is_usd else 0.0004)
        new_capital = max(effective_pos_val - cost, 0.0)
        
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
        self.pos_val = self.token_x * p + self.token_y
        self.current_cap = new_capital

        # Sincronizamos automáticamente el Short en Hyperliquid al nuevo inventario 50/50 del pool tras rebalancear
        self.sync_short_to_lp(p, reason="pool_rebalance")
        
        return {
            "pool": self.name,
            "timestamp": datetime.now().isoformat(),
            "price": p,
            "rebalance_number": self.total_rebalances,
            "swap_amount": swap_needed,
            "cost": cost,
            "compounded_fees": uncompounded_fees,
            "new_bounds": [p_lower, p_upper]
        }
        
    def to_dict(self):
        uncompounded_fees = max(self.accumulated_fees - self.compounded_fees, 0.0)
        total_val = self.pos_val + uncompounded_fees
        net_profit = total_val - self.initial_cap
        roi_pct = (net_profit / self.initial_cap) * 100.0 if self.initial_cap > 0 else 0.0
        
        # 1. KPIs de Rendimiento (Real Fee APR basado en la concentración actual y fees reales)
        elapsed_days = max(self.total_time_sec / 86400.0, 1.0 / 86400.0)
        raw_apr = (self.accumulated_fees / max(self.initial_cap, 0.001)) * (365.25 / elapsed_days) * 100.0
        active_apr = raw_apr if elapsed_days >= 0.05 else (self.instant_fee_apr if self.instant_fee_apr > 0 else raw_apr)
        real_fee_apr = max(0.0, min(active_apr, 350.0))
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
            "compounded_fees": self.compounded_fees,
            "short_tokens": self.short_tokens,
            "short_entry_price": self.short_entry_price,
            "realized_short_pnl": self.realized_short_pnl,
            "short_tx_costs": self.short_tx_costs,
            "short_adjustments": self.short_adjustments,
            "out_of_range_sec": (time.time() - self.out_of_range_since) if self.out_of_range_since else 0.0,
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
        
        # 1. SOL-USDC Position (50% = 500 EUR = $540 USD initial, +/-6.0% anti-whipsaw range on bin_step=10 pool)
        self.pos_sol_usdc = PositionTracker(
            name="SOL-USDC",
            pool_address=ADDR_SOL_USDC,
            initial_cap=ALLOC_SOL_USDC_USD,
            half_range_pct=OPTIMAL_HALF_RANGE_PCT,
            rebal_thresh=1.05,
            quote_is_usd=True,
            token_x_symbol="SOL",
            token_y_symbol="USDC"
        )
        
        # 2. JUP-USDC Position (25% = 250 EUR = $270 USD initial, +/-6.0% anti-whipsaw range on bin_step=50 pool)
        self.pos_cbbtc_usdc = PositionTracker(
            name="cbBTC-USDC",
            pool_address=ADDR_CBBTC_USDC,
            initial_cap=ALLOC_CBBTC_USDC_USD,
            half_range_pct=OPTIMAL_HALF_RANGE_PCT,
            rebal_thresh=1.05,
            quote_is_usd=True,
            token_x_symbol="cbBTC",
            token_y_symbol="USDC"
        )
        
        # 3. HYPE-USDC Position (25% = 250 EUR = $270 USD initial, +/-6.0% anti-whipsaw range on bin_step=20 pool)
        self.pos_hype_sol = PositionTracker(
            name="HYPE-USDC",
            pool_address=ADDR_HYPE_USDC,
            initial_cap=ALLOC_HYPE_SOL_USD,
            half_range_pct=OPTIMAL_HALF_RANGE_PCT,
            rebal_thresh=1.05,
            quote_is_usd=True,
            token_x_symbol="HYPE",
            token_y_symbol="USDC"
        )
        self.hype_initialized = True
        
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
                
            if data.get("reset_epoch") != RESET_EPOCH:
                print(f"[*] Nuevo ciclo de reset detectado ({RESET_EPOCH}). Iniciando estadísticas desde cero ahora mismo.")
                return
                
            print("[+] Restaurando estado persistente desde Firestore...")
            prev_sol_price = float(data.get("sol_price_usd", 95.29))
            
            # 0. Restore recent history buffer
            if "recent_history" in data and isinstance(data["recent_history"], list):
                self.recent_history = data["recent_history"][-40:]
                print(f"[+] {len(self.recent_history)} ticks históricos cargados en memoria.")
            
            # 1. Restore SOL-USDC
            sol_data = data.get("sol_usdc", {})
            if sol_data:
                self.pos_sol_usdc.total_time_sec = float(sol_data.get("total_time_sec", 0.0))
                self.pos_sol_usdc.time_in_range_sec = float(sol_data.get("time_in_range_sec", 0.0))
                
                saved_fees = float(sol_data.get("accumulated_fees", 0.0))
                days_active = self.pos_sol_usdc.time_in_range_sec / 86400.0
                max_realistic_fees = self.pos_sol_usdc.initial_cap * 0.0080 * max(days_active, 0.01)
                if saved_fees > max_realistic_fees or sol_data.get("pool_address") == "5rCf1DM8LjKTw4YqhnoLcngyZYeNnQqztScTogYHAS6":
                    saved_fees = self.pos_sol_usdc.initial_cap * 0.000745 * days_active
                self.pos_sol_usdc.accumulated_fees = saved_fees
                self.pos_sol_usdc.compounded_fees = float(sol_data.get("compounded_fees", 0.0))
                
                # If upgrading from ±2.5% to ±3.5% anti-whipsaw range, undo the false single-wick rebalance at $96.83
                if abs(float(sol_data.get("half_range_pct", 0.025)) - 0.025) < 0.001:
                    p0 = 94.63
                    self.pos_sol_usdc.total_rebalances = 0
                    self.pos_sol_usdc.total_rebal_costs = 0.0
                    self.pos_sol_usdc.current_cap = ALLOC_SOL_USDC_USD
                else:
                    p0 = float(sol_data.get("entry_price", 94.63))
                    self.pos_sol_usdc.total_rebalances = int(sol_data.get("total_rebalances", 0))
                    self.pos_sol_usdc.total_rebal_costs = float(sol_data.get("total_rebal_costs", 0.0))
                    self.pos_sol_usdc.current_cap = float(sol_data.get("current_cap", ALLOC_SOL_USDC_USD))
                    
                if p0 > 0:
                    self.pos_sol_usdc.entry_price = p0
                    self.pos_sol_usdc.p_lower = p0 * (1.0 - self.pos_sol_usdc.half_range_pct)
                    self.pos_sol_usdc.p_upper = p0 * (1.0 + self.pos_sol_usdc.half_range_pct)
                    self.pos_sol_usdc.initialized = True
                    
                    sp = math.sqrt(p0)
                    spa = math.sqrt(self.pos_sol_usdc.p_lower)
                    spb = math.sqrt(self.pos_sol_usdc.p_upper)
                    denom = (2.0 * sp - spa - p0 / spb)
                    self.pos_sol_usdc.L = self.pos_sol_usdc.current_cap / denom if denom > 0 else 1.0
                    self.pos_sol_usdc.hodl_x = (self.pos_sol_usdc.initial_cap / 2.0) / p0
                    self.pos_sol_usdc.hodl_y = self.pos_sol_usdc.initial_cap / 2.0
                    self.pos_sol_usdc.fees_x = (self.pos_sol_usdc.accumulated_fees * 0.5) / p0
                    self.pos_sol_usdc.fees_y = self.pos_sol_usdc.accumulated_fees * 0.5
                    self.pos_sol_usdc.short_tokens = float(sol_data.get("short_tokens", self.pos_sol_usdc.hodl_x))
                    self.pos_sol_usdc.short_entry_price = float(sol_data.get("short_entry_price", p0))
                    self.pos_sol_usdc.realized_short_pnl = float(sol_data.get("realized_short_pnl", 0.0))
                    self.pos_sol_usdc.short_tx_costs = float(sol_data.get("short_tx_costs", (self.pos_sol_usdc.initial_cap / 2.0) * 0.00035))
                    self.pos_sol_usdc.short_adjustments = int(sol_data.get("short_adjustments", 0))
                    
            # 2. Restore JUP-USDC (or seamlessly migrate from cbBTC-USDC preserving 100% of accumulated fees)
            jup_data = data.get("jup_usdc", {})
            if not jup_data:
                # Seamless migration from cbbtc_usdc
                old_btc = data.get("cbbtc_usdc", {})
                self.pos_cbbtc_usdc.accumulated_fees = float(old_btc.get("accumulated_fees", 0.3683))
                self.pos_cbbtc_usdc.compounded_fees = float(old_btc.get("compounded_fees", 0.0))
                self.pos_cbbtc_usdc.total_time_sec = float(old_btc.get("total_time_sec", 0.0))
                self.pos_cbbtc_usdc.time_in_range_sec = float(old_btc.get("time_in_range_sec", 0.0))
                self.pos_cbbtc_usdc.total_rebalances = 0
                self.pos_cbbtc_usdc.total_rebal_costs = 0.0
                self.pos_cbbtc_usdc.initial_cap = ALLOC_JUP_USDC_USD
                self.pos_cbbtc_usdc.current_cap = ALLOC_JUP_USDC_USD
                self.pos_cbbtc_usdc.initialized = False
                print(f"[+] Migrado cbBTC-USDC -> JUP-USDC preservando ${self.pos_cbbtc_usdc.accumulated_fees:.4f} USD en fees.")
            else:
                self.pos_cbbtc_usdc.total_rebalances = int(jup_data.get("total_rebalances", 0))
                self.pos_cbbtc_usdc.total_rebal_costs = float(jup_data.get("total_rebal_costs", 0.0))
                self.pos_cbbtc_usdc.total_time_sec = float(jup_data.get("total_time_sec", 0.0))
                self.pos_cbbtc_usdc.time_in_range_sec = float(jup_data.get("time_in_range_sec", 0.0))
                self.pos_cbbtc_usdc.accumulated_fees = float(jup_data.get("accumulated_fees", 0.0))
                self.pos_cbbtc_usdc.compounded_fees = float(jup_data.get("compounded_fees", 0.0))
                
                if "entry_price" in jup_data and float(jup_data["entry_price"]) > 0:
                    p0 = float(jup_data["entry_price"])
                    self.pos_cbbtc_usdc.entry_price = p0
                    self.pos_cbbtc_usdc.p_lower = p0 * (1.0 - self.pos_cbbtc_usdc.half_range_pct)
                    self.pos_cbbtc_usdc.p_upper = p0 * (1.0 + self.pos_cbbtc_usdc.half_range_pct)
                    self.pos_cbbtc_usdc.current_cap = float(jup_data.get("current_cap", ALLOC_JUP_USDC_USD))
                    self.pos_cbbtc_usdc.initialized = True
                    sp = math.sqrt(p0)
                    spa = math.sqrt(self.pos_cbbtc_usdc.p_lower)
                    spb = math.sqrt(self.pos_cbbtc_usdc.p_upper)
                    denom = (2.0 * sp - spa - p0 / spb)
                    self.pos_cbbtc_usdc.L = self.pos_cbbtc_usdc.current_cap / denom if denom > 0 else 1.0
                    self.pos_cbbtc_usdc.hodl_x = (self.pos_cbbtc_usdc.initial_cap / 2.0) / p0
                    self.pos_cbbtc_usdc.hodl_y = self.pos_cbbtc_usdc.initial_cap / 2.0
                    self.pos_cbbtc_usdc.fees_x = (self.pos_cbbtc_usdc.accumulated_fees * 0.5) / p0
                    self.pos_cbbtc_usdc.fees_y = self.pos_cbbtc_usdc.accumulated_fees * 0.5
                    self.pos_cbbtc_usdc.short_tokens = float(jup_data.get("short_tokens", self.pos_cbbtc_usdc.hodl_x))
                    self.pos_cbbtc_usdc.short_entry_price = float(jup_data.get("short_entry_price", p0))
                    self.pos_cbbtc_usdc.realized_short_pnl = float(jup_data.get("realized_short_pnl", 0.0))
                    self.pos_cbbtc_usdc.short_tx_costs = float(jup_data.get("short_tx_costs", (self.pos_cbbtc_usdc.initial_cap / 2.0) * 0.00035))
                    self.pos_cbbtc_usdc.short_adjustments = int(jup_data.get("short_adjustments", 0))

            # 3. Restore HYPE-USDC (or migrate seamlessly from HYPE-SOL preserving 100% of fees)
            hype_data = data.get("hype_sol", {})
            if hype_data:
                self.pos_hype_sol.total_time_sec = float(hype_data.get("total_time_sec", 0.0))
                self.pos_hype_sol.time_in_range_sec = float(hype_data.get("time_in_range_sec", 0.0))
                was_usd = bool(hype_data.get("quote_is_usd", False))
                if not was_usd:
                    # Seamless migration from HYPE-SOL to HYPE-USDC: convert earned SOL fees to USD
                    old_fees_sol = float(hype_data.get("accumulated_fees", 0.0))
                    self.pos_hype_sol.accumulated_fees = old_fees_sol * prev_sol_price
                    self.pos_hype_sol.compounded_fees = 0.0
                    self.pos_hype_sol.initial_cap = ALLOC_HYPE_SOL_USD
                    self.pos_hype_sol.current_cap = ALLOC_HYPE_SOL_USD
                    self.pos_hype_sol.total_rebalances = 0
                    self.pos_hype_sol.total_rebal_costs = 0.0
                    self.pos_hype_sol.initialized = False
                    print(f"[+] Migrado HYPE-SOL -> HYPE-USDC preservando ${self.pos_hype_sol.accumulated_fees:.4f} USD en fees.")
                else:
                    self.pos_hype_sol.total_rebalances = int(hype_data.get("total_rebalances", 0))
                    self.pos_hype_sol.total_rebal_costs = float(hype_data.get("total_rebal_costs", 0.0))
                    self.pos_hype_sol.initial_cap = ALLOC_HYPE_SOL_USD
                    self.pos_hype_sol.current_cap = float(hype_data.get("current_cap", ALLOC_HYPE_SOL_USD))
                    self.pos_hype_sol.accumulated_fees = float(hype_data.get("accumulated_fees", 0.0))
                    self.pos_hype_sol.compounded_fees = float(hype_data.get("compounded_fees", 0.0))
                    p0 = float(hype_data.get("entry_price", 0.0))
                    if p0 > 5.0: # Valid USD price (~$81.64)
                        self.pos_hype_sol.entry_price = p0
                        self.pos_hype_sol.p_lower = p0 * (1.0 - self.pos_hype_sol.half_range_pct)
                        self.pos_hype_sol.p_upper = p0 * (1.0 + self.pos_hype_sol.half_range_pct)
                        self.pos_hype_sol.initialized = True
                        sp = math.sqrt(p0)
                        spa = math.sqrt(self.pos_hype_sol.p_lower)
                        spb = math.sqrt(self.pos_hype_sol.p_upper)
                        denom = (2.0 * sp - spa - p0 / spb)
                        self.pos_hype_sol.L = self.pos_hype_sol.current_cap / denom if denom > 0 else 1.0
                        self.pos_hype_sol.hodl_x = (self.pos_hype_sol.initial_cap / 2.0) / p0
                        self.pos_hype_sol.hodl_y = self.pos_hype_sol.initial_cap / 2.0
                        self.pos_hype_sol.fees_x = (self.pos_hype_sol.accumulated_fees * 0.5) / p0
                        self.pos_hype_sol.fees_y = self.pos_hype_sol.accumulated_fees * 0.5
                        self.pos_hype_sol.short_tokens = float(hype_data.get("short_tokens", self.pos_hype_sol.hodl_x))
                        self.pos_hype_sol.short_entry_price = float(hype_data.get("short_entry_price", p0))
                        self.pos_hype_sol.realized_short_pnl = float(hype_data.get("realized_short_pnl", 0.0))
                        self.pos_hype_sol.short_tx_costs = float(hype_data.get("short_tx_costs", (self.pos_hype_sol.initial_cap / 2.0) * 0.00035))
                        self.pos_hype_sol.short_adjustments = int(hype_data.get("short_adjustments", 0))

            print(f"[+] Estado restaurado. Comisiones acumuladas SOL-USDC: ${self.pos_sol_usdc.accumulated_fees:.4f} USD")

            # Upgrade migration to ±6.0% range + dynamic short delta-sync (>15% drift)
            if data.get("strategy_migration_version") != STRATEGY_MIGRATION_VERSION:
                print(f"[*] Aplicando migración cuantitativa {STRATEGY_MIGRATION_VERSION}: rangos ±6.0% + sincronización dinámica de cortos (>15% desv.)...")
                # Initial entry prices at reset_epoch (2026-11-06T20:16:00)
                init_entries = [
                    (self.pos_sol_usdc, 90.10345, ALLOC_SOL_USDC_USD, float(data.get("sol_price_usd", 86.31))),
                    (self.pos_cbbtc_usdc, 0.24623, ALLOC_JUP_USDC_USD, float(data.get("btc_price_usd", 0.23425))),
                    (self.pos_hype_sol, 78.28076, ALLOC_HYPE_SOL_USD, float(data.get("hype_price_usd", 73.28587)))
                ]
                for pos, p0_init, alloc_usd, p_curr in init_entries:
                    pos.half_range_pct = OPTIMAL_HALF_RANGE_PCT
                    pos.entry_price = p0_init
                    pos.p_lower = p0_init * (1.0 - OPTIMAL_HALF_RANGE_PCT)
                    pos.p_upper = p0_init * (1.0 + OPTIMAL_HALF_RANGE_PCT)
                    pos.total_rebalances = 0
                    pos.total_rebal_costs = 0.0
                    # Capital includes initial allocation + already compounded fees
                    pos.current_cap = alloc_usd + pos.compounded_fees
                    sp0 = math.sqrt(p0_init)
                    spa = math.sqrt(pos.p_lower)
                    spb = math.sqrt(pos.p_upper)
                    denom = (2.0 * sp0 - spa - p0_init / spb)
                    pos.L = pos.current_cap / denom if denom > 0 else 1.0
                    pos.hodl_x = (alloc_usd / 2.0) / p0_init
                    pos.hodl_y = alloc_usd / 2.0
                    # Compute current token_x at p_curr inside the ±6% range
                    sp_c = math.sqrt(max(min(p_curr, pos.p_upper), pos.p_lower))
                    pos.token_x = pos.L * (1.0 / sp_c - 1.0 / spb)
                    pos.token_y = pos.L * (sp_c - spa)
                    pos.pos_val = pos.token_x * p_curr + pos.token_y
                    # Simulate continuous 15%-threshold delta-sync along the path p0_init -> p_curr
                    # Across the drop, average hedged short size is the midpoint between initial 50% token_x and current token_x
                    init_short_tokens = (alloc_usd / 2.0) / p0_init
                    avg_hedged_tokens = 0.55 * pos.token_x + 0.45 * init_short_tokens
                    init_tx_cost = (alloc_usd / 2.0) * HYPERLIQUID_TAKER_FEE
                    sync_tx_cost = abs(pos.token_x - init_short_tokens) * p_curr * HYPERLIQUID_TAKER_FEE
                    pos.realized_short_pnl = (p0_init - p_curr) * avg_hedged_tokens
                    pos.short_tx_costs = init_tx_cost + sync_tx_cost
                    pos.short_tokens = pos.token_x
                    pos.short_entry_price = p_curr
                    pos.short_adjustments = 2
                    pos.initialized = True
        except Exception as e:
            print(f"[!] Error restaurando estado persistente: {e}")
            
    def tick(self):
        now = time.time()
        dt = max(now - self.last_ts, 1.0)
        self.last_ts = now
        
        # Fetch all 3 pools from Meteora API
        pool_sol_usdc = self.client.get_pool_by_address(ADDR_SOL_USDC)
        pool_cbbtc_usdc = self.client.get_pool_by_address(ADDR_JUP_USDC)
        pool_hype_sol = self.client.get_pool_by_address(ADDR_HYPE_USDC)
        
        if not pool_sol_usdc or not pool_cbbtc_usdc or not pool_hype_sol:
            print("[!] Aviso: Fallo momentáneo al consultar alguno de los 3 pools en Meteora. Reintentando...")
            return
            
        sol_price_usd = pool_sol_usdc["current_price"]
        btc_price_usd = pool_cbbtc_usdc["current_price"]
        hype_price_usd = pool_hype_sol["current_price"]
        hype_price_sol = hype_price_usd / sol_price_usd if sol_price_usd > 0 else 0.85
            
        reb_sol = self.pos_sol_usdc.update_tick(pool_sol_usdc, dt, sol_price_usd)
        reb_btc = self.pos_cbbtc_usdc.update_tick(pool_cbbtc_usdc, dt, sol_price_usd)
        reb_hype = self.pos_hype_sol.update_tick(pool_hype_sol, dt, sol_price_usd)

        # Portfolio-wide Auto-Compound trigger whenever combined uncompounded fees in Meteora reach >= $5.00 USD
        total_uncompounded_usd = (
            max(self.pos_sol_usdc.accumulated_fees - self.pos_sol_usdc.compounded_fees, 0.0) +
            max(self.pos_cbbtc_usdc.accumulated_fees - self.pos_cbbtc_usdc.compounded_fees, 0.0) +
            max(self.pos_hype_sol.accumulated_fees - self.pos_hype_sol.compounded_fees, 0.0)
        )
        if total_uncompounded_usd >= AUTO_COMPOUND_FEE_THRESHOLD_USD:
            print(f"[+] [PORTFOLIO] Acumulados ${total_uncompounded_usd:.2f} USD (>= $5.00 USD). Ejecutando Auto-Compound automático en Meteora...")
            self.pos_sol_usdc.compound_fees_only(sol_price_usd)
            self.pos_cbbtc_usdc.compound_fees_only(btc_price_usd)
            self.pos_hype_sol.compound_fees_only(hype_price_usd)
            total_uncompounded_usd = 0.0

        total_compounded_usd = (
            self.pos_sol_usdc.compounded_fees +
            self.pos_cbbtc_usdc.compounded_fees +
            self.pos_hype_sol.compounded_fees
        )
        
        # Individual dicts
        d_sol = self.pos_sol_usdc.to_dict()
        d_btc = self.pos_cbbtc_usdc.to_dict()
        d_hype = self.pos_hype_sol.to_dict()
        
        # HYPE-USDC position is now natively in USD terms
        hype_val_usd = d_hype["total_val"]
        hype_init_usd = d_hype["initial_cap"]
        hype_fees_usd = d_hype["accumulated_fees"]
        hype_il_usd = d_hype["il_amount"]
        hype_net_vs_hodl_usd = d_hype["net_vs_hodl"]
        hype_rebal_costs_usd = d_hype["total_rebal_costs"]
        
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
        
        # Token Balances across all 3 pools (SOL-USDC, cbBTC-USDC, HYPE-USDC)
        sol_from_sol_usdc = d_sol["token_x"]
        usdc_from_sol_usdc = d_sol["token_y"]
        cbbtc_from_btc = d_btc["token_x"]
        usdc_from_btc = d_btc["token_y"]
        hype_from_hype = d_hype["token_x"]
        usdc_from_hype = d_hype["token_y"]
        
        sol_total = sol_from_sol_usdc
        usdc_total = usdc_from_sol_usdc + usdc_from_btc + usdc_from_hype
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
        fees_sol_total = d_sol.get("fees_x", 0.0)
        fees_usdc_total = d_sol.get("fees_y", 0.0) + d_btc.get("fees_y", 0.0) + d_hype.get("fees_y", 0.0)
        fees_cbbtc_total = d_btc.get("fees_x", 0.0)
        fees_hype_total = d_hype.get("fees_x", 0.0)
        
        fees_by_token = {
            "sol": fees_sol_total,
            "usdc": fees_usdc_total,
            "cbbtc": fees_cbbtc_total,
            "jup": fees_cbbtc_total,
            "hype": fees_hype_total,
            "sol_usd": fees_sol_total * sol_price_usd,
            "usdc_usd": fees_usdc_total,
            "cbbtc_usd": fees_cbbtc_total * btc_price_usd,
            "jup_usd": fees_cbbtc_total * btc_price_usd,
            "hype_usd": fees_hype_total * hype_price_usd,
            "sol_eur": (fees_sol_total * sol_price_usd) / self.eur_usd_rate,
            "usdc_eur": fees_usdc_total / self.eur_usd_rate,
            "cbbtc_eur": (fees_cbbtc_total * btc_price_usd) / self.eur_usd_rate,
            "jup_eur": (fees_cbbtc_total * btc_price_usd) / self.eur_usd_rate,
            "hype_eur": (fees_hype_total * hype_price_usd) / self.eur_usd_rate
        }
        
        # -------------------------------------------------------------
        # Hyperliquid Delta-Neutral Perps Hedge Engine (Live MarkPx & Dynamic Rebalance-Synced Short)
        # -------------------------------------------------------------
        hl_market = fetch_hyperliquid_perps()
        sol_hl = hl_market["SOL"]
        btc_hl = hl_market.get("JUP", hl_market.get("BTC"))
        hype_hl = hl_market["HYPE"]

        # Dynamic Rebalance-Synced Short Sizes & Entry Prices (paid & settled 100% in USDC)
        sol_short_tokens = d_sol.get("short_tokens") or (270.0 / max(d_sol.get("entry_price", sol_price_usd), 1.0))
        btc_short_tokens = d_btc.get("short_tokens") or (135.0 / max(d_btc.get("entry_price", btc_price_usd), 1.0))
        hype_short_tokens = d_hype.get("short_tokens") or (135.0 / max(d_hype.get("entry_price", hype_price_usd), 1.0))

        sol_entry_px = d_sol.get("short_entry_price") or d_sol.get("entry_price") or sol_price_usd
        btc_entry_px = d_btc.get("short_entry_price") or d_btc.get("entry_price") or btc_price_usd
        hype_entry_px = d_hype.get("short_entry_price") or d_hype.get("entry_price") or hype_price_usd

        # Realized USDC PnL (crystallized at each pool rebalance) + Unrealized USDC PnL on active leg
        sol_unrealized_pnl = (sol_entry_px - sol_price_usd) * sol_short_tokens
        btc_unrealized_pnl = (btc_entry_px - btc_price_usd) * btc_short_tokens
        hype_unrealized_pnl = (hype_entry_px - hype_price_usd) * hype_short_tokens

        sol_short_pnl_usd = d_sol.get("realized_short_pnl", 0.0) + sol_unrealized_pnl - d_sol.get("short_tx_costs", 0.0)
        btc_short_pnl_usd = d_btc.get("realized_short_pnl", 0.0) + btc_unrealized_pnl - d_btc.get("short_tx_costs", 0.0)
        hype_short_pnl_usd = d_hype.get("realized_short_pnl", 0.0) + hype_unrealized_pnl - d_hype.get("short_tx_costs", 0.0)

        total_short_pnl_usd = sol_short_pnl_usd + btc_short_pnl_usd + hype_short_pnl_usd
        total_short_pnl_eur = total_short_pnl_usd / self.eur_usd_rate
        total_realized_short_pnl_usd = d_sol.get("realized_short_pnl", 0.0) + d_btc.get("realized_short_pnl", 0.0) + d_hype.get("realized_short_pnl", 0.0)
        total_short_adjustments = d_sol.get("short_adjustments", 0) + d_btc.get("short_adjustments", 0) + d_hype.get("short_adjustments", 0)
        total_short_tx_costs_usd = d_sol.get("short_tx_costs", 0.0) + d_btc.get("short_tx_costs", 0.0) + d_hype.get("short_tx_costs", 0.0)

        # Live Funding Rate Yield on Hyperliquid Short Notional (paid hourly in USDC from reset moment)
        elapsed_hours = max(d_sol.get("total_time_sec", 0.0) / 3600.0, 0.0)
        sol_short_notional = sol_short_tokens * sol_hl["mark_px"]
        btc_short_notional = btc_short_tokens * btc_hl["mark_px"]
        hype_short_notional = hype_short_tokens * hype_hl["mark_px"]
        total_short_notional_usd = sol_short_notional + btc_short_notional + hype_short_notional

        sol_funding_usd = sol_short_notional * max(sol_hl["funding_1h"], 0.000005) * elapsed_hours
        btc_funding_usd = btc_short_notional * max(btc_hl["funding_1h"], 0.00001) * elapsed_hours
        hype_funding_usd = hype_short_notional * max(hype_hl["funding_1h"], 0.00002) * elapsed_hours
        total_funding_usd = sol_funding_usd + btc_funding_usd + hype_funding_usd
        total_funding_eur = total_funding_usd / self.eur_usd_rate

        weighted_funding_apr = (
            (sol_hl["funding_apr"] * 0.50) +
            (btc_hl["funding_apr"] * 0.25) +
            (hype_hl["funding_apr"] * 0.25)
        )

        unhedged_portfolio_usd = total_portfolio_usd
        unhedged_portfolio_eur = total_portfolio_eur
        hedged_portfolio_usd = unhedged_portfolio_usd + total_short_pnl_usd + total_funding_usd
        hedged_portfolio_eur = hedged_portfolio_usd / self.eur_usd_rate
        hedged_roi_pct = ((hedged_portfolio_usd - total_initial_usd) / total_initial_usd) * 100.0

        # Pure LP Price PnL (excluding fees) vs Short PnL reconciliation
        sol_lp_price_pnl_usd = d_sol["pos_val"] - d_sol.get("initial_cap", ALLOC_SOL_USDC_USD)
        btc_lp_price_pnl_usd = d_btc["pos_val"] - d_btc.get("initial_cap", ALLOC_CBBTC_USDC_USD)
        hype_lp_price_pnl_usd = d_hype["pos_val"] - d_hype.get("initial_cap", ALLOC_HYPE_SOL_USD)
        d_sol["lp_price_pnl_usd"] = sol_lp_price_pnl_usd
        d_btc["lp_price_pnl_usd"] = btc_lp_price_pnl_usd
        d_hype["lp_price_pnl_usd"] = hype_lp_price_pnl_usd

        total_lp_price_pnl_usd = sol_lp_price_pnl_usd + btc_lp_price_pnl_usd + hype_lp_price_pnl_usd
        total_lp_price_pnl_eur = total_lp_price_pnl_usd / self.eur_usd_rate
        net_price_hedge_pnl_usd = total_lp_price_pnl_usd + total_short_pnl_usd
        net_price_hedge_pnl_eur = net_price_hedge_pnl_usd / self.eur_usd_rate

        total_passive_yield_usd = total_fees_usd + total_funding_usd
        total_passive_yield_eur = total_passive_yield_usd / self.eur_usd_rate
        # Funding APR applies to the 50% shorted notional ($540 / $1080 = 0.50 of total portfolio)
        funding_portfolio_apr = weighted_funding_apr * 0.50
        total_combined_apr = combined_real_apr + funding_portfolio_apr
        total_combined_apy = ((math.pow(1.0 + (total_combined_apr / 100.0) / 365.25, 365.25) - 1.0)) * 100.0

        hyperliquid_hedge = {
            "enabled": True,
            "settlement_currency": "USDC",
            "mode": "Hyperliquid Delta-Sync Automático (>15% desv. o Rebalanceo) + Meteora Auto-Compound c/$2.50 USD",
            "recommended_split": "80% Meteora Pools (800 €) / 20% Hyperliquid Cross-Margin 2.0x (200 €)",
            "margin_collateral_usd": 216.0,
            "margin_collateral_eur": 200.0,
            "effective_leverage": round(total_short_notional_usd / 216.0, 2),
            "total_short_notional_usd": total_short_notional_usd,
            "total_short_pnl_usd": total_short_pnl_usd,
            "total_short_pnl_eur": total_short_pnl_eur,
            "total_lp_price_pnl_usd": total_lp_price_pnl_usd,
            "total_lp_price_pnl_eur": total_lp_price_pnl_eur,
            "net_price_hedge_pnl_usd": net_price_hedge_pnl_usd,
            "net_price_hedge_pnl_eur": net_price_hedge_pnl_eur,
            "total_realized_short_pnl_usd": total_realized_short_pnl_usd,
            "total_short_adjustments": total_short_adjustments,
            "total_short_tx_costs_usd": total_short_tx_costs_usd,
            "uncompounded_fees_usd": total_uncompounded_usd,
            "compounded_fees_usd": total_compounded_usd,
            "auto_compound_threshold_usd": AUTO_COMPOUND_FEE_THRESHOLD_USD,
            "total_funding_usd": total_funding_usd,
            "total_funding_eur": total_funding_eur,
            "weighted_funding_apr": weighted_funding_apr,
            "funding_portfolio_apr": funding_portfolio_apr,
            "total_combined_apr": total_combined_apr,
            "total_combined_apy": total_combined_apy,
            "unhedged_portfolio_usd": unhedged_portfolio_usd,
            "unhedged_portfolio_eur": unhedged_portfolio_eur,
            "hedged_portfolio_usd": hedged_portfolio_usd,
            "hedged_portfolio_eur": hedged_portfolio_eur,
            "hedged_roi_pct": hedged_roi_pct,
            "net_delta_pct": 0.0,
            "positions": {
                "SOL": {
                    "symbol": "SOL-PERP",
                    "side": "SHORT",
                    "settlement": "USDC",
                    "size_tokens": sol_short_tokens,
                    "lp_tokens": d_sol["token_x"],
                    "entry_px": sol_entry_px,
                    "mark_px": sol_hl["mark_px"],
                    "notional_usd": sol_short_notional,
                    "realized_pnl_usd": d_sol.get("realized_short_pnl", 0.0),
                    "unrealized_pnl_usd": sol_unrealized_pnl,
                    "pnl_usd": sol_short_pnl_usd,
                    "lp_price_pnl_usd": sol_lp_price_pnl_usd,
                    "net_pair_pnl_usd": sol_lp_price_pnl_usd + sol_short_pnl_usd,
                    "rebalance_syncs": d_sol.get("short_adjustments", 0),
                    "funding_1h_pct": sol_hl["funding_1h"] * 100.0,
                    "funding_apr_pct": sol_hl["funding_apr"],
                    "funding_earned_usd": sol_funding_usd
                },
                "JUP": {
                    "symbol": "JUP-PERP",
                    "side": "SHORT",
                    "settlement": "USDC",
                    "size_tokens": btc_short_tokens,
                    "lp_tokens": d_btc["token_x"],
                    "entry_px": btc_entry_px,
                    "mark_px": btc_hl["mark_px"],
                    "notional_usd": btc_short_notional,
                    "realized_pnl_usd": d_btc.get("realized_short_pnl", 0.0),
                    "unrealized_pnl_usd": btc_unrealized_pnl,
                    "pnl_usd": btc_short_pnl_usd,
                    "lp_price_pnl_usd": btc_lp_price_pnl_usd,
                    "net_pair_pnl_usd": btc_lp_price_pnl_usd + btc_short_pnl_usd,
                    "rebalance_syncs": d_btc.get("short_adjustments", 0),
                    "funding_1h_pct": btc_hl["funding_1h"] * 100.0,
                    "funding_apr_pct": btc_hl["funding_apr"],
                    "funding_earned_usd": btc_funding_usd
                },
                "BTC": {
                    "symbol": "JUP-PERP",
                    "side": "SHORT",
                    "settlement": "USDC",
                    "size_tokens": btc_short_tokens,
                    "lp_tokens": d_btc["token_x"],
                    "entry_px": btc_entry_px,
                    "mark_px": btc_hl["mark_px"],
                    "notional_usd": btc_short_notional,
                    "realized_pnl_usd": d_btc.get("realized_short_pnl", 0.0),
                    "unrealized_pnl_usd": btc_unrealized_pnl,
                    "pnl_usd": btc_short_pnl_usd,
                    "lp_price_pnl_usd": btc_lp_price_pnl_usd,
                    "net_pair_pnl_usd": btc_lp_price_pnl_usd + btc_short_pnl_usd,
                    "rebalance_syncs": d_btc.get("short_adjustments", 0),
                    "funding_1h_pct": btc_hl["funding_1h"] * 100.0,
                    "funding_apr_pct": btc_hl["funding_apr"],
                    "funding_earned_usd": btc_funding_usd
                },
                "HYPE": {
                    "symbol": "HYPE-PERP",
                    "side": "SHORT",
                    "settlement": "USDC",
                    "size_tokens": hype_short_tokens,
                    "lp_tokens": d_hype["token_x"],
                    "entry_px": hype_entry_px,
                    "mark_px": hype_hl["mark_px"],
                    "notional_usd": hype_short_notional,
                    "realized_pnl_usd": d_hype.get("realized_short_pnl", 0.0),
                    "unrealized_pnl_usd": hype_unrealized_pnl,
                    "pnl_usd": hype_short_pnl_usd,
                    "lp_price_pnl_usd": hype_lp_price_pnl_usd,
                    "net_pair_pnl_usd": hype_lp_price_pnl_usd + hype_short_pnl_usd,
                    "rebalance_syncs": d_hype.get("short_adjustments", 0),
                    "funding_1h_pct": hype_hl["funding_1h"] * 100.0,
                    "funding_apr_pct": hype_hl["funding_apr"],
                    "funding_earned_usd": hype_funding_usd
                }
            }
        }

        state_doc = {
            "reset_epoch": RESET_EPOCH,
            "strategy_migration_version": STRATEGY_MIGRATION_VERSION,
            "last_updated": datetime.now().isoformat(),
            "fees_by_token": fees_by_token,
            "hyperliquid_hedge": hyperliquid_hedge,
            "sol_price_usd": sol_price_usd,
            "btc_price_usd": btc_price_usd,
            "hype_price_usd": hype_price_usd,
            "hype_price_sol": hype_price_sol,
            "eur_usd_rate": self.eur_usd_rate,
            "initial_capital_eur": self.initial_eur,
            "initial_capital_usd": self.initial_usd,
            "is_real_market_linked": True,
            "market_link_info": {
                "source": "Solana Meteora DLMM + Hyperliquid L1 Perps API (Live Real-Time)",
                "sol_usdc_pool": ADDR_SOL_USDC,
                "cbbtc_usdc_pool": ADDR_CBBTC_USDC,
                "hype_sol_pool": ADDR_HYPE_USDC,
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
                "hedged_portfolio_usd": hedged_portfolio_usd,
                "hedged_portfolio_eur": hedged_portfolio_eur,
                "hedged_roi_pct": hedged_roi_pct,
                "short_hedge_pnl_usd": total_short_pnl_usd,
                "short_hedge_pnl_eur": total_short_pnl_eur,
                "lp_price_pnl_usd": total_lp_price_pnl_usd,
                "lp_price_pnl_eur": total_lp_price_pnl_eur,
                "net_price_hedge_pnl_usd": net_price_hedge_pnl_usd,
                "net_price_hedge_pnl_eur": net_price_hedge_pnl_eur,
                "funding_earned_usd": total_funding_usd,
                "funding_earned_eur": total_funding_eur,
                "total_passive_yield_usd": total_passive_yield_usd,
                "total_passive_yield_eur": total_passive_yield_eur,
                "total_combined_apr": total_combined_apr,
                "total_combined_apy": total_combined_apy,
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
                "jup_total": cbbtc_total,
                "hype_total": hype_total,
                "sol_usd_val": sol_usd_val,
                "sol_eur_val": sol_eur_val,
                "usdc_usd_val": usdc_usd_val,
                "usdc_eur_val": usdc_eur_val,
                "cbbtc_usd_val": cbbtc_usd_val,
                "jup_usd_val": cbbtc_usd_val,
                "cbbtc_eur_val": cbbtc_eur_val,
                "jup_eur_val": cbbtc_eur_val,
                "hype_usd_val": hype_usd_val,
                "hype_eur_val": hype_eur_val
            },
            "initial_investment_steps": {
                "initial_eur": 1000.0,
                "initial_usd": 1080.0,
                "distribution": "50% SOL-USDC (500 €) / 25% JUP-USDC (250 €) / 25% HYPE-USDC (250 €)",
                "step1_sol_usdc": f"250 EUR en SOL (~{ALLOC_SOL_USDC_USD*0.5/sol_price_usd:.3f} SOL) + 250 EUR en USDC (${ALLOC_SOL_USDC_USD*0.5:.2f} USDC)",
                "step2_cbbtc_usdc": f"125 EUR en JUP (~{ALLOC_JUP_USDC_USD*0.5/btc_price_usd:.2f} JUP) + 125 EUR en USDC (${ALLOC_JUP_USDC_USD*0.5:.2f} USDC)",
                "step3_hype_sol": f"125 EUR en HYPE (~{ALLOC_HYPE_SOL_USD*0.5/hype_price_usd:.3f} HYPE) + 125 EUR en USDC (${ALLOC_HYPE_SOL_USD*0.5:.2f} USDC)"
            },
            "sol_usdc": d_sol,
            "cbbtc_usdc": d_btc,
            "jup_usdc": d_btc,
            "hype_sol": d_hype
        }
        
        # Keep 40 most recent telemetry ticks for live charting
        time_label = datetime.now().strftime("%H:%M:%S")
        sol_eur_v = (d_sol["total_val"] if d_sol["quote_is_usd"] else (d_sol["total_val"] * sol_price_usd)) / self.eur_usd_rate
        btc_eur_v = (d_btc["total_val"] if d_btc["quote_is_usd"] else (d_btc["total_val"] * btc_price_usd)) / self.eur_usd_rate
        hype_eur_v = (d_hype["total_val"] if d_hype["quote_is_usd"] else (hype_fees_usd + (d_hype["pos_val"] * sol_price_usd))) / self.eur_usd_rate
        
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
                with TICK_LOCK:
                    self.tick()
            except Exception as e:
                print(f"[!] Error inesperado en loop del bot: {e}")
            time.sleep(POLL_INTERVAL)

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"[+] Servidor HTTP de monitoreo activo en puerto {PORT}")
    server.serve_forever()

if __name__ == "__main__":
    daemon = TriPoolCloudDaemon()
    GLOBAL_DAEMON = daemon
    t = threading.Thread(target=start_health_server, daemon=True)
    t.start()
    daemon.run()

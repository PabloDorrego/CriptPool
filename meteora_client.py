"""
Meteora DLMM Client for Python
Directly queries Meteora DatAPI pools endpoint by address
"""

import urllib.request
import json
import time

class MeteoraClient:
    BASE_URL = "https://dlmm.datapi.meteora.ag"
    
    def __init__(self, timeout=10):
        self.timeout = timeout
        
    def get_pool_by_address(self, pool_address):
        url = f"{self.BASE_URL}/pools/{pool_address}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    raw = json.loads(resp.read().decode("utf-8"))
                    if isinstance(raw, dict) and "current_price" in raw:
                        return self._parse_pool(raw)
        except Exception as e:
            print(f"[!] Error consultando Meteora para {pool_address}: {e}")
        return None
        
    def _parse_pool(self, raw):
        cfg = raw.get("pool_config", {})
        vol = raw.get("volume", {})
        fees = raw.get("fees", {})
        return {
            "address": raw.get("address"),
            "name": raw.get("name"),
            "current_price": float(raw.get("current_price", 0.0)),
            "tvl": float(raw.get("tvl", 0.0)),
            "bin_step": cfg.get("bin_step", 10),
            "base_fee_pct": float(cfg.get("base_fee_pct", 0.04)),
            "dynamic_fee_pct": float(raw.get("dynamic_fee_pct", 0.0)),
            "protocol_fee_pct": float(cfg.get("protocol_fee_pct", 5.0)),
            "volume_24h": float(vol.get("24h", 0.0)),
            "volume_1h": float(vol.get("1h", 0.0)),
            "fees_24h": float(fees.get("24h", 0.0)),
            "apy": float(raw.get("apy", 0.0)),
            "token_x": raw.get("token_x", {}).get("symbol", "SOL"),
            "token_y": raw.get("token_y", {}).get("symbol", "USDC"),
            "timestamp": time.time()
        }

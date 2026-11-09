import urllib.request
import json

def get_hyperliquid_coins():
    url = "https://api.hyperliquid.xyz/info"
    payload = json.dumps({"type": "metaAndAssetCtxs"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            meta = data[0].get("universe", [])
            coins = {m.get("name") for m in meta}
            return coins
    except Exception as e:
        print("Error HL:", e)
        return set()

def scan_meteora_pools(hl_coins):
    url = "https://dlmm.datapi.meteora.ag/pools?page_size=100&order_by=fees_24h"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pools = data.get("data", [])
            print(f"Total Meteora pools fetched: {len(pools)}")
            
            candidates = []
            for p in pools:
                name = p.get("name", "")
                t_x = p.get("token_x", {}).get("symbol", "").upper()
                t_y = p.get("token_y", {}).get("symbol", "").upper()
                tvl = float(p.get("tvl", 0) or 0)
                vol = float(p.get("volume", {}).get("24h", 0) if isinstance(p.get("volume"), dict) else (p.get("volume_24h", 0) or 0))
                fees = float(p.get("fees", {}).get("24h", 0) if isinstance(p.get("fees"), dict) else (p.get("fees_24h", 0) or 0))
                
                apr = (fees / tvl * 365.25 * 100.0) if tvl > 0 else 0
                
                x_on_hl = t_x in hl_coins or t_x in ["SOL", "JUP", "HYPE", "BTC", "ETH", "WIF", "RENDER", "POPCAT", "RAY"]
                y_on_hl = t_y in hl_coins or t_y in ["SOL", "JUP", "HYPE", "BTC", "ETH", "WIF", "RENDER", "POPCAT", "RAY"]
                
                is_hedgeable = False
                hedge_type = ""
                if (t_y in ["USDC", "USDT", "USD"]) and x_on_hl:
                    is_hedgeable = True
                    hedge_type = f"Short {t_x}"
                elif (t_x in ["USDC", "USDT", "USD"]) and y_on_hl:
                    is_hedgeable = True
                    hedge_type = f"Short {t_y}"
                elif x_on_hl and y_on_hl:
                    is_hedgeable = True
                    hedge_type = f"Short {t_x} + Short {t_y}"
                    
                candidates.append({
                    "name": name,
                    "address": p.get("address"),
                    "tvl": tvl,
                    "vol": vol,
                    "fees": fees,
                    "apr": apr,
                    "bin_step": p.get("pool_config", {}).get("bin_step", 0),
                    "base_fee": float(p.get("pool_config", {}).get("base_fee_pct", 0) or 0),
                    "is_hedgeable": is_hedgeable,
                    "hedge_type": hedge_type,
                    "t_x": t_x,
                    "t_y": t_y
                })
                
            print("\n=== TOP 20 POOLS METEORA APTAS PARA ESTRATEGIA DELTA-NEUTRAL (CON PERPETUOS EN HYPERLIQUID) ===")
            candidates_hedgeable = [c for c in candidates if c["is_hedgeable"] and c["tvl"] >= 100000]
            for c in sorted(candidates_hedgeable, key=lambda x: x["fees"], reverse=True)[:20]:
                print(f"{c['name']:15s} | TVL: ${c['tvl']:10,.0f} | Vol24: ${c['vol']:11,.0f} | Fees24: ${c['fees']:8,.2f} | APR base: {c['apr']:5.1f}% | {c['hedge_type']:25s} | Bin: {c['bin_step']:2d} | Fee: {c['base_fee']}% | Addr: {c['address']}")

            print("\n=== TODOS LOS POOLS RELACIONADOS CON JUP EN TOP 100 ===")
            jup_found = [c for c in candidates if "JUP" in c["name"].upper()]
            for c in jup_found:
                print(f"{c['name']:15s} | TVL: ${c['tvl']:10,.0f} | Vol24: ${c['vol']:11,.0f} | Fees24: ${c['fees']:8,.2f} | APR base: {c['apr']:5.1f}% | {c['hedge_type']:25s} | Addr: {c['address']}")

    except Exception as e:
        print("Error Meteora:", e)

if __name__ == "__main__":
    coins = get_hyperliquid_coins()
    scan_meteora_pools(coins)

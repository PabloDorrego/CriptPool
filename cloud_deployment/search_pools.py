import urllib.request
import json

def fetch_all():
    url = "https://dlmm.datapi.meteora.ag/pools?limit=100"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pools = data.get("data", [])
            print(f"Total pools fetched: {len(pools)}")
            
            # Print all JUP pools
            print("\n=== TODOS LOS PARES CON JUP ===")
            jup_pools = [p for p in pools if "JUP" in p.get("name", "").upper()]
            for p in sorted(jup_pools, key=lambda x: float(x.get("fees", {}).get("24h", 0) if isinstance(x.get("fees"), dict) else (x.get("fees_24h", 0) or 0)), reverse=True):
                tvl = float(p.get("tvl", 0) or 0)
                vol = float(p.get("volume", {}).get("24h", 0) if isinstance(p.get("volume"), dict) else (p.get("volume_24h", 0) or 0))
                fees = float(p.get("fees", {}).get("24h", 0) if isinstance(p.get("fees"), dict) else (p.get("fees_24h", 0) or 0))
                apr = (fees / tvl * 365.25 * 100.0) if tvl > 0 else 0
                bin_step = p.get("pool_config", {}).get("bin_step", 0)
                base_fee = float(p.get("pool_config", {}).get("base_fee_pct", 0) or 0)
                print(f"{p.get('name'):20s} | TVL: ${tvl:12,.0f} | Vol24h: ${vol:12,.0f} | Fees24h: ${fees:8,.2f} | APR base: {apr:6.1f}% | Bin: {bin_step} | Fee: {base_fee}% | {p.get('address')}")
                
            # Top 15 pools on Meteora by fees / volume
            print("\n=== TOP 20 POOLS METEORA POR COMISIONES (FEES 24H) ===")
            top_pools = sorted(pools, key=lambda x: float(x.get("fees", {}).get("24h", 0) if isinstance(x.get("fees"), dict) else (x.get("fees_24h", 0) or 0)), reverse=True)[:20]
            for p in top_pools:
                tvl = float(p.get("tvl", 0) or 0)
                vol = float(p.get("volume", {}).get("24h", 0) if isinstance(p.get("volume"), dict) else (p.get("volume_24h", 0) or 0))
                fees = float(p.get("fees", {}).get("24h", 0) if isinstance(p.get("fees"), dict) else (p.get("fees_24h", 0) or 0))
                apr = (fees / tvl * 365.25 * 100.0) if tvl > 0 else 0
                bin_step = p.get("pool_config", {}).get("bin_step", 0)
                base_fee = float(p.get("pool_config", {}).get("base_fee_pct", 0) or 0)
                print(f"{p.get('name'):20s} | TVL: ${tvl:12,.0f} | Vol24h: ${vol:12,.0f} | Fees24h: ${fees:8,.2f} | APR base: {apr:6.1f}% | Bin: {bin_step} | Fee: {base_fee}% | {p.get('address')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_all()

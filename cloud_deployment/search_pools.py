import urllib.request, json

for s in ['JUP', 'WIF', 'RENDER', 'PYTH', 'POPCAT', 'HYPE', 'RAY', 'DRIFT']:
    url = f"https://dlmm.datapi.meteora.ag/pools?search={s}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pools = data.get("data", [])
            print(f"\n--- SEARCH: {s} (Found {len(pools)}) ---")
            for p in pools[:5]:
                name = p.get("name", "")
                tvl = float(p.get("tvl", 0) or 0)
                vol = float(p.get("volume", {}).get("24h", 0) if isinstance(p.get("volume"), dict) else (p.get("volume_24h", 0) or 0))
                fees = float(p.get("fees", {}).get("24h", 0) if isinstance(p.get("fees"), dict) else (p.get("fees_24h", 0) or 0))
                addr = p.get("address", "")
                bin_step = p.get("pool_config", {}).get("bin_step", 0)
                base_fee = float(p.get("pool_config", {}).get("base_fee_pct", 0) or 0)
                fee_ratio = (fees / tvl * 100.0) if tvl > 0 else 0
                apr = fee_ratio * 365.25
                print(f"{name:20s} | TVL: ${tvl:<10,.0f} | Vol24: ${vol:<12,.0f} | Fees24: ${fees:<9,.2f} | Fee/TVL: {fee_ratio:.2f}%/d (APR: {apr:.0f}%) | Bin: {bin_step} | Fee: {base_fee}% | Addr: {addr}")
    except Exception as e:
        print(f"Error {s}: {e}")

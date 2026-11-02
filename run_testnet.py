"""
Meteora DLMM Testnet & Paper Trading CLI Suite
Main controller to launch, monitor, inspect, and reset the simulation environment.
"""

import sys
import time
import os
import json
from datetime import datetime
from paper_trading_engine import PaperTradingEngine, STATE_FILE, HISTORY_FILE, CONFIG_FILE
from meteora_client import MeteoraClient

def print_banner():
    print("""
================================================================================
   METEORA DLMM (SOLANA) - ENTORNO DE PRUEBAS / PAPER TRADING BOT               
================================================================================
    """)

def cmd_status():
    print_banner()
    if not os.path.exists(STATE_FILE):
        print("[-] No hay ninguna posición virtual activa. Ejecuta 'python run_testnet.py start' para iniciar.")
        return
        
    engine = PaperTradingEngine()
    tick = engine.update_tick()
    if not tick:
        print("[!] No se pudo conectar con Meteora. Revisa tu conexión a internet.")
        return
        
    st = tick["state"]
    pool = tick["pool"]
    
    # Distance to boundaries
    p_curr = st["current_price"]
    dist_low_pct = abs(p_curr - st["p_lower"]) / st["entry_price"] * 100.0
    dist_high_pct = abs(st["p_upper"] - p_curr) / st["entry_price"] * 100.0
    
    print(f" [ESTADO DEL POOL - {st['pool_name']}]")
    print(f"  * Dirección Pool: {st['pool_address']}")
    print(f"  * Precio Actual:  ${p_curr:.4f} USDC")
    print(f"  * TVL del Pool:   ${pool.get('tvl', 0):,.2f} USD")
    print(f"  * Volumen 24h:    ${pool.get('volume_24h', 0):,.2f} USD")
    print(f"  * Tarifa Base:    {pool.get('base_fee_pct', 0)}% | Tarifa Dinámica: {pool.get('dynamic_fee_pct', 0):.4f}%")
    print("-" * 80)
    print(f" [TU POSICIÓN VIRTUAL DE PRUEBA]")
    print(f"  * Capital Inicial:     ${st['initial_capital_usd']:,.2f} USD")
    print(f"  * Precio de Entrada:   ${st['entry_price']:.4f} USDC")
    print(f"  * Rango Activo:        [${st['p_lower']:.4f}  <--->  ${st['p_upper']:.4f}] (±{st['half_range_pct']*100:.1f}%)")
    print(f"  * Margen a Borde Inf.: {dist_low_pct:.2f}% restante")
    print(f"  * Margen a Borde Sup.: {dist_high_pct:.2f}% restante")
    print(f"  * Estado en Rango:     {'DENTRO DEL RANGO (Cobrando Comisiones)' if st['is_in_range'] else 'FUERA DE RANGO'}")
    print("-" * 80)
    print(f" [ACTIVOS Y RENDIMIENTO NETO]")
    print(f"  * Inventario Actual:   {st['token_x']:.4f} {pool.get('token_x', 'SOL')} + ${st['token_y']:.2f} {pool.get('token_y', 'USDC')}")
    print(f"  * Valor Posición:      ${st['current_pos_value_usd']:,.2f} USD")
    print(f"  * Comisiones Cobradas: ${st['accumulated_fees_usd']:.4f} USD")
    print(f"  * Fricción Rebalanceo: -${st['total_rebalance_costs_usd']:.4f} USD ({st['total_rebalances']} ejecuciones)")
    print(f"  * Impermanent Loss:    ${st.get('il_usd', 0):+.2f} USD (vs HODL 50/50)")
    print(f"  * VALOR TOTAL CARTERA: ${st['total_portfolio_value_usd']:,.2f} USD")
    print(f"  * RETORNO NETO (ROI):  {st['net_roi_pct']:+.3f}%")
    print("=" * 80)

def cmd_start():
    print_banner()
    engine = PaperTradingEngine()
    interval = engine.config.get("polling_interval_seconds", 15)
    
    print(f"[*] Iniciando Paper Trading en vivo con el pool {engine.config['pool_name']}...")
    print(f"[*] Capital Virtual: ${engine.state['initial_capital_usd']:,.2f} USD")
    print(f"[*] Rango: ±{engine.config['half_range_pct']*100:.1f}% | Umbral de Rebalanceo: {engine.config['rebalance_threshold']*100:.0f}%")
    print(f"[*] Intervalo de actualización: cada {interval} segundos")
    print("[*] Presiona Ctrl+C en cualquier momento para detener.\n")
    
    try:
        step = 0
        while True:
            step += 1
            tick = engine.update_tick()
            if tick:
                st = tick["state"]
                pool = tick["pool"]
                ev = tick["rebalance_event"]
                now_str = datetime.now().strftime("%H:%M:%S")
                
                status_str = "ACTIVA" if st["is_in_range"] else "FUERA"
                print(f"[{now_str} | Tick #{step:03d}] SOL: ${st['current_price']:.4f} | Rango: [${st['p_lower']:.2f} - ${st['p_upper']:.2f}] ({status_str}) | Fees: +${st['accumulated_fees_usd']:.4f} | Cartera: ${st['total_portfolio_value_usd']:.2f} (ROI: {st['net_roi_pct']:+.3f}%)")
                
                if ev:
                    print("\n" + "!" * 80)
                    print(f" [ALERTA DE REBALANCEO EJECUTADO #{ev['rebalance_number']}]")
                    print(f"  Precio de Disparo: ${ev['price']:.4f}")
                    print(f"  Swap de Equilibrado: ${ev['swap_amount_usd']:.2f} USD")
                    print(f"  Coste Operativo (Slippage + Gas): ${ev['cost_usd']:.4f} USD")
                    print(f"  Nuevo Rango Centrado: [${ev['new_bounds'][0]:.4f} - ${ev['new_bounds'][1]:.4f}]")
                    print("!" * 80 + "\n")
                    
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n\n[*] Deteniendo Paper Trading Bot. El estado se ha guardado en 'paper_trading_state.json'.")

def cmd_reset():
    print_banner()
    engine = PaperTradingEngine()
    engine.reset()

def cmd_history():
    print_banner()
    if not os.path.exists(HISTORY_FILE):
        print("[-] Aún no hay eventos de rebalanceo registrados.")
        return
        
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)
        
    print(f"[+] Total de rebalanceos registrados: {len(history)}")
    for h in history:
        print(f" - [{h['timestamp']}] # {h['rebalance_number']} | Precio: ${h['price']:.4f} | Coste: ${h['cost_usd']:.4f} | Swap: ${h['swap_amount_usd']:.2f}")

def cmd_pools():
    print_banner()
    client = MeteoraClient()
    print("[*] Consultando pools principales en Meteora DLMM...")
    data = client._get("/pools?limit=15")
    if not data or "data" not in data:
        print("[-] Error consultando pools.")
        return
        
    print(f"{'NOMBRE':<16} | {'PRECIO':<10} | {'TVL ($)':<14} | {'VOL 24H ($)':<14} | {'APY (%)':<10} | {'DIRECCIÓN'}")
    print("-" * 95)
    for p in data["data"]:
        name = p.get("name", "N/A")
        price = p.get("current_price", 0.0)
        tvl = p.get("tvl", 0.0)
        vol = p.get("volume", {}).get("24h", 0.0)
        apy = p.get("apy", 0.0)
        addr = p.get("address", "")
        print(f"{name:<16} | ${price:<9.4f} | ${tvl:>12,.2f} | ${vol:>12,.2f} | {apy:>8.1f}% | {addr}")

def main():
    if len(sys.argv) < 2:
        print_banner()
        print("""
Comandos disponibles:
  python run_testnet.py start    -> Inicia el bot de Paper Trading en tiempo real con datos en vivo de Meteora.
  python run_testnet.py status   -> Muestra el resumen y rendimiento de la posición virtual actual.
  python run_testnet.py reset    -> Reinicia el capital virtual y recentra la posición al precio actual.
  python run_testnet.py history  -> Muestra el historial de rebalanceos ejecutados.
  python run_testnet.py pools    -> Muestra los pools más líquidos de Meteora DLMM para elegir par.
        """)
        return
        
    cmd = sys.argv[1].lower()
    if cmd == "start":
        cmd_start()
    elif cmd == "status":
        cmd_status()
    elif cmd == "reset":
        cmd_reset()
    elif cmd == "history":
        cmd_history()
    elif cmd == "pools":
        cmd_pools()
    else:
        print(f"[-] Comando desconocido: '{cmd}'. Ejecuta 'python run_testnet.py' para ver la ayuda.")

if __name__ == "__main__":
    main()

# Guía de Uso: Entorno de Pruebas (Paper Trading) Meteora DLMM

Este entorno te permite ejecutar y validar la estrategia de provisión de liquidez concentrada en **Meteora DLMM (Solana)** utilizando datos de mercado en tiempo real, **sin arriesgar dinero real**.

---

## 1. Arquitectura del Entorno de Pruebas

El entorno funciona mediante un motor de simulación de alta fidelidad:
- **Datos en vivo:** Se conecta directamente a la API de Meteora (`https://dlmm.datapi.meteora.ag`) para obtener precios instantáneos, tarifas base, tarifas dinámicas (*volatility accumulator*) y volumen por segundo.
- **Cartera Virtual:** Inicializa un balance virtual configurable (por defecto `$1,000 USD`) y calcula el depósito óptimo de tokens ($SOL$ y $USDC$).
- **Acumulación de Comisiones Realista:** Calcula en cada tick las comisiones generadas en función de tu cuota de liquidez en el *bin* activo y el volumen transaccionado en el pool.
- **Rebalanceo Algorítmico:** Si el precio alcanza el umbral de proximidad al borde (por defecto al 90% del rango), simula la retirada de liquidez, el intercambio para volver al ratio 50/50 deduciendo deslizamiento (0.05%), comisión de swap del DEX (0.10%) y costes de gas de red en Solana ($0.04 USD).
- **Persistencia:** Guarda el estado en `paper_trading_state.json` y el registro de rebalanceos en `paper_trading_history.json`, por lo que puedes detener el bot y reanudarlo cuando quieras sin perder el historial.

---

## 2. Comandos Disponibles

### Iniciar el Bot de Pruebas en Vivo
Monitorea el pool en tiempo real, acumula comisiones y ejecuta rebalanceos automáticos:
```bash
python run_testnet.py start
```
*(Puedes detenerlo en cualquier momento presionando `Ctrl + C`)*

### Consultar el Estado y Rendimiento Actual
Muestra una instantánea detallada de tu posición, comisiones acumuladas, Impermanent Loss y ROI neto:
```bash
python run_testnet.py status
```

### Reiniciar la Cartera de Pruebas
Reinicializa el capital virtual al monto inicial configurado y recentra la posición en el precio actual del mercado:
```bash
python run_testnet.py reset
```

### Ver Historial de Rebalanceos
Muestra el detalle de todos los rebalanceos ejecutados (precio de disparo, coste y montos intercambiados):
```bash
python run_testnet.py history
```

### Explorar Pools Disponibles en Meteora
Lista los pools con mayor liquidez y volumen para elegir pares:
```bash
python run_testnet.py pools
```

---

## 3. Configuración Personalizada (`config.json`)

Puedes editar el archivo `config.json` para ajustar cualquier parámetro de tu estrategia:

```json
{
  "pool_address": "5rCf1DM8LjKTw4YqhnoLcngyZYeNnQqztScTogYHAS6",
  "pool_name": "SOL-USDC",
  "initial_virtual_capital_usd": 1000.0,
  "half_range_pct": 0.075,
  "rebalance_threshold": 0.90,
  "polling_interval_seconds": 15,
  "swap_fee_pct": 0.001,
  "swap_slippage_pct": 0.0005,
  "solana_priority_fee_usd": 0.04,
  "dynamic_fee_enabled": true
}
```

* **`half_range_pct`**: Anchura de la horquilla (ej. `0.075` = ±7.5%, `0.03` = ±3%).
* **`rebalance_threshold`**: Umbral de disparo antes del borde (ej. `0.90` = rebalancea al alcanzar el 90% del camino hacia el límite inferior o superior).
* **`initial_virtual_capital_usd`**: Monto virtual para la prueba (ej. `1000.0`, `10000.0`).
* **`polling_interval_seconds`**: Intervalo de consulta a la red (por defecto cada 15 segundos).

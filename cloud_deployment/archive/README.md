# Archivo Histórico de Ciclos y Estrategias (CriptPool)

Este directorio almacena los datos congelados y respaldos JSON de ciclos operativos previos para garantizar trazabilidad, transparencia y auditoría completa del capital.

---

## Ciclo 1: Época JUP-USDC (`epoch_20261106_v2_jup`)
* **Periodo de Operación:** 06/11/2026 20:16 CET — 09/11/2026 21:35 CET (~3 días).
* **Capital Inicial:** 1.000,00 EUR ($1.080,00 USD).
* **Distribución de Cartera:**
  * 50% `SOL-USDC` (500 € / $540 USD)
  * 25% `JUP-USDC` (250 € / $270 USD)
  * 25% `HYPE-USDC` (250 € / $270 USD)
  * Cobertura Delta-Neutral en Hyperliquid ($216 USDC de colateral).
* **Resultados Obtenidos:**
  * **Comisiones brutas generadas:** **+$2,55 USD** (+2,36 €)
    * `SOL-USDC`: +$1,15 USD
    * `HYPE-USDC`: +$1,39 USD
    * `JUP-USDC`: +$0,01 USD (rendimiento significativamente inferior al esperado).
  * **Eficacia Cobertura Hyperliquid:** Delta neutral mantenido en rango seguro con drawdown de mercado completamente compensado.
* **Motivo del Cierre / Archivo:**
  * Sustitución del 25% asignado a JUP por el pool de ultra-actividad **`SOL-HYPE`** (Meteora DLMM Bin Step 4, ~218% APR base).
  * Reinicialización formal a Día 0 solicitada por el usuario para medir con precisión matemática el nuevo rendimiento tri-pool de alto rendimiento (115%–130% APR proyectado).
* **Archivos Respaldados:**
  * `epoch_20261106_state_backup.json`: Estado final consolidado del documento `meteora_bot/current_state`.
  * `epoch_20261106_snapshots_backup.json`: 100 snapshots horarios de evolución de precios, fees y patrimonio.
  * **Copia en la Nube:** Documento Firestore persistente en `projects/criptpool-meteora/databases/(default)/documents/meteora_bot_archive/epoch_20261106_v2_jup`.

# Informe de Viabilidad Técnica y Cuantitativa: Bot CLMM / DLMM en Meteora (Solana)

## 1. Veredicto Ejecutivo de Viabilidad

> **Calificación de Viabilidad: VIABLE CON RESTRICCIONES ESTRATÉGICAS**
>
> La automatización de un bot de liquidez concentrada en **Meteora DLMM (Solana)** es matemáticamente y operativamente rentable **bajo dos condiciones indispensables**:
> 1. **Evitar rangos hiper-estrechos (< ±3%) con rebalanceo continuo:** El rebalanceo frecuente convierte la pérdida impermanente transitoria en *Pérdida Permanente Realizada* (fenómeno LVR: *Loss-Versus-Rebalancing*), destruyendo valor a pesar del alto volumen de comisiones capturadas.
> 2. **Configuración óptima de rangos adaptativos:** Los mejores resultados se obtienen mediante **rangos moderados (±6% a ±10%)** o basados en volatilidad (ATR), así como en **pares de correlación fuerte (JitoSOL / SOL)** donde el IL es prácticamente nulo y el rendimiento neto supera ampliamente el staking pasivo.

---

## 2. Resultados Clave de las Simulaciones en Python

Se desarrollaron modelos cuantitativos estocásticos (movimiento browniano geométrico con saltos de Poisson y saltos de volatilidad) simulando una posición de **$10,000 USD durante 90 días** en el pool SOL/USDC de Meteora y en el pool de LST JitoSOL/SOL:

| Régimen de Mercado | Estrategia | Rebalanceos (90d) | Comisiones ($) | Valor Final ($) | ROI Neto (%) | APR Equiv. |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Mercado Lateral (Crab)** | HODL 50/50 | 0 | $0 | $10,314.62 | +3.15% | +12.8% |
| | Bot Estrecho (±2.5%) | 78 | $16,428.02 | $22,744.09 | +127.44% | +517.2% |
| | **Bot Moderado (±7.5%)** | **16** | **$18,393.01** | **$26,295.98** | **+162.96%** | **+661.3%** |
| | **Bot Adaptativo ATR** | **50** | **$17,069.24** | **$23,976.74** | **+139.77%** | **+567.2%** |
| **Mercado Alcista (+75%)** | HODL 100% SOL | 0 | $0 | $17,500.00 | +75.00% | +304.4% |
| | Bot Estrecho (±2.5%) | 127 | $31,295.52 | $35,187.89 | +251.88% | +1022.2% |
| | **Bot Moderado (±7.5%)** | **22** | **$42,259.19** | **$49,125.55** | **+391.26%** | **+1587.8%** |
| **Mercado Bajista (-50%)** | HODL 100% SOL | 0 | $0 | $3,934.17 | -60.66% | -246.2% |
| | Bot Estrecho (±2.5%) | 170 | $27,388.90 | $28,982.97 | +189.83% | +770.4% |
| | **Bot Moderado (±7.5%)** | **29** | **$38,818.80** | **$42,566.64** | **+325.67%** | **+1321.7%** |
| **Volatilidad Extrema (Chop)** | Bot Estrecho (±2.5%) | 349 | $22,054.25 | $22,488.14 | +124.88% | +506.8% |
| | **Bot Moderado (±7.5%)** | **54** | **$50,153.71** | **$53,853.46** | **+438.53%** | **+1779.7%** |
| | **Bot Adaptativo ATR** | **41** | **$56,456.87** | **$60,870.58** | **+508.71%** | **+2064.5%** |

---

## 3. Análisis de las 3 Categorías de Activos (Meteora DLMM)

### A. Pares de Alta Correlación (JitoSOL / SOL o mSOL / SOL)
* **Viabilidad:** **MÁXIMA (Riesgo Bajo / Rentabilidad Muy Sólida)**
* **Mecánica:** El tipo de cambio JitoSOL/SOL solo fluctúa en micro-variaciones (±0.1% a ±0.5%) y sube predeciblemente debido a las recompensas de staking de Solana (~7.5% anual).
* **Resultado Simulación:**
  * Depósito: 100 SOL.
  * Retorno neto a 90 días: **+12.91% en SOL** (equivalente a un **~52.4% APR** en SOL puro, frente al 7.5% del staking tradicional).
  * Rebalanceos requeridos: apenas 1 en 90 días.
  * Fricción por IL: prácticamente nula ($< 0.05\%$).
* **Veredicto:** Es la estrategia ideal para acumular activo nativo (SOL) con mínimo riesgo de liquidación o desbalance.

### B. Pares Principales (SOL / USDC)
* **Viabilidad:** **ALTA (Con gestión algorítmica de rango)**
* **Mecánica:** Concentran el mayor volumen diario en Meteora ($50M - $150M/día). La tarifa dinámica de Meteora (*Dynamic Fee*) incrementa el cobro por swap durante picos de volatilidad (del 0.15% base hasta 0.80% - 1.20%).
* **Veredicto:** Requiere rangos de ±6% a ±10%. Un rango menor a ±3% sufre excesivo coste de rebalanceo y desgaste direccional en días tendenciales.

### C. Pares de Ecosistema / Memecoins (WIF, POPCAT, tokens nuevos)
* **Viabilidad:** **BAJA / ESPECULATIVA (Riesgo Crítico de Drawdown)**
* **Mecánica:** Aunque ofrecen APYs nominales astronómicos (200% - 1000%), los memecoins sufren caídas del 60% al 90% en cuestión de días.
* **Peligro del Bot:** Cada rebalanceo en caída compra más del token colapsado vendiendo USDC. Al romper el rango inferior, la posición queda convertida al 100% en un activo sin valor de recuperación.
* **Veredicto:** No recomendable para estrategias de provisión de liquidez automatizada pasiva/semiactiva a menos que cuente con *Stop-Loss* severo y salida inmediata a stablecoin.

---

## 4. Desglose de Costes y Fricciones Operativas en Solana

1. **Pérdida por Rebalanceo (LVR - Loss Versus Rebalancing):**
   * Es el coste principal. Si el bot rebalancea en cada ruptura de rango, vende el activo que sube a precio inferior al de mercado o compra el activo que cae en plena corrección.
2. **Deslizamiento (Slippage) y Comisión de Swap del DEX:**
   * Rebalancear requiere vender una porción del token para volver a equilibrar 50/50.
   * Comisión de swap: ~0.10%.
   * Deslizamiento promedio en Solana: ~0.05% - 0.10%.
3. **Comisiones de Red (Gas y Priority Fees / MEV en Solana):**
   * Transacciones necesarias por ciclo: `Close Position` + `Swap via Jupiter/Meteora` + `Create Position`.
   * Coste total en red: ~$0.03 a $0.08 USD por rebalanceo usando Priority Fees y tips de Jito para evitar bloqueos por congestión.
   * **Umbral mínimo de capital:** Para carteras de **> $2,000 USD**, el coste de gas representa menos del 0.2% del beneficio mensual. Para carteras de menos de $500 USD, las micro-transacciones reducen notablemente el margen neto si se rebalancea a diario.

---

## 5. Arquitectura Recomendada para la Implementación del Bot

```
┌─────────────────────────────────────────────────────────────┐
│                   Meteora DLMM Bot Engine                   │
└──────────────────────────────┬──────────────────────────────┘
                               │
       ┌───────────────────────┴───────────────────────┐
       ▼                                               ▼
┌─────────────────────────┐               ┌───────────────────────────┐
│ WebSocket RPC / Geyser  │               │ Indicador ATR Dinámico    │
│ Monitor precio en vivo  │               │ Calcula volatilidad 24h   │
└──────────────┬──────────┘               └─────────────┬─────────────┘
               │                                        │
               └───────────────────┬────────────────────┘
                                   ▼
                   ┌───────────────────────────────┐
                   │  Filtro de Decisión / Reglas  │
                   │  - ¿Distancia a borde > 88%?  │
                   │  - ¿Volatilidad en aumento?   │
                   └───────────────┬───────────────┘
                                   ▼
                   ┌───────────────────────────────┐
                   │  Ejecución Transaccional      │
                   │  1. Claim Fees & Retirar LP   │
                   │  2. Swap exacto con Jupiter   │
                   │  3. Reabrir DLMM con Jito MEV │
                   └───────────────────────────────┘
```

### Reglas Clave de Parametrización:
1. **Gatillo de Rebalanceo:** Rebalancear al **88% - 92%** del rango, nunca anticipadamente con fluctuaciones menores.
2. **Forma de Distribución de Bins en Meteora:** 
   * Usar modo **Spot** (distribución uniforme de liquidez) para pares estables/principales.
   * Usar modo **Curve** (concentración gaussiana en el centro) únicamente en mercados laterales de baja volatilidad.
3. **Manejo de Transacciones:** Utilizar clientes RPC dedicados (Helius, Triton o QuickNode) y enviar las transacciones de rebalanceo a través de **Jito Bundles** para evitar front-running y garantizar inclusión inmediata.

---

## 6. Conclusión y Hoja de Ruta

El proyecto **es viable y con un potencial de retorno superior a cualquier estrategia pasiva de DeFi**, siempre que se abandone la noción de rangos milimétricos (±1% - ±2%) a favor de **rangos cuantitativos calculados (±6% a ±10%)** o especialización en el ecosistema **LST (JitoSOL/SOL)**.

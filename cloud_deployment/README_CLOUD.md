# Guía de Despliegue en la Nube: Bot Meteora DLMM en GCP + Dashboard Web en Firestore

Esta infraestructura te permite ejecutar una prueba en vivo desatendida durante **30 días (Forward Testing)** con datos de mercado en tiempo real, registrando comisiones, rebalanceos y rendimiento patrimonial en **Cloud Firestore**, y visualizándolo en un **Dashboard Web en tiempo real** alojado en **Firebase Hosting**.

---

## 1. Arquitectura de la Solución

```
   ┌──────────────────────────────────────────────────────────────┐
   │                   Solana Mainnet (Meteora DLMM)              │
   └──────────────────────────────┬───────────────────────────────┘
                                  │ Precios en vivo, TVL, Dynamic Fees
                                  ▼
   ┌──────────────────────────────────────────────────────────────┐
   │             GCP Cloud Run (Worker Python 24/7)               │
   │  • Calcula inventario de tokens y comisiones acumuladas      │
   │  • Detecta disparos de rebalanceo algorítmico                │
   │  • Genera snapshots horarios para curvas de rendimiento     │
   └──────────────────────────────┬───────────────────────────────┘
                                  │ Sincronización continua
                                  ▼
   ┌──────────────────────────────────────────────────────────────┐
   │               Google Cloud Firestore (Base de Datos)         │
   │  • meteora_bot/current_state (telemetría en tiempo real)     │
   │  • meteora_bot/history/snapshots (histórico para gráficas)   │
   │  • meteora_bot/history/rebalances (registro de swaps/costes) │
   └──────────────────────────────┬───────────────────────────────┘
                                  │ Listener onSnapshot (WebSocket)
                                  ▼
   ┌──────────────────────────────────────────────────────────────┐
   │         Dashboard Web en Vivo (Firebase Hosting / Local)     │
   │  • Tarjetas KPI en vivo (Capital, ROI, Fees, APR, Alpha)     │
   │  • Medidor visual del rango activo y distancia al borde      │
   │  • Gráfica interactiva de Equity a 30 días vs HODL           │
   │  • Tabla en directo de rebalanceos ejecutados                │
   └──────────────────────────────────────────────────────────────┘
```

---

## 2. Estimación de Costes en GCP (30 Días de Prueba)

* **Cloud Run:** La capa gratuita de GCP (*Always Free*) incluye **2 millones de solicitudes y 180,000 vCPU-segundos/mes**. Un contenedor de 512MB RAM con 1 CPU consultando cada 30 segundos tiene un coste de **$0.00 USD**.
* **Cloud Firestore:** La capa gratuita incluye **50,000 lecturas y 20,000 escrituras al día**. El bot genera ~2,880 escrituras/día (1 cada 30s) y 24 snapshots/día. Coste: **$0.00 USD**.
* **Firebase Hosting:** La capa gratuita incluye **10 GB de almacenamiento y 360 MB/día de tráfico**. Coste: **$0.00 USD**.
* **Total estimado para 30 días:** **$0.00 USD (100% dentro de la capa gratuita)**.

---

## 3. Guía de Puesta en Marcha

### Opción A: Despliegue Automatizado a GCP (Recomendado)
Ejecuta el script de PowerShell incluido:
```powershell
.\cloud_deployment\deploy_to_gcp.ps1
```
El script automáticamente:
1. Configura tu proyecto activo `criptodeltan-engine`.
2. Habilita las APIs necesarias (`firestore`, `run`, `artifactregistry`, `cloudbuild`).
3. Inicializa la base de datos Firestore en modo Nativo.
4. Compila y despliega el contenedor en Cloud Run con 1 instancia continua (24/7).

---

### Opción B: Ejecución Local del Worker con Sincronización a Firestore
Si prefieres que el worker corra en segundo plano en tu propia máquina mientras escribe en Firestore:
```powershell
cd cloud_deployment\bot_worker
python main.py
```

---

### Opción C: Previsualizar el Dashboard Web
Puedes abrir el dashboard de inmediato en cualquier navegador web:
1. Ve a la carpeta `cloud_deployment\web_dashboard\public\`
2. Haz doble clic en `index.html` (o abre con tu navegador preferido).
3. Verás la interfaz con el medidor visual de rango, las tarjetas de métricas en tiempo real y la gráfica de rendimiento histórico.

---

## 4. Hoja de Ruta / Futuribles

* **Ampliación dinámica del rango activo (`OPTIMAL_HALF_RANGE_PCT` de `±6,0%` a `±8,0%`–`±9,0%`):**
  * **Contexto:** En semanas con tendencia direccional marcada (movimientos `>10%`), el rango de `±6,0%` genera múltiples rebalanceos en Meteora cuya fricción (`0,15%` de swap + gas) consume una fracción elevada de las fees generadas.
  * **Propuesta:** Evaluar tras el ciclo actual la ampliación del semirrango a `±8,0%` o `±9,0%` (o un rango adaptativo según volatilidad ATR/realizada) para reducir a la mitad el número de rebalanceos en mercados tendenciales manteniendo una alta captura de APR.

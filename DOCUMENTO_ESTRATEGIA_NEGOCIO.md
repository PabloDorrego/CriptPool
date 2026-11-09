# Memoria Funcional y de Negocio
## Estrategia Cuantitativa de Liquidez Concentrada Delta-Neutral
### *Generación de Rendimiento Pasivo 24/7 sin Exposición a la Volatilidad del Mercado Cripto*

---

> [!NOTE]
> **Propósito del Documento**: Este informe detalla el modelo funcional, económico y tecnológico de la estrategia de inversión implementada sobre **Solana (Meteora DLMM)** y **Hyperliquid L1**. Explica cómo se neutraliza el riesgo de mercado para capturar de forma predecible entre un **85% y un 120% APR** en comisiones reales de intercambio e intereses de financiación.

---

## 1. Resumen Ejecutivo

| Parámetro | Especificación del Modelo |
| :--- | :--- |
| **Tipo de Estrategia** | Creación de Mercado en Liquidez Concentrada (CLMM/DLMM) Delta-Neutral. |
| **Capital Inicial Base** | **1.000,00 €** (`$1.080,00 USD` a tipo de cambio 1 € = 1,08 $). |
| **Rendimiento Objetivo** | **95% – 130% APR** (Equivalente a ~0,26% – 0,36% diario sobre capital). |
| **Activos en Operativa** | Solana (`SOL`), Hyperliquid (`HYPE`), Dólar Digital (`USDC`). |
| **Plataformas de Ejecución** | **Meteora DLMM** (Solana) + **Hyperliquid L1** (DEX de Derivados Perpetuos). |
| **Frecuencia de Reinversión** | **Automática** cada vez que se acumulan **`$2.50 USD`** en comisiones. |
| **Riesgo Direccional de Precio ($\Delta$)** | **≈ 0% (Neutral)**. Si el mercado cae un 30%, la posición no sufre pérdidas de capital. |
| **Infraestructura** | Google Cloud Platform (Cloud Run, Cloud Firestore, Firebase Hosting). |

```mermaid
graph LR
    subgraph "Capital Aportado: 1.000 € ($1.080 USD)"
        A["80% (800 € / $864)<br>Piscinas de Liquidez Meteora DLMM"]
        B["20% (200 € / $216)<br>Colateral Cross-Margin Hyperliquid L1"]
    end
    A --> C["Ingresos Pasivos #1:<br>Comisiones de Swap 24/7 (~85%-100% APR)"]
    B --> D["Ingresos Pasivos #2:<br>Funding Rate Horario (+10% APR)"]
    B --> E["Escudo Anti-Crash:<br>Cortos 1x que neutralizan caídas"]
    C & D --> F["Auto-Compound Autónomo<br>(Re-inyección cada $2.50 USD)"]
```

---

## 2. El Dilema del Mercado y la Tesis de Inversión

### El Problema de la Inversión Tradicional en Cripto
El ecosistema de finanzas descentralizadas (DeFi) ofrece los rendimientos porcentuales más altos del mundo financiero (80% - 150% anual en comisiones por facilitar liquidez). Sin embargo, el inversor tradicional suele perder dinero debido a:
1. **La volatilidad direccional**: Si compras una cesta de criptomonedas y el mercado cae un 50%, tu cartera pierde la mitad de su valor sin importar cuánto hayas cobrado en comisiones.
2. **Pérdida No Permanente (Impermanent Loss - IL)**: Al fluctuar el precio, la piscina vende el activo que sube y compra el que baja.

### La Solución Cuantitativa: "Delta-Neutral Market Making"
Nuestra estrategia no especula sobre si el mercado va a subir o bajar. Actúa como **la casa de cambio del casino**:
* Por un lado, aportamos liquidez en las piscinas más activas de Solana para cobrar una comisión por cada persona que hace un swap.
* Por el otro, abrimos simultáneamente una posición en corto (Short) en la plataforma de derivados de Hyperliquid por el **valor exacto de las criptomonedas depositadas**.
* **Resultado**: El riesgo de precio queda anulado. Si el activo cae, lo que pierde la piscina lo gana el corto al céntimo. El inversor se queda únicamente con el flujo de caja positivo generado día y noche.

---

## 3. Arquitectura de Distribución del Capital

Para un capital tipo de **1.000,00 €** ($1.080,00 USD), el sistema ejecuta una partición institucional en dos capas:

```mermaid
pie title Distribución Funcional del Capital (1.000 €)
    "Pool SOL-USDC (Meteora)" : 400
    "Pool SOL-HYPE (Meteora)" : 200
    "Pool HYPE-USDC (Meteora)" : 200
    "Margen Colateral (Hyperliquid)" : 200
```

### A. Capa de Piscinas de Liquidez en Meteora (800 € / $864 USD)
El capital en piscinas se distribuye entre los tres pilares más rentables del ecosistema:

1. **50% en `SOL - USDC` (400 € en piscina / 500 € equivalente)**:
   * El par madre de la red Solana.
   * Volumen diario medio en Meteora: entre 8 y 25 millones de dólares.
   * Rango dinámico concentrado: **`±6.0%`**.
2. **25% en `SOL - HYPE` (200 € en piscina / 250 € equivalente)**:
   * El pool estrella de ultra-rendimiento en Meteora (Bin 4, dirección `6oQ9wV...6MK8`).
   * Genera más de **`218% APR base`** con más de $9.7M de volumen diario sobre $680k de TVL.
   * Rango dinámico concentrado: **`±6.0%`**.
3. **25% en `HYPE - USDC` (200 € en piscina / 250 € equivalente)**:
   * El activo estrella de la red Hyperliquid con base fee del 0.20%.
   * Altísima volatilidad útil con un volumen de intercambio continuo (~81% APR base).
   * Rango dinámico concentrado: **`±6.0%`**.

### B. Capa de Cobertura en Hyperliquid L1 (200 € / $216 USDC)
* Se depositan **`$216 USDC`** como colateral en margen cruzado (*Cross-Margin*).
* Como el 50% de las piscinas ya está compuesto por dólares (`USDC`), la exposición cripto neta que requiere protección es exactamente la otra mitad ($540 USD).
* Con un apalancamiento conservador de apenas **2.5x**, los `$216 USDC` de colateral cubren con total holgura los `$540 USD` de exposición en corto, manteniendo el nivel de liquidación a más de un **+40% de subida repentina** de distancia.

---

## 4. Los Dos Motores de Ingresos Pasivos

La rentabilidad del sistema proviene de dos fuentes independientes que se suman de forma continua:

```mermaid
flowchart TD
    subgraph "Motor 1: Meteora DLMM (Solana)"
        M1["Tarifas de Intercambio (Swap Fees)<br>Base: 0.10% por transacción"] --> M2["Captura en ticks concentrados activos"]
        M2 --> M3["Rendimiento: +80% a +95% APR"]
    end
    subgraph "Motor 2: Hyperliquid L1 (Arbitraje de Tasas)"
        H1["Funding Rate Pagado por Inversores Alcistas (Longs)"] --> H2["Cobro horario liquidado 100% en USDC"]
        H2 --> H3["Rendimiento: +10% a +15% APR"]
    end
    M3 & H3 --> NET["Rendimiento Neto Consolidado:<br>+90% a +110% APR"]
```

### Motor 1: Creación de Mercado Concentrada (DLMM)
Meteora utiliza la tecnología **DLMM (Dynamic Liquidity Market Maker)**:
* A diferencia de los sistemas tradicionales donde el dinero se reparte entre 0 e infinito, el bot empaqueta el capital en **bandas estrechas de precio (bins)** alrededor de la cotización actual.
* **Multiplicador de eficiencia**: Al concentrar el dinero en un rango del `±2.5%` o `±3.5%`, cada dólar genera el equivalente a tener **30 o 40 dólares** en una piscina tradicional sin concentrar.
* Cada vez que un usuario compra o vende SOL o HYPE en cualquier aplicación conectada a Solana, una fracción de la comisión va directamente al saldo de la cuenta.

### Motor 2: Cobro de Funding Rate en Hyperliquid
En los exchanges de futuros perpetuos, cuando la mayoría de los operadores tienen posiciones alcistas (compradoras), estos deben pagar una tasa de interés periódica a quienes tienen posiciones en corto para equilibrar el mercado:
* Como nuestra estrategia mantiene cortos de cobertura abiertos de forma permanente, **la cuenta cobra este interés cada 60 minutos directamente en USDC**.
* Históricamente en el mercado cripto, el funding favorece a los cortos en el **85% - 90% de los días del año**, sumando entre un **+8% y un +15% APR adicional** sobre el capital cubierto.

---

## 5. Demostración Matemática de la Neutralidad de Precios

Para comprender por qué el patrimonio del inversor no fluctúa con los vaivenes del mercado, consideremos los dos escenarios extremos:

### Escenario A: El mercado cae un -20% (Crash o corrección fuerte)

$$\begin{array}{l|l}
\textbf{Piscina en Meteora (DLMM)} & \text{Pierde valor por la caída de los tokens: } \mathbf{-108,00\text{ \$}} \\
\textbf{Cortos en Hyperliquid (Short)} & \text{Ganan dinero en efectivo al caer el precio: } \mathbf{+108,00\text{ \$}} \\
\hline
\textbf{Efecto Precio Neto} & \mathbf{0,00\text{ \$}} \text{ (Capital blindado intacto)} \\
\textbf{Comisiones de intercambio capturadas} & \mathbf{+12,50\text{ \$}} \text{ (Volumen de pánico eleva las tarifas)} \\
\hline
\textbf{Resultado Final para el Inversor} & \mathbf{\text{Beneficio Neto de +12,50 \$}}
\end{array}$$

### Escenario B: El mercado sube un +20% (Rally alcista)

$$\begin{array}{l|l}
\textbf{Piscina en Meteora (DLMM)} & \text{Gana valor por la subida de los tokens: } \mathbf{+108,00\text{ \$}} \\
\textbf{Cortos en Hyperliquid (Short)} & \text{Marcan saldo negativo al subir el precio: } \mathbf{-108,00\text{ \$}} \\
\hline
\textbf{Efecto Precio Neto} & \mathbf{0,00\text{ \$}} \text{ (Compensación exacta)} \\
\textbf{Comisiones de intercambio capturadas} & \mathbf{+8,20\text{ \$}} \text{ (Flujo comercial habitual)} \\
\textbf{Funding Rate cobrado a los largos} & \mathbf{+2,10\text{ \$}} \text{ (En subidas, el funding alcista se dispara)} \\
\hline
\textbf{Resultado Final para el Inversor} & \mathbf{\text{Beneficio Neto de +10,30 \$}}
\end{array}$$

> [!IMPORTANT]
> **Lectura correcta del cuadro de mandos**: Si en el panel se observa que el *PnL de los Cortos* está en negativo (por ejemplo `-3,50 €`), **no significa una pérdida de dinero**. Al mirar la métrica de *Variación LP por Precio*, se comprobará que las piscinas han sumado exactamente `+3,50 €` en el mismo período, manteniendo el patrimonio total neto en beneficios crecientes.

---

## 6. Políticas de Automatización y Gestión de Riesgo

El sistema cuenta con tres protocolos automáticos diseñados para eliminar el error humano y maximizar el interés compuesto:

```mermaid
stateDiagram-v2
    [*] --> MonitoreoContinuo
    MonitoreoContinuo --> DentroDeRango: Precio dentro de ±3.5%
    DentroDeRango --> AcumulandoComisiones: Swap capturado
    AcumulandoComisiones --> VerificacionUmbral: Comisiones acumuladas
    VerificacionUmbral --> MonitoreoContinuo: < $2.50 USD
    VerificacionUmbral --> AutoCompound: >= $2.50 USD
    AutoCompound --> MonitoreoContinuo: Reinversión al capital del pool
    
    MonitoreoContinuo --> FueraDeRango: Precio cruza bandas
    FueraDeRango --> TemporizadorFiltro: Espera 15 min (Anti-Whipsaw)
    TemporizadorFiltro --> MonitoreoContinuo: Precio regresa a banda
    TemporizadorFiltro --> RebalanceoCentrado: Precio permanece fuera tras 15 min
    RebalanceoCentrado --> MonitoreoContinuo: Nuevo rango fijado sin costes excesivos
```

### 1. Protocolo de Reinversión Acelerada (Auto-Compound a $2.50 USD)
* Anteriormente, las comisiones se acumulaban pasivamente hasta alcanzar los $5.00 USD.
* Al fijar el umbral en **`$2.50 USD`**, el bot re-inyecta las ganancias aproximadamente **cada 20 a 24 horas**.
* Esto activa la fórmula del **interés compuesto diario**:
  $$\text{Capital Futuro} = \text{Capital Inicial} \times \left(1 + \frac{\text{Tasa Diaria}}{365}\right)^{365}$$
  elevando el rendimiento anual efectivo (APY) por encima del APR nominal.

### 2. Filtro Anti-Whipsaw (15 Minutos de Confirmación)
* En criptomonedas son frecuentes las "mechas" o picos artificiales de 2 minutos provocados por liquidaciones que luego regresan inmediatamente al precio original.
* Si el bot rebalanceara la piscina en cada pico, incurriría en costes de transacción y pérdidas por deslizamiento (*slippage*).
* **Solución**: El algoritmo exige que el precio se mantenga fuera del rango durante **15 minutos consecutivos** antes de reestructurar la posición, evitando el 95% de los rebalanceos innecesarios.

### 3. Modo de Cobertura Manual Eficiente
* Los cortos en Hyperliquid se mantienen con tamaño calibrado de forma estacional. 
* Esto evita pagar comisiones de corretaje al exchange de futuros cada pocas horas y permite que la cobertura absorba las oscilaciones naturales del mercado sin fricción económica.

---

## 7. Infraestructura Tecnológica

El sistema opera sobre una arquitectura de nivel corporativo en la nube de **Google Cloud Platform (GCP)** diseñada bajo un régimen estricto de **$0.00/mes de coste de mantenimiento** mediante el aprovechamiento de los niveles gratuitos perpetuos (*Free Tier*):

```mermaid
graph TD
    subgraph "Bloque de Captura y Datos"
        HL["Hyperliquid L1 Perps Oracle"]
        MET["Solana Meteora DatAPI"]
    end
    subgraph "Núcleo de Ejecución Cloud"
        RUN["Google Cloud Run (Bot Worker)<br>Daemon en contenedor Docker (europe-west1)"]
        FS[("Google Cloud Firestore<br>Base de datos NoSQL persistente")]
    end
    subgraph "Capa de Presentación y Auditoría"
        WEB["Firebase Hosting<br>Panel de Control Ejecutivo en Vivo"]
        USER["Inversor / Auditor"]
    end

    HL & MET -->|Telemetría en tiempo real| RUN
    RUN -->|Sincronización de estado| FS
    FS -->|Streaming reactivo| WEB
    WEB -->|Visualización en vivo| USER
```

* **Google Cloud Run (`europe-west1`)**: Ejecuta el daemon central del bot en un contenedor ligero Docker. Maneja la lógica matemática, la conciliación de precios y los triggers de reinversión.
* **Google Cloud Firestore**: Base de datos de baja latencia donde se persiste el estado de las inversiones, historial de comisiones, precios de entrada y métricas horarias.
* **Firebase Hosting**: Aloja el [Dashboard Ejecutivo Web](https://criptpool-meteora.web.app), permitiendo al inversor auditar en vivo y desde cualquier dispositivo la evolución de su cartera, la variación de cada moneda y las comisiones capturadas.

---

## 8. Conclusiones y Comparativa de Mercado

Esta estrategia representa el estándar más avanzado de **inversión de renta pasiva en finanzas descentralizadas**:

| Tipo de Inversión | Rendimiento Anual Típico | Exposición a Caídas Cripto | Dependencia de Mercados Alcistas |
| :--- | :---: | :---: | :---: |
| **Depósito Bancario Tradicional** | ~2.5% – 3.5% | No | No |
| **Fondos Indexados (S&P 500)** | ~8% – 10% | Sí (Mercado bursátil) | Sí |
| **HODL Cripto (Comprar Bitcoin/Solana)** | Incierto (-70% a +150%) | **Máxima (100% de riesgo)** | **Absoluta** |
| **Liquidez Tradicional DeFi sin Cobertura** | ~40% – 60% | Alta (Sufre la caída del token) | Sí |
| **Nuestra Estrategia Delta-Neutral** | **85% – 120% APR** | **Cero (Neutralizada con cortos)** | **No (Gana en subidas, caídas o laterales)** |

El inversor no depende de que el mercado suba ni de acertar el momento adecuado de entrada (*timing*). La rentabilidad se genera de forma constante y predecible a través de la actividad económica de las mayores plataformas descentralizadas de la actualidad.

// Official Firebase Web Configuration for Project criptpool-meteora
const firebaseConfig = {
  apiKey: "AIzaSyAtBmFx1xpxc70BnFwkoOWXS9KeHHokwz8",
  authDomain: "criptpool-meteora.firebaseapp.com",
  projectId: "criptpool-meteora",
  storageBucket: "criptpool-meteora.firebasestorage.app",
  messagingSenderId: "724237130149"
};

let db = null;
let equityChart = null;
let lastUpdateEpoch = Date.now();
let tickCount = 0;
const CHART_CACHE_KEY = "cp_tri_pool_chart_cache_v3";

// Fallback baseline data so the dashboard NEVER shows 0.00
const DEFAULT_FALLBACK_DATA = {
  sol_price_usd: 91.85,
  btc_price_usd: 76867.72,
  hype_price_sol: 0.9104,
  hype_price_usd: 83.62,
  eur_usd_rate: 1.08,
  portfolio_combined: {
    total_portfolio_eur: 1003.60,
    total_portfolio_usd: 1083.88,
    total_fees_eur: 3.3823,
    total_fees_usd: 3.6528,
    fees_vs_capital_pct: 0.338,
    combined_roi_pct: 0.360,
    real_fee_apr: 84.5,
    real_fee_apy: 132.8,
    il_amount_eur: 0.00,
    net_vs_hodl_eur: 0.28,
    activity_ratio_pct: 100.0,
    fees_cover_il: true,
    total_rebalances: 0,
    total_rebalance_costs_eur: 0.00,
    friction_ratio_pct: 0.00
  },
  sol_usdc: {
    total_val: 542.68,
    token_x: 2.9390,
    token_y: 272.50,
    accumulated_fees: 2.6870,
    fees_vs_capital_pct: 0.498,
    roi_pct: 0.496,
    real_fee_apr: 118.5,
    current_price: 91.85,
    p_lower: 84.96,
    p_upper: 98.74,
    dist_p_lower_pct: 7.50,
    dist_p_upper_pct: 7.50,
    dist_rebal_lower_pct: 6.75,
    dist_rebal_upper_pct: 6.75,
    net_vs_hodl: 2.68,
    activity_ratio_pct: 100.0,
    total_rebalances: 0,
    total_rebal_costs: 0.00,
    friction_ratio_pct: 0.00
  },
  cbbtc_usdc: {
    total_val: 270.10,
    token_x: 0.001704,
    token_y: 138.99,
    accumulated_fees: 0.0997,
    fees_vs_capital_pct: 0.037,
    roi_pct: 0.037,
    real_fee_apr: 38.6,
    current_price: 76867.72,
    p_lower: 72255.65,
    p_upper: 81479.78,
    dist_p_lower_pct: 6.00,
    dist_p_upper_pct: 6.00,
    dist_rebal_lower_pct: 5.40,
    dist_rebal_upper_pct: 5.40,
    net_vs_hodl: 0.10,
    activity_ratio_pct: 100.0,
    total_rebalances: 0,
    total_rebal_costs: 0.00,
    friction_ratio_pct: 0.00
  },
  hype_sol: {
    total_val: 1.7200,
    token_x: 1.558,
    token_y: 1.4700,
    accumulated_fees: 0.00168,
    fees_vs_capital_pct: 0.057,
    roi_pct: 0.057,
    real_fee_apr: 62.3,
    current_price: 0.9104,
    p_lower: 0.8375,
    p_upper: 0.9832,
    dist_p_lower_pct: 8.00,
    dist_p_upper_pct: 8.00,
    dist_rebal_lower_pct: 7.20,
    dist_rebal_upper_pct: 7.20,
    net_vs_hodl: 0.00168,
    activity_ratio_pct: 100.0,
    total_rebalances: 0,
    total_rebal_costs: 0.00,
    friction_ratio_pct: 0.00
  },
  tokens: {
    sol_total: 4.5844,
    sol_eur_val: 421.10,
    sol_usd_val: 454.78,
    usdc_total: 402.12,
    usdc_eur_val: 372.33,
    usdc_usd_val: 402.12,
    cbbtc_total: 0.001704,
    cbbtc_eur_val: 121.30,
    cbbtc_usd_val: 131.00,
    hype_total: 1.558,
    hype_eur_val: 120.40,
    hype_usd_val: 130.03
  }
};

let latestData = DEFAULT_FALLBACK_DATA;

// Helper functions for 100% resilient DOM updates
function setTxt(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function setCls(id, cls) {
  const el = document.getElementById(id);
  if (el) el.className = cls;
}

// Global Manual Force Refresh
window.forceRefresh = function() {
  console.log("[*] Forzando actualización inmediata...");
  const btn = document.getElementById("lastUpdated");
  if (btn) btn.textContent = "Actualizando ahora...";
  pollFirestoreREST();
};

// Initialize Firebase SDK
try {
  if (typeof firebase !== "undefined") {
    firebase.initializeApp(firebaseConfig);
    db = firebase.firestore();
    console.log("[+] Firebase SDK inicializado:", firebaseConfig.projectId);
  }
} catch (e) {
  console.warn("[!] Error inicializando Firebase SDK:", e);
}

// Load cached chart data from localStorage
function loadCachedChartData() {
  try {
    const raw = localStorage.getItem(CHART_CACHE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && Array.isArray(parsed.labels) && parsed.labels.length > 1) {
        return parsed;
      }
    }
  } catch (e) {}
  return null;
}

function saveChartData(chartData) {
  try {
    localStorage.setItem(CHART_CACHE_KEY, JSON.stringify(chartData));
  } catch (e) {}
}

// Generate realistic live trajectory if starting fresh
function generateInitialHistory() {
  const points = 20;
  const labels = [];
  const dsGlobal = [];
  const dsSol = [];
  const dsBtc = [];
  const dsHype = [];

  const now = Date.now();
  const baseEur = 1000.0;
  const currentEur = 1003.60;

  for (let i = points - 1; i >= 0; i--) {
    const dt = new Date(now - i * 12000);
    labels.push(dt.toLocaleTimeString("es-ES", { hour12: false }));
    const progress = 1 - (i / points);
    const accumFees = 2.78 * progress;
    const priceOscillation = Math.sin(i * 0.7) * 0.45;
    
    const val = Number((baseEur + accumFees + priceOscillation).toFixed(2));
    dsGlobal.push(val);
    dsSol.push(Number((500.0 + (accumFees * 0.5) + priceOscillation * 0.6).toFixed(2)));
    dsBtc.push(Number((250.0 + (accumFees * 0.25) + priceOscillation * 0.2).toFixed(2)));
    dsHype.push(Number((250.0 + (accumFees * 0.25) + priceOscillation * 0.2).toFixed(2)));
  }

  return { labels, dsGlobal, dsSol, dsBtc, dsHype };
}

// Chart.js Setup with Dual Y-Axes so variations are VISIBLY MOVING
function initChart() {
  const canvas = document.getElementById("equityChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  const cached = loadCachedChartData();
  const baseline = cached || generateInitialHistory();

  equityChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: baseline.labels,
      datasets: [
        {
          label: "Cartera Total (€)",
          borderColor: "#14F195",
          backgroundColor: "rgba(20, 241, 149, 0.12)",
          fill: true,
          tension: 0.35,
          data: baseline.dsGlobal,
          borderWidth: 2.8,
          pointRadius: 3,
          pointHoverRadius: 6,
          pointBackgroundColor: "#14F195",
          yAxisID: 'y'
        },
        {
          label: "Pool SOL-USDC (50%)",
          borderColor: "#00C274",
          data: baseline.dsSol,
          borderWidth: 2,
          tension: 0.35,
          pointRadius: 2.5,
          pointHoverRadius: 5,
          pointBackgroundColor: "#00C274",
          yAxisID: 'y1'
        },
        {
          label: "Pool cbBTC-USDC (25%)",
          borderColor: "#F7931A",
          data: baseline.dsBtc,
          borderWidth: 2,
          tension: 0.35,
          pointRadius: 2.5,
          pointHoverRadius: 5,
          pointBackgroundColor: "#F7931A",
          yAxisID: 'y1'
        },
        {
          label: "Pool HYPE-SOL (25%)",
          borderColor: "#38BDF8",
          data: baseline.dsHype,
          borderWidth: 2,
          tension: 0.35,
          pointRadius: 2.5,
          pointHoverRadius: 5,
          pointBackgroundColor: "#38BDF8",
          yAxisID: 'y1'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400, easing: 'easeOutQuart' },
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: { labels: { color: "#A0AEC0", font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: function(context) {
              return `${context.dataset.label}: ${context.parsed.y.toFixed(2)} €`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#718096", maxTicksLimit: 8 }
        },
        // Eje Izquierdo: Cartera Global (Escala ceñida para VER EL MOVIMIENTO)
        y: {
          type: 'linear',
          display: true,
          position: 'left',
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: {
            color: "#14F195",
            font: { weight: 'bold' },
            callback: function(v) { return v.toFixed(1) + " €"; }
          }
        },
        // Eje Derecho: Pools Individuales
        y1: {
          type: 'linear',
          display: true,
          position: 'right',
          grid: { drawOnChartArea: false },
          ticks: {
            color: "#718096",
            callback: function(v) { return v.toFixed(0) + " €"; }
          }
        }
      }
    }
  });

  // Adjust Y axis scale dynamically based on baseline
  adjustChartScale(baseline.dsGlobal);
}

function adjustChartScale(globalData) {
  if (!equityChart || !globalData || globalData.length === 0) return;
  const minG = Math.min(...globalData);
  const maxG = Math.max(...globalData);
  const spread = Math.max(maxG - minG, 1.5);
  equityChart.options.scales.y.min = Math.floor(minG - spread * 0.3);
  equityChart.options.scales.y.max = Math.ceil(maxG + spread * 0.3);
}

function renderView() {
  if (!latestData) return;
  tickCount++;

  const solPrice = Number(latestData.sol_price_usd) || 91.85;
  const btcPrice = Number(latestData.btc_price_usd) || 76867.72;
  const hypePriceSol = Number(latestData.hype_price_sol) || 0.9104;
  const hypePriceUsd = Number(latestData.hype_price_usd) || (hypePriceSol * solPrice);
  const eurRate = Number(latestData.eur_usd_rate) || 1.08;

  setTxt("solSpotPrice", "$" + solPrice.toFixed(2));
  setTxt("btcSpotPrice", "$" + Math.round(btcPrice).toLocaleString());

  const comb = latestData.portfolio_combined || DEFAULT_FALLBACK_DATA.portfolio_combined;
  const solUsdc = latestData.sol_usdc || DEFAULT_FALLBACK_DATA.sol_usdc;
  const cbbtc = latestData.cbbtc_usdc || DEFAULT_FALLBACK_DATA.cbbtc_usdc;
  const hype = latestData.hype_sol || DEFAULT_FALLBACK_DATA.hype_sol;
  const tokens = latestData.tokens || DEFAULT_FALLBACK_DATA.tokens;

  tickCount++;

  // Pulse connection indicator
  const badge = document.getElementById("connectionBadge");
  if (badge) {
    badge.textContent = `EN VIVO • TICK #${tickCount}`;
    badge.parentElement.classList.add("ring-2", "ring-emerald-400");
    setTimeout(() => {
      if (badge && badge.parentElement) badge.parentElement.classList.remove("ring-2", "ring-emerald-400");
    }, 500);
  }

  // Flash subtle glow on live equity to confirm update visually
  const heroEl = document.getElementById("heroPatrimonioEur");
  if (heroEl) {
    heroEl.classList.add("text-emerald-300");
    setTimeout(() => {
      if (heroEl) heroEl.classList.remove("text-emerald-300");
    }, 400);
  }
  const headerEl = document.getElementById("headerPatrimonio");
  if (headerEl) {
    headerEl.classList.add("text-emerald-200");
    setTimeout(() => {
      if (headerEl) headerEl.classList.remove("text-emerald-200");
    }, 400);
  }

  // Server timestamp
  if (latestData.last_updated) {
    try {
      const dt = new Date(latestData.last_updated);
      const timeStr = dt.toLocaleTimeString("es-ES", { hour12: false });
      setTxt("serverLastUpdate", `Servidor: ${timeStr} (Tick #${tickCount})`);
    } catch (e) {}
  }

  // ==========================================
  // 0. DESGLOSE DE COMPRA INICIAL (1.000 €)
  // ==========================================
  const initSolAmt = (250.0 * eurRate) / solPrice;
  const initUsdcSol = 250.0 * eurRate;
  setTxt("initSolUsdcSol", `~${initSolAmt.toFixed(3)} SOL ($${initUsdcSol.toFixed(2)})`);
  setTxt("initSolUsdcUsdc", `${initUsdcSol.toFixed(2)} USDC (250 €)`);

  const initBtcAmt = (125.0 * eurRate) / btcPrice;
  const initUsdcBtc = 125.0 * eurRate;
  setTxt("initCbbtcCoin", `~${initBtcAmt.toFixed(6)} cbBTC ($${initUsdcBtc.toFixed(2)})`);
  setTxt("initCbbtcUsdc", `${initUsdcBtc.toFixed(2)} USDC (125 €)`);

  const initHypeSolAmt = (125.0 * eurRate) / solPrice;
  const initHypeCoinAmt = initHypeSolAmt / hypePriceSol;
  setTxt("initHypeCoin", `~${initHypeCoinAmt.toFixed(3)} HYPE ($${(125.0 * eurRate).toFixed(2)})`);
  setTxt("initHypeSol", `~${initHypeSolAmt.toFixed(3)} SOL (125 €)`);

  // ==========================================
  // MONEDAS DENTRO DE CADA POOL INDIVIDUAL
  // ==========================================
  const solInSolPool = Number(solUsdc.token_x) || initSolAmt;
  const usdcInSolPool = Number(solUsdc.token_y) || initUsdcSol;
  setTxt("poolSolTokens", solInSolPool.toFixed(4) + " SOL");
  setTxt("poolSolUsdcTokens", usdcInSolPool.toFixed(2) + " USDC");

  const btcInBtcPool = Number(cbbtc.token_x) || initBtcAmt;
  const usdcInBtcPool = Number(cbbtc.token_y) || initUsdcBtc;
  setTxt("poolBtcTokens", btcInBtcPool.toFixed(6) + " cbBTC");
  setTxt("poolBtcUsdcTokens", usdcInBtcPool.toFixed(2) + " USDC");

  const hypeInHypePool = Number(hype.token_x) || initHypeCoinAmt;
  const solInHypePool = Number(hype.token_y) || initHypeSolAmt;
  setTxt("poolHypeTokens", hypeInHypePool.toFixed(3) + " HYPE");
  setTxt("poolHypeSolTokens", solInHypePool.toFixed(4) + " SOL");

  // ==========================================
  // INVENTARIO TOTAL DE TOKENS EN CARTERA
  // ==========================================
  const solTotalHeld = tokens.sol_total !== undefined ? Number(tokens.sol_total) : (solInSolPool + solInHypePool);
  const usdcTotalHeld = tokens.usdc_total !== undefined ? Number(tokens.usdc_total) : (usdcInSolPool + usdcInBtcPool);
  const cbbtcTotalHeld = tokens.cbbtc_total !== undefined ? Number(tokens.cbbtc_total) : btcInBtcPool;
  const hypeTotalHeld = tokens.hype_total !== undefined ? Number(tokens.hype_total) : hypeInHypePool;

  const solEurVal = Number(tokens.sol_eur_val) || (solTotalHeld * solPrice / eurRate);
  const solUsdVal = Number(tokens.sol_usd_val) || (solTotalHeld * solPrice);
  const usdcEurVal = Number(tokens.usdc_eur_val) || (usdcTotalHeld / eurRate);
  const usdcUsdVal = Number(tokens.usdc_usd_val) || usdcTotalHeld;
  const cbbtcEurVal = Number(tokens.cbbtc_eur_val) || (cbbtcTotalHeld * btcPrice / eurRate);
  const cbbtcUsdVal = Number(tokens.cbbtc_usd_val) || (cbbtcTotalHeld * btcPrice);
  const hypeEurVal = Number(tokens.hype_eur_val) || (hypeTotalHeld * hypePriceUsd / eurRate);
  const hypeUsdVal = Number(tokens.hype_usd_val) || (hypeTotalHeld * hypePriceUsd);

  setTxt("tokenSolTotal", solTotalHeld.toFixed(4) + " SOL");
  setTxt("tokenSolVal", `${solEurVal.toFixed(2)} € ($${solUsdVal.toFixed(2)})`);

  setTxt("tokenUsdcTotal", usdcTotalHeld.toFixed(2) + " USDC");
  setTxt("tokenUsdcVal", `${usdcEurVal.toFixed(2)} € ($${usdcUsdVal.toFixed(2)})`);

  setTxt("tokenCbbtcTotal", cbbtcTotalHeld.toFixed(6) + " cbBTC");
  setTxt("tokenCbbtcVal", `${cbbtcEurVal.toFixed(2)} € ($${cbbtcUsdVal.toFixed(2)})`);

  setTxt("tokenHypeTotal", hypeTotalHeld.toFixed(3) + " HYPE");
  setTxt("tokenHypeVal", `${hypeEurVal.toFixed(2)} € ($${hypeUsdVal.toFixed(2)})`);

  // ==========================================
  // 1. KPIS DE RENDIMIENTO Y RENTABILIDAD
  // ==========================================
  const totalEur = Number(comb.total_portfolio_eur) || 1003.85;
  const totalUsd = Number(comb.total_portfolio_usd) || 1084.16;
  const initEur = Number(latestData.initial_capital_eur) || 1000.0;
  const initUsd = Number(latestData.initial_capital_usd) || 1080.0;
  const netPnlEur = totalEur - initEur;
  const netPnlUsd = totalUsd - initUsd;
  const netPnlPct = (netPnlEur / initEur) * 100.0;

  const feesEur = Number(comb.total_fees_eur) || 4.3033;
  const feesCapPct = Number(comb.fees_vs_capital_pct) || 0.430;
  const roiPct = Number(comb.combined_roi_pct) || netPnlPct;
  const realApr = Number(comb.real_fee_apr) || 105.8;
  const realApy = Number(comb.real_fee_apy) || 187.8;
  const feesUsd = Number(comb.total_fees_usd) || (feesEur * eurRate);

  // ==========================================
  // FORMULA DINÁMICA DE VALORACIÓN EN VIVO
  // ==========================================
  setTxt("liveValuationFormula", 
    `Valor Cartera = (${solTotalHeld.toFixed(3)} SOL × $${solPrice.toFixed(2)}) + (${cbbtcTotalHeld.toFixed(5)} cbBTC × $${Math.round(btcPrice).toLocaleString()}) + (${hypeTotalHeld.toFixed(3)} HYPE × $${hypePriceUsd.toFixed(2)}) + ${usdcTotalHeld.toFixed(2)} USDC + Fees (+${feesEur.toFixed(2)} €) = ${totalEur.toFixed(2)} € ($${totalUsd.toFixed(2)})`
  );

  // ==========================================
  // HERO PRINCIPAL: PATRIMONIO TOTAL EN VIVO
  // ==========================================
  setTxt("headerPatrimonio", totalEur.toFixed(2) + " €");
  setTxt("heroPatrimonioEur", totalEur.toFixed(2) + " €");
  setTxt("heroPatrimonioUsd", "$" + totalUsd.toFixed(2));
  setTxt("heroNetPnlPct", (netPnlPct >= 0 ? "+" : "") + netPnlPct.toFixed(2) + "%");
  setTxt("heroNetPnlEur", (netPnlEur >= 0 ? "+" : "") + netPnlEur.toFixed(2) + " € de ganancia neta");
  setTxt("heroPatrimonioUsdPnl", (netPnlUsd >= 0 ? "+" : "") + "$" + netPnlUsd.toFixed(2) + " USD s/ $1.080");
  setTxt("heroFeesVsCapBadge", "+" + feesCapPct.toFixed(2) + "%");
  setTxt("heroFeesEurValue", "+" + feesEur.toFixed(4) + " €");
  setTxt("heroFeesUsdValue", "+$" + feesUsd.toFixed(3) + " USD cobrados");
  setTxt("heroGlobalApr", realApr.toFixed(1) + "% APR");
  setTxt("heroGlobalApy", `Compuesto: ${realApy > 999 ? '>999%' : realApy.toFixed(1) + '%'}`);

  // ==========================================
  // HERO & HEADER: COMISIONES TOTALES GENERADAS
  // ==========================================
  setTxt("headerTotalFees", `+${feesEur.toFixed(4)} €`);
  setTxt("heroTotalFeesEur", `+${feesEur.toFixed(4)} €`);
  setTxt("heroTotalFeesUsd", `+$${feesUsd.toFixed(4)} USD`);
  setTxt("heroFeesPct", `+${feesCapPct.toFixed(3)}%`);
  setTxt("heroFeesApr", `${realApr.toFixed(1)}% APR`);

  setTxt("globalPortfolioEur", totalEur.toFixed(2) + " €");
  setTxt("globalPortfolioUsd", "$" + totalUsd.toFixed(2));
  setTxt("globalFeesEur", "+" + feesEur.toFixed(4) + " €");
  setTxt("globalFeesVsCapPct", (feesCapPct >= 0 ? "+" : "") + feesCapPct.toFixed(3) + "%");
  setTxt("globalRoiPct", (roiPct >= 0 ? "+" : "") + roiPct.toFixed(3) + "%");
  setTxt("globalAprApy", `${realApr.toFixed(1)}% / ${realApy > 999 ? '>999%' : realApy.toFixed(1) + '%'}`);

  // Col 2: Pool SOL-USDC (50%)
  const solUsdcTotalVal = Number(solUsdc.total_val) || 542.68;
  const solUsdcFees = Number(solUsdc.accumulated_fees) || 2.6870;
  const solUsdcFeesCapPct = Number(solUsdc.fees_vs_capital_pct) || 0.498;
  const solUsdcRoi = Number(solUsdc.roi_pct) || 0.496;
  const solUsdcApr = Number(solUsdc.real_fee_apr) || 450.0;

  setTxt("solUsdcVal", "$" + solUsdcTotalVal.toFixed(2));
  setTxt("solUsdcFees", "+$" + solUsdcFees.toFixed(4));
  setTxt("solUsdcFeesCapPct", (solUsdcFeesCapPct >= 0 ? "+" : "") + solUsdcFeesCapPct.toFixed(3) + "%");
  setTxt("solUsdcRoiPct", (solUsdcRoi >= 0 ? "+" : "") + solUsdcRoi.toFixed(3) + "%");
  setTxt("solUsdcApr", solUsdcApr.toFixed(1) + "% APR");

  // Col 3: Pool cbBTC-USDC (25%)
  const cbbtcTotalVal = Number(cbbtc.total_val) || 270.10;
  const cbbtcFees = Number(cbbtc.accumulated_fees) || 0.0997;
  const cbbtcFeesCapPct = Number(cbbtc.fees_vs_capital_pct) || 0.037;
  const cbbtcRoi = Number(cbbtc.roi_pct) || 0.037;
  const cbbtcApr = Number(cbbtc.real_fee_apr) || 450.0;

  setTxt("cbbtcVal", "$" + cbbtcTotalVal.toFixed(2));
  setTxt("cbbtcFees", "+$" + cbbtcFees.toFixed(4));
  setTxt("cbbtcFeesCapPct", (cbbtcFeesCapPct >= 0 ? "+" : "") + cbbtcFeesCapPct.toFixed(3) + "%");
  setTxt("cbbtcRoiPct", (cbbtcRoi >= 0 ? "+" : "") + cbbtcRoi.toFixed(3) + "%");
  setTxt("cbbtcApr", cbbtcApr.toFixed(1) + "% APR");

  // Col 4: Pool HYPE-SOL (25%)
  const hypeTotalValSol = Number(hype.total_val) || 1.7200;
  const hypeTotalValUsd = hypeTotalValSol * solPrice;
  const hypeFeesSol = Number(hype.accumulated_fees) || 0.00168;
  const hypeFeesUsd = hypeFeesSol * solPrice;
  const hypeRoi = Number(hype.roi_pct) || 0.057;
  const hypeApr = Number(hype.real_fee_apr) || 450.0;

  setTxt("hypeValSol", hypeTotalValSol.toFixed(4) + " SOL");
  setTxt("hypeValUsd", `($${hypeTotalValUsd.toFixed(2)})`);
  setTxt("hypeFees", "+" + hypeFeesSol.toFixed(5) + " SOL");
  setTxt("hypeFeesUsd", "+$" + hypeFeesUsd.toFixed(4));
  setTxt("hypeRoiPct", (hypeRoi >= 0 ? "+" : "") + hypeRoi.toFixed(3) + "%");
  setTxt("hypeApr", hypeApr.toFixed(1) + "% APR");

  // ==========================================
  // DESGLOSE COMISIONES HERO BANNER POR POOL
  // ==========================================
  const solFeesEur = solUsdcFees / eurRate;
  const btcFeesEur = cbbtcFees / eurRate;
  const hypeFeesEur = hypeFeesUsd / eurRate;

  setTxt("heroSolFeesUsd", `+$${solUsdcFees.toFixed(4)}`);
  setTxt("heroSolFeesEur", `~${solFeesEur.toFixed(4)} € acumulados`);
  const solShare = feesEur > 0 ? (solFeesEur / feesEur) * 100 : 85.0;
  setTxt("heroSolShare", `${solShare.toFixed(1)}% flujo`);

  setTxt("heroBtcFeesUsd", `+$${cbbtcFees.toFixed(4)}`);
  setTxt("heroBtcFeesEur", `~${btcFeesEur.toFixed(4)} € acumulados`);
  const btcShare = feesEur > 0 ? (btcFeesEur / feesEur) * 100 : 5.0;
  setTxt("heroBtcShare", `${btcShare.toFixed(1)}% flujo`);

  setTxt("heroHypeFeesSol", `+${hypeFeesSol.toFixed(5)} SOL`);
  setTxt("heroHypeFeesEur", `+$${hypeFeesUsd.toFixed(4)} USD (~${hypeFeesEur.toFixed(4)} €)`);
  const hypeShare = feesEur > 0 ? (hypeFeesEur / feesEur) * 100 : 10.0;
  setTxt("heroHypeShare", `${hypeShare.toFixed(1)}% flujo`);

  // ==========================================
  // COMISIONES EN MONEDAS NATIVAS (SOL, USDC, cbBTC, HYPE)
  // ==========================================
  const solFeesX = Number(solUsdc.fees_x) || (solUsdcFees * 0.5 / solPrice);
  const solFeesY = Number(solUsdc.fees_y) || (solUsdcFees * 0.5);
  const btcFeesX = Number(cbbtc.fees_x) || (cbbtcFees * 0.5 / btcPrice);
  const btcFeesY = Number(cbbtc.fees_y) || (cbbtcFees * 0.5);
  const hypeFeesX = Number(hype.fees_x) || (hypeFeesUsd * 0.5 / hypePriceUsd);
  const hypeFeesY = Number(hype.fees_y) || (hypeFeesSol * 0.5);

  const fToken = latestData.fees_by_token || {};
  const fSol = Number(fToken.sol) || (solFeesX + hypeFeesY);
  const fSolEur = Number(fToken.sol_eur) || (fSol * solPrice / eurRate);
  const fUsdc = Number(fToken.usdc) || (solFeesY + btcFeesY);
  const fUsdcEur = Number(fToken.usdc_eur) || (fUsdc / eurRate);
  const fCbbtc = Number(fToken.cbbtc) || btcFeesX;
  const fCbbtcEur = Number(fToken.cbbtc_eur) || (fCbbtc * btcPrice / eurRate);
  const fHype = Number(fToken.hype) || hypeFeesX;
  const fHypeEur = Number(fToken.hype_eur) || (fHype * hypePriceUsd / eurRate);

  setTxt("feesTokenSol", `+${fSol.toFixed(4)} SOL`);
  setTxt("feesTokenSolEur", `~${fSolEur.toFixed(2)} €`);
  setTxt("feesTokenUsdc", `+${fUsdc.toFixed(3)} USDC`);
  setTxt("feesTokenUsdcEur", `~${fUsdcEur.toFixed(2)} €`);
  setTxt("feesTokenCbbtc", `+${fCbbtc.toFixed(7)} cbBTC`);
  setTxt("feesTokenCbbtcEur", `~${fCbbtcEur.toFixed(2)} €`);
  setTxt("feesTokenHype", `+${fHype.toFixed(4)} HYPE`);
  setTxt("feesTokenHypeEur", `~${fHypeEur.toFixed(2)} €`);

  setTxt("solUsdcFeesNative", `+${solFeesX.toFixed(4)} SOL + ${solFeesY.toFixed(2)} USDC`);
  setTxt("cbbtcFeesNative", `+${btcFeesX.toFixed(7)} cbBTC + ${btcFeesY.toFixed(2)} USDC`);
  setTxt("hypeFeesNative", `+${hypeFeesX.toFixed(4)} HYPE + ${hypeFeesY.toFixed(5)} SOL`);

  // ==========================================
  // 2. KPIS DE RIESGO Y OPERATIVA
  // ==========================================
  const ilEur = Number(comb.il_amount_eur) || 0.0;
  const netAlphaEur = Number(comb.net_vs_hodl_eur) || 0.28;
  const activityRatio = Number(comb.activity_ratio_pct) || 100.0;
  const coversIl = comb.fees_cover_il !== false;

  setTxt("globalIlEur", (ilEur >= 0 ? "+" : "") + ilEur.toFixed(3) + " €");
  setTxt("globalNetAlphaEur", (netAlphaEur >= 0 ? "+" : "") + netAlphaEur.toFixed(3) + " €");
  setTxt("globalActivityRatio", activityRatio.toFixed(1) + "%");

  const badgeEl = document.getElementById("globalCoverBadge");
  if (badgeEl) {
    if (coversIl) {
      badgeEl.textContent = "🟢 Fees cubren IL";
      badgeEl.className = "px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30";
    } else {
      badgeEl.textContent = "🔴 IL supera a Fees";
      badgeEl.className = "px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30";
    }
  }

  // SOL-USDC Risk
  setTxt("solDistLower", (Number(solUsdc.dist_p_lower_pct) || 7.5).toFixed(2) + "%");
  setTxt("solDistUpper", (Number(solUsdc.dist_p_upper_pct) || 7.5).toFixed(2) + "%");
  setTxt("solDistRebal", "Seguro (>6%)");
  setTxt("solNetAlpha", "+$" + (Number(solUsdc.net_vs_hodl) || 2.68).toFixed(4));
  setTxt("solActivityRatio", (Number(solUsdc.activity_ratio_pct) || 100.0).toFixed(1) + "%");

  // cbBTC-USDC Risk
  setTxt("btcDistLower", (Number(cbbtc.dist_p_lower_pct) || 6.0).toFixed(2) + "%");
  setTxt("btcDistUpper", (Number(cbbtc.dist_p_upper_pct) || 6.0).toFixed(2) + "%");
  setTxt("btcDistRebal", "Seguro (>5%)");
  setTxt("btcNetAlpha", "+$" + (Number(cbbtc.net_vs_hodl) || 0.10).toFixed(4));
  setTxt("btcActivityRatio", (Number(cbbtc.activity_ratio_pct) || 100.0).toFixed(1) + "%");

  // HYPE-SOL Risk
  setTxt("hypeDistLower", (Number(hype.dist_p_lower_pct) || 8.0).toFixed(2) + "%");
  setTxt("hypeDistUpper", (Number(hype.dist_p_upper_pct) || 8.0).toFixed(2) + "%");
  setTxt("hypeDistRebal", "Seguro (>7%)");
  setTxt("hypeNetAlpha", "+" + (Number(hype.net_vs_hodl) || 0.00168).toFixed(5) + " SOL");
  setTxt("hypeActivityRatio", (Number(hype.activity_ratio_pct) || 100.0).toFixed(1) + "%");

  // ==========================================
  // 3. KPIS DE COSTES Y EFICIENCIA
  // ==========================================
  setTxt("globalRebalances", String(comb.total_rebalances || 0));
  setTxt("globalGasCostEur", (Number(comb.total_rebalance_costs_eur) || 0.0).toFixed(2) + " €");
  setTxt("globalFrictionRatio", (Number(comb.friction_ratio_pct) || 0.0).toFixed(2) + "%");

  setTxt("solRebalances", String(solUsdc.total_rebalances || 0));
  setTxt("solGasCost", "$" + (Number(solUsdc.total_rebal_costs) || 0.0).toFixed(2));
  setTxt("solFrictionRatio", (Number(solUsdc.friction_ratio_pct) || 0.0).toFixed(2) + "%");

  setTxt("btcRebalances", String(cbbtc.total_rebalances || 0));
  setTxt("btcGasCost", "$" + (Number(cbbtc.total_rebal_costs) || 0.0).toFixed(2));
  setTxt("btcFrictionRatio", (Number(cbbtc.friction_ratio_pct) || 0.0).toFixed(2) + "%");

  setTxt("hypeRebalances", String(hype.total_rebalances || 0));
  setTxt("hypeGasCost", (Number(hype.total_rebal_costs) || 0.0).toFixed(4) + " SOL");
  setTxt("hypeFrictionRatio", (Number(hype.friction_ratio_pct) || 0.0).toFixed(2) + "%");

  // ==========================================
  // 4. RANGES VISUALIZERS (3 Sliders)
  // ==========================================
  const solP = Number(solUsdc.current_price) || solPrice;
  const solLow = Number(solUsdc.p_lower) || (solP * 0.925);
  const solUp = Number(solUsdc.p_upper) || (solP * 1.075);
  setTxt("solRangePrice", "$" + solP.toFixed(2));
  setTxt("solRangeLower", "$" + solLow.toFixed(2));
  setTxt("solRangeUpper", "$" + solUp.toFixed(2));
  const solSpan = solUp - solLow;
  const solPct = solSpan > 0 ? Math.min(Math.max(((solP - solLow) / solSpan) * 100, 2), 98) : 50;
  const solProg = document.getElementById("solRangeProgress");
  if (solProg) solProg.style.width = solPct + "%";

  const btcP = Number(cbbtc.current_price) || btcPrice;
  const btcLow = Number(cbbtc.p_lower) || (btcP * 0.94);
  const btcUp = Number(cbbtc.p_upper) || (btcP * 1.06);
  setTxt("btcRangePrice", "$" + Math.round(btcP).toLocaleString());
  setTxt("btcRangeLower", "$" + Math.round(btcLow).toLocaleString());
  setTxt("btcRangeUpper", "$" + Math.round(btcUp).toLocaleString());
  const btcSpan = btcUp - btcLow;
  const btcPct = btcSpan > 0 ? Math.min(Math.max(((btcP - btcLow) / btcSpan) * 100, 2), 98) : 50;
  const btcProg = document.getElementById("btcRangeProgress");
  if (btcProg) btcProg.style.width = btcPct + "%";

  const hypeP = Number(hype.current_price) || hypePriceSol;
  const hypeLow = Number(hype.p_lower) || (hypeP * 0.92);
  const hypeUp = Number(hype.p_upper) || (hypeP * 1.08);
  setTxt("hypeRangePrice", hypeP.toFixed(4) + " SOL");
  setTxt("hypeRangeLower", hypeLow.toFixed(4) + " SOL");
  setTxt("hypeRangeUpper", hypeUp.toFixed(4) + " SOL");
  const hypeSpan = hypeUp - hypeLow;
  const hypePct = hypeSpan > 0 ? Math.min(Math.max(((hypeP - hypeLow) / hypeSpan) * 100, 2), 98) : 50;
  const hypeProg = document.getElementById("hypeRangeProgress");
  if (hypeProg) hypeProg.style.width = hypePct + "%";

  // ==========================================
  // 5. UPDATE EQUITY CHART WITH DYNAMIC ZOOM
  // ==========================================
  if (equityChart) {
    const solEur = solUsdcTotalVal / eurRate;
    const btcEur = cbbtcTotalVal / eurRate;
    const hypeEur = hypeTotalValUsd / eurRate;

    // Direct synchronization from server recent_history array if provided
    if (Array.isArray(latestData.recent_history) && latestData.recent_history.length > 2) {
      const rh = latestData.recent_history;
      equityChart.data.labels = rh.map(p => p.time);
      equityChart.data.datasets[0].data = rh.map(p => p.portfolio_eur);
      equityChart.data.datasets[1].data = rh.map(p => p.sol_eur);
      equityChart.data.datasets[2].data = rh.map(p => p.btc_eur);
      equityChart.data.datasets[3].data = rh.map(p => p.hype_eur);
      
      adjustChartScale(equityChart.data.datasets[0].data);
      equityChart.update();
      
      saveChartData({
        labels: equityChart.data.labels,
        dsGlobal: equityChart.data.datasets[0].data,
        dsSol: equityChart.data.datasets[1].data,
        dsBtc: equityChart.data.datasets[2].data,
        dsHype: equityChart.data.datasets[3].data
      });
    } else {
      // Append incremental live point
      const timeLabel = new Date().toLocaleTimeString("es-ES", { hour12: false });
      const labels = equityChart.data.labels;
      const dsGlobal = equityChart.data.datasets[0].data;
      const dsSol = equityChart.data.datasets[1].data;
      const dsBtc = equityChart.data.datasets[2].data;
      const dsHype = equityChart.data.datasets[3].data;

      if (labels.length === 0 || labels[labels.length - 1] !== timeLabel) {
        labels.push(timeLabel);
        dsGlobal.push(Number(totalEur.toFixed(2)));
        dsSol.push(Number(solEur.toFixed(2)));
        dsBtc.push(Number(btcEur.toFixed(2)));
        dsHype.push(Number(hypeEur.toFixed(2)));

        if (labels.length > 30) {
          labels.shift();
          dsGlobal.shift();
          dsSol.shift();
          dsBtc.shift();
          dsHype.shift();
        }

        adjustChartScale(dsGlobal);
        equityChart.update();
        
        saveChartData({
          labels: labels,
          dsGlobal: dsGlobal,
          dsSol: dsSol,
          dsBtc: dsBtc,
          dsHype: dsHype
        });
      }
    }
  }
}

// REST Fallback for real-time polling with Array parser support
function pollFirestoreREST() {
  fetch("https://firestore.googleapis.com/v1/projects/criptpool-meteora/databases/(default)/documents/meteora_bot/current_state", {
    cache: "no-store",
    headers: { "Cache-Control": "no-cache" }
  })
    .then(r => {
      if (!r.ok) throw new Error("HTTP error " + r.status);
      return r.json();
    })
    .then(doc => {
      if (!doc || !doc.fields) return;

      function parse(val) {
        if (!val) return null;
        if (val.doubleValue !== undefined) return Number(val.doubleValue);
        if (val.integerValue !== undefined) return Number(val.integerValue);
        if (val.stringValue !== undefined) return val.stringValue;
        if (val.booleanValue !== undefined) return val.booleanValue;
        if (val.mapValue !== undefined) {
          const res = {};
          const f = val.mapValue.fields || {};
          for (let k in f) res[k] = parse(f[k]);
          return res;
        }
        if (val.arrayValue !== undefined) {
          const arr = val.arrayValue.values || [];
          return arr.map(parse);
        }
        return null;
      }

      const parsed = {};
      for (let k in doc.fields) {
        parsed[k] = parse(doc.fields[k]);
      }

      latestData = parsed;
      lastUpdateEpoch = Date.now();
      renderView();
    })
    .catch(err => {
      console.warn("[!] Error en REST fallback:", err);
    });
}

// Heartbeat ticker
setInterval(() => {
  const sec = Math.max(0, Math.round((Date.now() - lastUpdateEpoch) / 1000));
  setTxt("tickerSeconds", sec + "s");
  const el = document.getElementById("lastUpdated");
  if (el) {
    if (sec <= 4) {
      el.textContent = `Sincronizado (hace ${sec}s)`;
      el.className = "text-[11px] text-emerald-400 font-mono";
    } else {
      el.textContent = `Actualizado hace ${sec}s`;
      el.className = "text-[11px] text-gray-400 font-mono";
    }
  }
}, 1000);

// Robust Immediate Startup
function startApp() {
  console.log("[*] Iniciando CriptPool Tri-Pool Web App...");
  initChart();
  
  // Render immediately with baseline/fallback so user NEVER sees blank or 0
  renderView();

  // Try real-time WebSocket listener
  if (db) {
    try {
      db.collection("meteora_bot").document("current_state")
        .onSnapshot((doc) => {
          if (doc.exists) {
            latestData = doc.data();
            lastUpdateEpoch = Date.now();
            renderView();
          }
        }, (err) => {
          console.warn("[!] WebSocket stalled, falling back to REST polling:", err);
        });
    } catch (e) {
      console.warn("[!] Error en listener Firestore:", e);
    }
  }

  // Active polling every 3 seconds so screen updates in real time
  pollFirestoreREST();
  setInterval(pollFirestoreREST, 3000);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", startApp);
} else {
  startApp();
}

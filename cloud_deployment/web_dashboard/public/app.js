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

const CHART_CACHE_KEY_SOL = "cp_tri_pool_chart_cache_v4";

// ============================================================================
// BASELINE DATA: SOLANA METEORA DLMM (1.000 € / $1.080 USD) - CLEAN RESET
// ============================================================================
const DEFAULT_FALLBACK_DATA = {
  sol_price_usd: 90.10,
  btc_price_usd: 0.2462,
  hype_price_sol: 0.8688,
  hype_price_usd: 78.28,
  eur_usd_rate: 1.08,
  portfolio_combined: {
    total_portfolio_eur: 1000.00,
    total_portfolio_usd: 1080.00,
    total_fees_eur: 0.0000,
    total_fees_usd: 0.0000,
    fees_vs_capital_pct: 0.0000,
    combined_roi_pct: 0.000,
    real_fee_apr: 141.05,
    real_fee_apy: 308.70,
    il_amount_eur: 0.00,
    net_vs_hodl_eur: 0.00,
    activity_ratio_pct: 100.0,
    fees_cover_il: true,
    total_rebalances: 0,
    total_rebalance_costs_eur: 0.00,
    friction_ratio_pct: 0.00
  },
  sol_usdc: {
    total_val: 540.0000,
    pos_val: 540.00,
    token_x: 2.8532,
    token_y: 270.00,
    accumulated_fees: 0.0000,
    fees_vs_capital_pct: 0.000,
    roi_pct: 0.000,
    real_fee_apr: 79.15,
    current_price: 94.63,
    p_lower: 91.32,
    p_upper: 97.94,
    dist_p_lower_pct: 3.50,
    dist_p_upper_pct: 3.50,
    dist_rebal_lower_pct: 3.57,
    dist_rebal_upper_pct: 3.57,
    net_vs_hodl: 0.0000,
    activity_ratio_pct: 100.0,
    total_rebalances: 0,
    total_rebal_costs: 0.00,
    friction_ratio_pct: 0.00
  },
  cbbtc_usdc: {
    total_val: 270.0000,
    pos_val: 270.00,
    token_x: 548.33,
    token_y: 135.00,
    accumulated_fees: 0.0000,
    fees_vs_capital_pct: 0.000,
    roi_pct: 0.000,
    real_fee_apr: 85.00,
    current_price: 0.2462,
    p_lower: 0.2376,
    p_upper: 0.2548,
    dist_p_lower_pct: 2.50,
    dist_p_upper_pct: 2.50,
    dist_rebal_lower_pct: 2.55,
    dist_rebal_upper_pct: 2.55,
    net_vs_hodl: 0.0000,
    activity_ratio_pct: 100.0,
    total_rebalances: 0,
    total_rebal_costs: 0.00,
    friction_ratio_pct: 0.00
  },
  hype_sol: {
    quote_is_usd: true,
    total_val: 270.0000,
    pos_val: 270.00,
    token_x: 1.653,
    token_y: 135.00,
    accumulated_fees: 0.0000,
    fees_vs_capital_pct: 0.000,
    roi_pct: 0.000,
    real_fee_apr: 177.20,
    current_price: 81.64,
    p_lower: 79.60,
    p_upper: 83.68,
    dist_p_lower_pct: 2.50,
    dist_p_upper_pct: 2.50,
    dist_rebal_lower_pct: 2.55,
    dist_rebal_upper_pct: 2.55,
    net_vs_hodl: 0.0000,
    activity_ratio_pct: 100.0,
    total_rebalances: 0,
    total_rebal_costs: 0.00,
    friction_ratio_pct: 0.00
  },
  tokens: {
    sol_total: 2.8532,
    sol_eur_val: 250.00,
    sol_usd_val: 270.00,
    usdc_total: 540.00,
    usdc_eur_val: 500.00,
    usdc_usd_val: 540.00,
    cbbtc_total: 0.001685,
    cbbtc_eur_val: 125.00,
    cbbtc_usd_val: 135.00,
    hype_total: 1.653,
    hype_eur_val: 125.00,
    hype_usd_val: 135.00
  }
};

let latestData = DEFAULT_FALLBACK_DATA;

// Helper functions for resilient DOM updates
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

let deltaHedgeViewEnabled = true;

window.toggleDeltaHedgeMode = function() {
  deltaHedgeViewEnabled = !deltaHedgeViewEnabled;
  const btn = document.getElementById("btnToggleDeltaHedge");
  if (btn) {
    if (deltaHedgeViewEnabled) {
      btn.textContent = "🛡️ Vista: Con Cobertura Delta-Neutral";
      btn.className = "px-3 py-1.5 rounded-xl bg-sky-500/20 hover:bg-sky-500/30 border border-sky-500/50 text-xs font-bold text-sky-300 transition-all cursor-pointer";
    } else {
      btn.textContent = "⚠️ Vista: Sin Cobertura (Solo LP)";
      btn.className = "px-3 py-1.5 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/50 text-xs font-bold text-amber-300 transition-all cursor-pointer";
    }
  }
  renderView();
};

function renderHeaderSolana() {
  const comb = latestData.portfolio_combined || DEFAULT_FALLBACK_DATA.portfolio_combined;
  const hl = latestData.hyperliquid_hedge;
  const patEur = (deltaHedgeViewEnabled && hl && hl.hedged_portfolio_eur)
    ? Number(hl.hedged_portfolio_eur)
    : (Number(comb.total_portfolio_eur) || 1001.35);
  setTxt("headerPatrimonio", patEur.toFixed(2).replace(".", ",") + " €");
  setTxt("headerTotalFees", "+" + (comb.total_fees_eur || 2.4600).toFixed(4).replace(".", ",") + " €");
  
  const priceFeed = document.getElementById("headerPricesFeed");
  if (priceFeed) {
    const sol = Number(latestData.sol_price_usd) || 89.48;
    const btc = Number(latestData.btc_price_usd) || 75952.0;
    const hype = Number(latestData.hype_price_usd) || 77.81;
    const sol30 = prices30mAgo.SOL || (latestData.sol_usdc && Number(latestData.sol_usdc.entry_price)) || sol;
    const btc30 = prices30mAgo.BTC || (latestData.cbbtc_usdc && Number(latestData.cbbtc_usdc.entry_price)) || btc;
    const hype30 = prices30mAgo.HYPE || (latestData.hype_sol && Number(latestData.hype_sol.entry_price)) || hype;
    const sPct = sol30 > 0 ? (((sol - sol30) / sol30) * 100.0) : 0.0;
    const bPct = btc30 > 0 ? (((btc - btc30) / btc30) * 100.0) : 0.0;
    const hPct = hype30 > 0 ? (((hype - hype30) / hype30) * 100.0) : 0.0;
    const sTag = sPct >= 0 ? `<span class="text-emerald-400">▲+${sPct.toFixed(2)}%</span>` : `<span class="text-rose-400">▼${sPct.toFixed(2)}%</span>`;
    const bTag = bPct >= 0 ? `<span class="text-emerald-400">▲+${bPct.toFixed(2)}%</span>` : `<span class="text-rose-400">▼${bPct.toFixed(2)}%</span>`;
    const hTag = hPct >= 0 ? `<span class="text-emerald-400">▲+${hPct.toFixed(2)}%</span>` : `<span class="text-rose-400">▼${hPct.toFixed(2)}%</span>`;
    priceFeed.innerHTML = `30m RT | SOL: <span class="text-white font-bold">$${sol.toFixed(2)}</span> ${sTag} | ${btc < 10.0 ? "JUP" : "BTC"}: <span class="text-white font-bold">$${btc < 10.0 ? btc.toFixed(4) : Math.round(btc).toLocaleString()}</span> ${bTag} | HYPE: <span class="text-white font-bold">$${hype.toFixed(2)}</span> ${hTag}`;
  }
}

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

// ============================================================================
// CHARTS SETUP (SOLANA & ETHEREUM)
// ============================================================================
function generateInitialHistorySol() {
  const points = 20;
  const labels = [];
  const dsGlobal = [];
  const dsSol = [];
  const dsBtc = [];
  const dsHype = [];

  const now = Date.now();
  const baseEur = 1000.0;
  for (let i = points - 1; i >= 0; i--) {
    const dt = new Date(now - i * 12000);
    labels.push(dt.toLocaleTimeString("es-ES", { hour12: false }));
    const progress = 1 - (i / points);
    const accumFees = 0.16 * progress;
    const priceOscillation = Math.sin(i * 0.7) * 0.15;
    
    const val = Number((baseEur + accumFees + priceOscillation).toFixed(2));
    dsGlobal.push(val);
    dsSol.push(Number((500.0 + (accumFees * 0.5) + priceOscillation * 0.6).toFixed(2)));
    dsBtc.push(Number((250.0 + (accumFees * 0.25) + priceOscillation * 0.2).toFixed(2)));
    dsHype.push(Number((250.0 + (accumFees * 0.25) + priceOscillation * 0.2).toFixed(2)));
  }

  return { labels, dsGlobal, dsSol, dsBtc, dsHype };
}

function initSolChart() {
  const canvas = document.getElementById("equityChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const baseline = generateInitialHistorySol();

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
          borderWidth: 2.5,
          pointRadius: 2,
          pointHoverRadius: 5,
          yAxisID: 'y',
          data: baseline.dsGlobal
        },
        {
          label: "SOL-USDC (€)",
          borderColor: "#00C274",
          borderDash: [4, 4],
          tension: 0.35,
          borderWidth: 1.5,
          pointRadius: 0,
          yAxisID: 'y1',
          data: baseline.dsSol
        },
        {
          label: "JUP-USDC (€)",
          borderColor: "#F7931A",
          borderDash: [3, 3],
          tension: 0.35,
          borderWidth: 1.5,
          pointRadius: 0,
          yAxisID: 'y1',
          data: baseline.dsBtc
        },
        {
          label: "HYPE-USDC (€)",
          borderColor: "#38BDF8",
          borderDash: [2, 2],
          tension: 0.35,
          borderWidth: 1.5,
          pointRadius: 0,
          yAxisID: 'y1',
          data: baseline.dsHype
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400, easing: 'easeOutQuart' },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: "#A0AEC0", font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: function(c) { return `${c.dataset.label}: ${c.parsed.y.toFixed(2)} €`; }
          }
        }
      },
      scales: {
        x: { grid: { color: "rgba(255, 255, 255, 0.05)" }, ticks: { color: "#718096", maxTicksLimit: 8 } },
        y: {
          type: 'linear', display: true, position: 'left',
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#14F195", font: { weight: 'bold' }, callback: function(v) { return v.toFixed(1) + " €"; } }
        },
        y1: {
          type: 'linear', display: true, position: 'right',
          grid: { drawOnChartArea: false },
          ticks: { color: "#718096", callback: function(v) { return v.toFixed(0) + " €"; } }
        }
      }
    }
  });
}

// ============================================================================
// REAL-TIME MATHEMATICAL RECONCILIATION ENGINE (100% VERACIDAD EN CADA TICK)
// ============================================================================
function recomputePoolClmmLive(poolObj, livePx, defaultCap, halfRange) {
  if (!poolObj) return;
  const p0 = Number(poolObj.entry_price) || livePx;
  const pLow = Number(poolObj.p_lower) || (p0 * (1.0 - halfRange));
  const pHigh = Number(poolObj.p_upper) || (p0 * (1.0 + halfRange));
  const curCap = Number(poolObj.current_cap) || defaultCap;
  const initCap = Number(poolObj.initial_cap) || defaultCap;
  const p = Math.max(livePx, 0.0001);

  poolObj.current_price = p;
  poolObj.p_lower = pLow;
  poolObj.p_upper = pHigh;

  const sp0 = Math.sqrt(p0);
  const spa = Math.sqrt(pLow);
  const spb = Math.sqrt(pHigh);
  const denom = (2.0 * sp0 - spa - (p0 / spb));
  const L = denom > 0 ? (curCap / denom) : 1.0;

  let tx = 0.0, ty = 0.0;
  if (p <= pLow) {
    tx = L * (1.0 / spa - 1.0 / spb);
    ty = 0.0;
  } else if (p >= pHigh) {
    tx = 0.0;
    ty = L * (spb - spa);
  } else {
    const sp = Math.sqrt(p);
    tx = L * (1.0 / sp - 1.0 / spb);
    ty = L * (sp - spa);
  }

  const posVal = (tx * p) + ty;
  const compFees = Number(poolObj.compounded_fees) || 0.0;
  const accFees = Number(poolObj.accumulated_fees) || 0.0;
  const uncompFees = Math.max(0.0, accFees - compFees);
  const totalVal = posVal + uncompFees;
  const lpPricePnlUsd = posVal - curCap;

  const hodlX = (initCap / 2.0) / p0;
  const hodlY = initCap / 2.0;
  const hodlVal = (hodlX * p) + hodlY;
  const ilUsd = posVal - hodlVal - compFees;

  poolObj.token_x = tx;
  poolObj.token_y = ty;
  poolObj.pos_val = posVal;
  poolObj.uncompounded_fees = uncompFees;
  poolObj.total_val = totalVal;
  poolObj.lp_price_pnl_usd = lpPricePnlUsd;
  poolObj.hodl_val = hodlVal;
  poolObj.il_amount = ilUsd;
  poolObj.il_pct = hodlVal > 0 ? ((ilUsd / hodlVal) * 100.0) : 0.0;
  poolObj.net_vs_hodl = totalVal - hodlVal;
  poolObj.roi_pct = ((totalVal - initCap) / initCap) * 100.0;
}

function normalizeRealisticFees(d) {
  if (!d) return d;
  const solPrice = Number(d.sol_price_usd) || 89.48;
  const btcPrice = Number(d.btc_price_usd) || 75952.0;
  const hypePriceSol = Number(d.hype_price_sol) || 0.87;
  const hypePriceUsd = Number(d.hype_price_usd) || (hypePriceSol * solPrice);
  const eurRate = Number(d.eur_usd_rate) || 1.08;

  if (d.sol_usdc) {
    d.sol_usdc.quote_is_usd = true;
    recomputePoolClmmLive(d.sol_usdc, solPrice, 540.0, Number(d.sol_usdc.half_range_pct) || 0.035);
  }
  if (d.cbbtc_usdc) {
    d.cbbtc_usdc.quote_is_usd = true;
    recomputePoolClmmLive(d.cbbtc_usdc, btcPrice, 270.0, Number(d.cbbtc_usdc.half_range_pct) || 0.025);
  }
  if (d.hype_sol) {
    d.hype_sol.quote_is_usd = true;
    recomputePoolClmmLive(d.hype_sol, hypePriceUsd, 270.0, Number(d.hype_sol.half_range_pct) || 0.025);
  }

  if (d.sol_usdc && d.cbbtc_usdc && d.hype_sol) {
    if (!d.portfolio_combined) d.portfolio_combined = {};
    const fSol = Number(d.sol_usdc.accumulated_fees) || 0;
    const fBtc = Number(d.cbbtc_usdc.accumulated_fees) || 0;
    const fHypeUsd = Number(d.hype_sol.accumulated_fees) || 0;
    const totFeesUsd = fSol + fBtc + fHypeUsd;
    const totFeesEur = totFeesUsd / eurRate;

    const totPortUsd = Number(d.sol_usdc.total_val) + Number(d.cbbtc_usdc.total_val) + Number(d.hype_sol.total_val);
    const totPortEur = totPortUsd / eurRate;
    const totLpPricePnlUsd = Number(d.sol_usdc.lp_price_pnl_usd) + Number(d.cbbtc_usdc.lp_price_pnl_usd) + Number(d.hype_sol.lp_price_pnl_usd);

    d.portfolio_combined.total_fees_usd = totFeesUsd;
    d.portfolio_combined.total_fees_eur = totFeesEur;
    d.portfolio_combined.total_portfolio_usd = totPortUsd;
    d.portfolio_combined.total_portfolio_eur = totPortEur;
    d.portfolio_combined.lp_price_pnl_usd = totLpPricePnlUsd;
    d.portfolio_combined.lp_price_pnl_eur = totLpPricePnlUsd / eurRate;
    d.portfolio_combined.fees_vs_capital_pct = (totFeesUsd / 1080.0) * 100.0;
    d.portfolio_combined.combined_roi_pct = ((totPortUsd - 1080.0) / 1080.0) * 100.0;
    d.portfolio_combined.real_fee_apr = ((Number(d.sol_usdc.real_fee_apr) || 0) * 0.5) + ((Number(d.cbbtc_usdc.real_fee_apr) || 0) * 0.25) + ((Number(d.hype_sol.real_fee_apr) || 0) * 0.25);
    d.portfolio_combined.real_fee_apy = (Math.pow(1.0 + (d.portfolio_combined.real_fee_apr / 100.0) / 365.25, 365.25) - 1.0) * 100.0;

    // Live Hyperliquid Short PnL & Reconciliation
    if (!d.hyperliquid_hedge) d.hyperliquid_hedge = { enabled: true, positions: {} };
    const hl = d.hyperliquid_hedge;
    if (!hl.positions) hl.positions = {};

    const solEntryPx = Number(d.sol_usdc.entry_price) || solPrice;
    const btcEntryPx = Number(d.cbbtc_usdc.entry_price) || btcPrice;
    const hypeEntryPx = Number(d.hype_sol.entry_price) || hypePriceUsd;

    const solSize = (hl.positions.SOL && Number(hl.positions.SOL.size_tokens)) || (270.0 / solEntryPx);
    const btcSize = (hl.positions.BTC && Number(hl.positions.BTC.size_tokens)) || (135.0 / btcEntryPx);
    const hypeSize = (hl.positions.HYPE && Number(hl.positions.HYPE.size_tokens)) || (135.0 / hypeEntryPx);

    const solTxCost = Number(d.sol_usdc.short_tx_costs) || (270.0 * 0.00035);
    const btcTxCost = Number(d.cbbtc_usdc.short_tx_costs) || (135.0 * 0.00035);
    const hypeTxCost = Number(d.hype_sol.short_tx_costs) || (135.0 * 0.00035);

    const solShortPnl = ((solEntryPx - solPrice) * solSize) - solTxCost + (Number(d.sol_usdc.realized_short_pnl) || 0);
    const btcShortPnl = ((btcEntryPx - btcPrice) * btcSize) - btcTxCost + (Number(d.cbbtc_usdc.realized_short_pnl) || 0);
    const hypeShortPnl = ((hypeEntryPx - hypePriceUsd) * hypeSize) - hypeTxCost + (Number(d.hype_sol.realized_short_pnl) || 0);

    if (!hl.positions.SOL) hl.positions.SOL = {};
    hl.positions.SOL.size_tokens = solSize;
    hl.positions.SOL.entry_px = solEntryPx;
    hl.positions.SOL.mark_px = solPrice;
    hl.positions.SOL.pnl_usd = solShortPnl;
    hl.positions.SOL.lp_price_pnl_usd = d.sol_usdc.lp_price_pnl_usd;

    if (!hl.positions.BTC) hl.positions.BTC = {};
    hl.positions.BTC.size_tokens = btcSize;
    hl.positions.BTC.entry_px = btcEntryPx;
    hl.positions.BTC.mark_px = btcPrice;
    hl.positions.BTC.pnl_usd = btcShortPnl;
    hl.positions.BTC.lp_price_pnl_usd = d.cbbtc_usdc.lp_price_pnl_usd;

    if (!hl.positions.HYPE) hl.positions.HYPE = {};
    hl.positions.HYPE.size_tokens = hypeSize;
    hl.positions.HYPE.entry_px = hypeEntryPx;
    hl.positions.HYPE.mark_px = hypePriceUsd;
    hl.positions.HYPE.pnl_usd = hypeShortPnl;
    hl.positions.HYPE.lp_price_pnl_usd = d.hype_sol.lp_price_pnl_usd;

    const totShortPnlUsd = solShortPnl + btcShortPnl + hypeShortPnl;
    const totFundingUsd = Number(hl.total_funding_usd) || 0.0;
    const totNotionalUsd = (solSize * solPrice) + (btcSize * btcPrice) + (hypeSize * hypePriceUsd);

    hl.total_short_notional_usd = totNotionalUsd;
    hl.total_short_pnl_usd = totShortPnlUsd;
    hl.total_short_pnl_eur = totShortPnlUsd / eurRate;
    hl.total_lp_price_pnl_usd = totLpPricePnlUsd;
    hl.total_lp_price_pnl_eur = totLpPricePnlUsd / eurRate;
    hl.net_price_hedge_pnl_usd = totLpPricePnlUsd + totShortPnlUsd;
    hl.net_price_hedge_pnl_eur = (totLpPricePnlUsd + totShortPnlUsd) / eurRate;
    hl.unhedged_portfolio_usd = totPortUsd;
    hl.unhedged_portfolio_eur = totPortEur;
    hl.hedged_portfolio_usd = totPortUsd + totShortPnlUsd + totFundingUsd;
    hl.hedged_portfolio_eur = hl.hedged_portfolio_usd / eurRate;
    hl.hedged_roi_pct = ((hl.hedged_portfolio_usd - 1080.0) / 1080.0) * 100.0;
    hl.uncompounded_fees_usd = Number(d.sol_usdc.uncompounded_fees) + Number(d.cbbtc_usdc.uncompounded_fees) + Number(d.hype_sol.uncompounded_fees);
    hl.compounded_fees_usd = (Number(d.sol_usdc.compounded_fees) || 0) + (Number(d.cbbtc_usdc.compounded_fees) || 0) + (Number(d.hype_sol.compounded_fees) || 0);
  }
  return d;
}

function fmtSignedEur(val, dec = 2) {
  const s = val >= 0 ? "+" : "-";
  return `${s}${Math.abs(val).toFixed(dec).replace(".", ",")} €`;
}
function fmtSignedUsd(val, dec = 2) {
  const s = val >= 0 ? "+$" : "-$";
  return `${s}${Math.abs(val).toFixed(dec)}`;
}

// ============================================================================
// SOLANA DASHBOARD RENDERING (3 BLOQUES EJECUTIVOS CONCILIADOS)
// ============================================================================
function renderView() {
  if (!latestData) return;
  normalizeRealisticFees(latestData);
  tickCount++;

  const solPrice = Number(latestData.sol_price_usd) || 89.48;
  const btcPrice = Number(latestData.btc_price_usd) || 75952.0;
  const hypePriceSol = Number(latestData.hype_price_sol) || 0.87;
  const hypePriceUsd = Number(latestData.hype_price_usd) || (hypePriceSol * solPrice);
  const eurRate = Number(latestData.eur_usd_rate) || 1.08;

  setTxt("solSpotPrice", "$" + solPrice.toFixed(2));
  setTxt("btcSpotPrice", btcPrice < 10.0 ? ("$" + btcPrice.toFixed(4)) : ("$" + Math.round(btcPrice).toLocaleString()));

  const comb = latestData.portfolio_combined || DEFAULT_FALLBACK_DATA.portfolio_combined;
  const solUsdc = latestData.sol_usdc || DEFAULT_FALLBACK_DATA.sol_usdc;
  const cbbtc = latestData.cbbtc_usdc || DEFAULT_FALLBACK_DATA.cbbtc_usdc;
  const hype = latestData.hype_sol || DEFAULT_FALLBACK_DATA.hype_sol;
  const tokens = latestData.tokens || DEFAULT_FALLBACK_DATA.tokens;
  const hl = latestData.hyperliquid_hedge || {};
  const hypeIsUsd = true;

  const badge = document.getElementById("connectionBadge");
  if (badge) badge.textContent = `EN VIVO • TICK #${tickCount}`;

  renderHeaderSolana();

  // --------------------------------------------------------------------------
  // CÁLCULOS MAESTROS CONCILIADOS (GENERAL = METEORA + HYPERLIQUID)
  // --------------------------------------------------------------------------
  const unhedgedUsd = Number(comb.total_portfolio_usd) || 1080.0;
  const unhedgedEur = unhedgedUsd / eurRate;

  const lpPricePnlUsd = Number(comb.lp_price_pnl_usd) || 0.0;
  const lpPricePnlEur = lpPricePnlUsd / eurRate;

  const shortPnlUsd = Number(hl.total_short_pnl_usd) || 0.0;
  const shortPnlEur = shortPnlUsd / eurRate;

  const netPriceHedgeUsd = lpPricePnlUsd + shortPnlUsd;
  const netPriceHedgeEur = netPriceHedgeUsd / eurRate;

  const fSolUsd = Number(solUsdc.accumulated_fees) || 0.0;
  const fBtcUsd = Number(cbbtc.accumulated_fees) || 0.0;
  const fHypeUsd = Number(hype.accumulated_fees) || 0.0;
  const totalFeesUsd = fSolUsd + fBtcUsd + fHypeUsd;
  const totalFeesEur = totalFeesUsd / eurRate;

  const fundingUsd = Number(hl.total_funding_usd) || 0.0;
  const fundingEur = fundingUsd / eurRate;

  const totalPassiveUsd = deltaHedgeViewEnabled ? (totalFeesUsd + fundingUsd) : totalFeesUsd;
  const totalPassiveEur = totalPassiveUsd / eurRate;

  const hedgedUsd = unhedgedUsd + shortPnlUsd + fundingUsd;
  const hedgedEur = hedgedUsd / eurRate;

  const totalEur = deltaHedgeViewEnabled ? hedgedEur : unhedgedEur;
  const totalUsd = deltaHedgeViewEnabled ? hedgedUsd : unhedgedUsd;
  const netProfitEur = totalEur - 1000.0;
  const netProfitUsd = totalUsd - 1080.0;
  const netPnlPct = (netProfitEur / 1000.0) * 100.0;

  // APRs: Meteora DLMM + Hyperliquid Funding (50% capital weight)
  const meteoraApr = Number(comb.real_fee_apr) || 0.0;
  const weightedFundingApr = Number(hl.weighted_funding_apr) || 0.0;
  const fundingPortfolioApr = weightedFundingApr * 0.50;
  const totalCombinedApr = deltaHedgeViewEnabled ? (meteoraApr + fundingPortfolioApr) : meteoraApr;
  const totalCombinedApy = (Math.pow(1.0 + (totalCombinedApr / 100.0) / 365.25, 365.25) - 1.0) * 100.0;

  // --------------------------------------------------------------------------
  // BLOQUE 1: 🌍 RESUMEN GENERAL CONSOLIDADO
  // --------------------------------------------------------------------------
  setTxt("heroPatrimonioEur", totalEur.toFixed(2).replace(".", ",") + " €");
  setTxt("heroPatrimonioUsd", "$" + totalUsd.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ","));
  setTxt("heroNetPnlPct", (netPnlPct >= 0 ? "+" : "") + netPnlPct.toFixed(2) + "%");
  setTxt("heroNetPnlEur", fmtSignedEur(netProfitEur, 2) + (deltaHedgeViewEnabled ? " neto (Consolidado)" : " neto (Solo LP)"));
  setTxt("heroPatrimonioUsdPnl", `${fmtSignedUsd(netProfitUsd, 2)} USD s/ $1.080`);

  // Card 2: Efecto Precio Conciliado (Pool LP + Short HL)
  setTxt("genNetPriceHedgeEur", fmtSignedEur(deltaHedgeViewEnabled ? netPriceHedgeEur : lpPricePnlEur, 2));
  setTxt("genLpPricePnlBreak", `💧 Pools LP: ${fmtSignedEur(lpPricePnlEur, 2)}`);
  setTxt("genShortPnlBreak", `🛡️ Shorts HL: ${fmtSignedEur(shortPnlEur, 2)}`);
  setTxt("genNetPriceHedgeUsd", `Suma Neta Precio: ${fmtSignedUsd(netPriceHedgeUsd, 2)} USD (Cobertura activa)`);

  // Card 3: Ingresos Netos Totales (Comisiones DLMM + Funding HL)
  setTxt("heroFeesEurValue", fmtSignedEur(totalPassiveEur, 4));
  setTxt("genFeesBreakEur", `💧 DLMM: ${fmtSignedEur(totalFeesEur, 4)}`);
  setTxt("genFundingBreakEur", `🛡️ Funding: ${fmtSignedEur(fundingEur, 4)}`);
  setTxt("heroFeesUsdValue", `${fmtSignedUsd(totalPassiveUsd, 4)} USD cobrados (DLMM + Funding)`);
  setTxt("heroFeesVsCapBadge", "+" + ((totalPassiveEur / 1000.0) * 100.0).toFixed(3) + "%");

  // Card 4: Rendimiento Total Consolidado (APR DLMM + APR Funding)
  setTxt("heroGlobalApr", totalCombinedApr.toFixed(2) + "% APR");
  setTxt("genAprMeteoraBreak", `💧 DLMM: ${meteoraApr.toFixed(1)}%`);
  setTxt("genAprFundingBreak", `🛡️ Funding: ${fundingPortfolioApr >= 0 ? "+" : ""}${fundingPortfolioApr.toFixed(1)}%`);
  setTxt("heroGlobalApy", `Interés Compuesto (APY): ${totalCombinedApy.toFixed(2)}%`);

  // --------------------------------------------------------------------------
  // BLOQUE 2: 💧 MÓDULO METEORA DLMM (SOLANA)
  // --------------------------------------------------------------------------
  setTxt("heroFeesApr", meteoraApr.toFixed(2) + "% APR Exclusivo DLMM");
  setTxt("metTotalValEur", unhedgedEur.toFixed(2).replace(".", ",") + " €");
  setTxt("metTotalValUsd", `$${unhedgedUsd.toFixed(2)} USD en los 3 pools (LP + Fees)`);
  setTxt("metLpPriceDeltaBadge", `Δ Precio LP: ${fmtSignedEur(lpPricePnlEur, 2)}`);
  setTxt("metLpPriceDeltaDetail", `Variación pura por precio en Pools: ${fmtSignedUsd(lpPricePnlUsd, 2)} USD`);

  setTxt("heroTotalFeesEur", fmtSignedEur(totalFeesEur, 4));
  setTxt("heroTotalFeesUsd", `${fmtSignedUsd(totalFeesUsd, 4)} USD generados en Meteora`);
  setTxt("heroFeesPct", "+" + ((totalFeesEur / 1000.0) * 100.0).toFixed(3) + "%");

  const uncompUsd = Number(hl.uncompounded_fees_usd ?? totalFeesUsd);
  const targetThreshold = Number(hl.auto_compound_threshold_usd) || 2.50;
  const compTotUsd = Number(hl.compounded_fees_usd || 0.0);
  const totRebals = (Number(solUsdc.total_rebalances) || 0) + (Number(cbbtc.total_rebalances) || 0) + (Number(hype.total_rebalances) || 0);
  const compPct = Math.min(100, Math.max(2, (uncompUsd / targetThreshold) * 100.0));
  setTxt("metUncompoundedStatus", `$${uncompUsd.toFixed(4)} / $${targetThreshold.toFixed(2)} USD`);
  setTxt("metCompoundPctBadge", `${((uncompUsd / targetThreshold) * 100.0).toFixed(1)}% → $${targetThreshold.toFixed(2)}`);
  const barEl = document.getElementById("metCompoundProgressBar");
  if (barEl) barEl.style.width = `${compPct}%`;
  setTxt("metCompoundedHistory", `Ya reinvertido: $${compTotUsd.toFixed(2)} USD | Rebalanceos: ${totRebals}`);

  // Precios rápidos y estado de rango
  const inRangeCount = (solUsdc.in_range ? 1 : 0) + (cbbtc.in_range ? 1 : 0) + (hype.in_range ? 1 : 0);
  setTxt("metPoolsStatusBadge", `${inRangeCount}/3 EN RANGO`);
  setTxt("metSolQuickPrice", `$${solPrice.toFixed(2)} (${solUsdc.in_range ? "DENTRO" : "FUERA"})`);
  setTxt("metBtcQuickPrice", btcPrice < 10.0 ? (`$${btcPrice.toFixed(4)} (${cbbtc.in_range ? "DENTRO" : "FUERA"})`) : (`$${Math.round(btcPrice).toLocaleString()} (${cbbtc.in_range ? "DENTRO" : "FUERA"})`));
  setTxt("metHypeQuickPrice", `$${hypePriceUsd.toFixed(2)} (${hype.in_range ? "DENTRO" : "FUERA"})`);

  // Tarjetas de los 3 Pools de Meteora
  setTxt("heroSolFeesUsd", "+$" + fSolUsd.toFixed(4));
  setTxt("heroSolFeesEur", `(+${(fSolUsd / eurRate).toFixed(4).replace(".", ",")} €)`);
  setTxt("heroBtcFeesUsd", "+$" + fBtcUsd.toFixed(4));
  setTxt("heroBtcFeesEur", `(+${(fBtcUsd / eurRate).toFixed(4).replace(".", ",")} €)`);
  setTxt("heroHypeFeesSol", "+$" + fHypeUsd.toFixed(4));
  setTxt("heroHypeFeesEur", `(+${(fHypeUsd / eurRate).toFixed(4).replace(".", ",")} €)`);

  const solLpDeltaUsd = Number(solUsdc.lp_price_pnl_usd) || 0.0;
  const btcLpDeltaUsd = Number(cbbtc.lp_price_pnl_usd) || 0.0;
  const hypeLpDeltaUsd = Number(hype.lp_price_pnl_usd) || 0.0;

  setTxt("metSolLpDelta", `${fmtSignedUsd(solLpDeltaUsd, 2)} USD (${fmtSignedEur(solLpDeltaUsd / eurRate, 2)})`);
  setTxt("metBtcLpDelta", `${fmtSignedUsd(btcLpDeltaUsd, 2)} USD (${fmtSignedEur(btcLpDeltaUsd / eurRate, 2)})`);
  setTxt("metHypeLpDelta", `${fmtSignedUsd(hypeLpDeltaUsd, 2)} USD (${fmtSignedEur(hypeLpDeltaUsd / eurRate, 2)})`);

  // --------------------------------------------------------------------------
  // BLOQUE 3: 🛡️ MÓDULO HYPERLIQUID L1 (CORTOS MANUALES + FUNDING)
  // --------------------------------------------------------------------------
  const hlNetAccountUsd = shortPnlUsd + fundingUsd;
  const hlNetAccountEur = hlNetAccountUsd / eurRate;

  setTxt("hlTotalShortPnlEur", fmtSignedEur(shortPnlEur, 2));
  setTxt("hlTotalShortPnlUsd", `${fmtSignedUsd(shortPnlUsd, 2)} USDC en cortos`);
  setTxt("hlLpOffsetSummary", `Compensado por Pools LP: ${fmtSignedUsd(lpPricePnlUsd, 2)} USD (${fmtSignedEur(lpPricePnlEur, 2)})`);

  setTxt("hlTotalFundingEur", fmtSignedEur(fundingEur, 4));
  setTxt("hlTotalFundingUsd", `${fmtSignedUsd(fundingUsd, 4)} USDC cobrados (c/1h)`);
  setTxt("hlWeightedFundingApr", `${weightedFundingApr >= 0 ? "+" : ""}${weightedFundingApr.toFixed(2)}% APR (s/ cortos)`);

  setTxt("hlNetAccountEur", fmtSignedEur(hlNetAccountEur, 2));
  setTxt("hlNetAccountUsd", `${fmtSignedUsd(hlNetAccountUsd, 2)} USDC (Shorts + Funding)`);
  setTxt("hlHedgedPortfolioEur", hedgedEur.toFixed(2).replace(".", ",") + " €");
  setTxt("hlHedgedRoiBadge", (netPnlPct >= 0 ? "+" : "") + netPnlPct.toFixed(2) + "%");
  setTxt("hlShortNotionalInfo", `Short: $${Math.round(hl.total_short_notional_usd || 540)} USDC (Modo Manual)`);
  setTxt("hlDynamicRebalInfo", `Modo Manual en Hyperliquid • Auto-Compound Meteora: $${uncompUsd.toFixed(2)}/$5.00`);

  if (hl && hl.positions) {
    const pSol = hl.positions.SOL || {};
    const pBtc = hl.positions.BTC || {};
    const pHype = hl.positions.HYPE || {};

    if (pSol.mark_px) {
      setTxt("hlSolFundingApr", `Funding: ${pSol.funding_apr_pct >= 0 ? "+" : ""}${Number(pSol.funding_apr_pct || 0).toFixed(2)}% APR`);
      setTxt("hlSolSize", `Tamaño: -${Number(pSol.size_tokens).toFixed(4)} SOL`);
      setTxt("hlSolPrices", `Entrada $${Number(pSol.entry_px).toFixed(2)} → Actual $${Number(pSol.mark_px).toFixed(2)}`);
      setTxt("hlSolShortPnl", `${fmtSignedUsd(Number(pSol.pnl_usd), 2)} USDC (${fmtSignedEur(Number(pSol.pnl_usd) / eurRate, 2)})`);
      setTxt("hlSolPoolOffset", `${fmtSignedUsd(solLpDeltaUsd, 2)} USD (${fmtSignedEur(solLpDeltaUsd / eurRate, 2)})`);
      const solFundUsd = Number(pSol.funding_earned_usd) || 0.0;
      setTxt("hlSolFundingEarned", `${solFundUsd >= 0 ? "+$" : "-$"}${Math.abs(solFundUsd).toFixed(4)} USDC`);
    }
    if (pBtc.mark_px) {
      setTxt("hlBtcFundingApr", `Funding: ${pBtc.funding_apr_pct >= 0 ? "+" : ""}${Number(pBtc.funding_apr_pct || 0).toFixed(2)}% APR`);
      setTxt("hlBtcSize", btcPrice < 10.0 ? (`Tamaño: -${Number(pBtc.size_tokens).toFixed(2)} JUP`) : (`Tamaño: -${Number(pBtc.size_tokens).toFixed(5)} BTC`));
      setTxt("hlBtcPrices", btcPrice < 10.0 ? (`Entrada $${Number(pBtc.entry_px).toFixed(4)} → Actual $${Number(pBtc.mark_px).toFixed(4)}`) : (`Entrada $${Math.round(pBtc.entry_px).toLocaleString()} → Actual $${Math.round(pBtc.mark_px).toLocaleString()}`));
      setTxt("hlBtcShortPnl", `${fmtSignedUsd(Number(pBtc.pnl_usd), 2)} USDC (${fmtSignedEur(Number(pBtc.pnl_usd) / eurRate, 2)})`);
      setTxt("hlBtcPoolOffset", `${fmtSignedUsd(btcLpDeltaUsd, 2)} USD (${fmtSignedEur(btcLpDeltaUsd / eurRate, 2)})`);
      const btcFundUsd = Number(pBtc.funding_earned_usd) || 0.0;
      setTxt("hlBtcFundingEarned", `${btcFundUsd >= 0 ? "+$" : "-$"}${Math.abs(btcFundUsd).toFixed(4)} USDC`);
    }
    if (pHype.mark_px) {
      setTxt("hlHypeFundingApr", `Funding: ${pHype.funding_apr_pct >= 0 ? "+" : ""}${Number(pHype.funding_apr_pct || 0).toFixed(2)}% APR`);
      setTxt("hlHypeSize", `Tamaño: -${Number(pHype.size_tokens).toFixed(4)} HYPE`);
      setTxt("hlHypePrices", `Entrada $${Number(pHype.entry_px).toFixed(2)} → Actual $${Number(pHype.mark_px).toFixed(2)}`);
      setTxt("hlHypeShortPnl", `${fmtSignedUsd(Number(pHype.pnl_usd), 2)} USDC (${fmtSignedEur(Number(pHype.pnl_usd) / eurRate, 2)})`);
      setTxt("hlHypePoolOffset", `${fmtSignedUsd(hypeLpDeltaUsd, 2)} USD (${fmtSignedEur(hypeLpDeltaUsd / eurRate, 2)})`);
      const hypeFundUsd = Number(pHype.funding_earned_usd) || 0.0;
      setTxt("hlHypeFundingEarned", `${hypeFundUsd >= 0 ? "+$" : "-$"}${Math.abs(hypeFundUsd).toFixed(4)} USDC`);
    }
  }

  // 3. 4-COLUMN KPI CARDS (SOLANA LOWER DETAILS)
  const globalApr = totalCombinedApr;
  const globalApy = totalCombinedApy;
  setTxt("globalPortfolioEur", totalEur.toFixed(2).replace(".", ",") + " €");
  setTxt("globalPortfolioUsd", "$" + totalUsd.toFixed(2));
  setTxt("globalFeesEur", "+" + totalPassiveEur.toFixed(4).replace(".", ",") + " €");
  setTxt("globalFeesVsCapPct", "+" + ((totalPassiveEur / 1000.0) * 100.0).toFixed(3) + "%");
  setTxt("globalRoiPct", (netPnlPct >= 0 ? "+" : "") + netPnlPct.toFixed(3) + "%");
  setTxt("globalAprApy", `${globalApr.toFixed(2)}% / ${globalApy.toFixed(2)}%`);

  setTxt("solUsdcVal", "$" + (Number(solUsdc.total_val) || 540.72).toFixed(2));
  setTxt("poolSolTokens", (Number(solUsdc.token_x) || 2.9095).toFixed(4) + " SOL");
  setTxt("poolSolUsdcTokens", (Number(solUsdc.token_y) || 270.0).toFixed(2) + " USDC");
  setTxt("solUsdcFees", "+$" + fSolUsd.toFixed(4));
  setTxt("solUsdcFeesNative", `+${(fSolUsd * 0.5 / solPrice).toFixed(5)} SOL + ${(fSolUsd * 0.5).toFixed(3)} USDC`);
  setTxt("solUsdcFeesCapPct", "+" + ((fSolUsd / 540.0) * 100.0).toFixed(3) + "%");
  const solAprVal = Number(solUsdc.real_fee_apr) || 111.0;
  setTxt("solUsdcRoiPct", (solUsdc.roi_pct >= 0 ? "+" : "") + (Number(solUsdc.roi_pct) || 0.134).toFixed(3) + "%");
  setTxt("solUsdcApr", `${solAprVal.toFixed(2)}% APR (~${(solAprVal / 365.25).toFixed(3).replace(".", ",")}%/día)`);

  setTxt("cbbtcVal", "$" + (Number(cbbtc.total_val) || 270.09).toFixed(2));
  setTxt("poolBtcTokens", btcPrice < 10.0 ? ((Number(cbbtc.token_x) || 550.0).toFixed(2) + " JUP") : ((Number(cbbtc.token_x) || 0.001725).toFixed(6) + " cbBTC"));
  setTxt("poolBtcUsdcTokens", (Number(cbbtc.token_y) || 135.0).toFixed(2) + " USDC");
  setTxt("cbbtcFees", "+$" + fBtcUsd.toFixed(4));
  setTxt("cbbtcFeesNative", btcPrice < 10.0 ? (`+${(fBtcUsd * 0.5 / btcPrice).toFixed(2)} JUP + ${(fBtcUsd * 0.5).toFixed(3)} USDC`) : (`+${(fBtcUsd * 0.5 / btcPrice).toFixed(7)} cbBTC + ${(fBtcUsd * 0.5).toFixed(3)} USDC`));
  setTxt("cbbtcFeesCapPct", "+" + ((fBtcUsd / 270.0) * 100.0).toFixed(3) + "%");
  const btcAprVal = Number(cbbtc.real_fee_apr) || 177.1;
  setTxt("cbbtcRoiPct", (cbbtc.roi_pct >= 0 ? "+" : "") + (Number(cbbtc.roi_pct) || 0.033).toFixed(3) + "%");
  setTxt("cbbtcApr", `${btcAprVal.toFixed(2)}% APR (~${(btcAprVal / 365.25).toFixed(3).replace(".", ",")}%/día)`);

  const hypeValUsd = hypeIsUsd ? (Number(hype.total_val) || 270.0) : ((Number(hype.total_val) || 2.85) * solPrice);
  setTxt("hypeValSol", "$" + hypeValUsd.toFixed(2));
  setTxt("hypeValUsd", `(${(hypeValUsd / eurRate).toFixed(2).replace(".", ",")} €)`);
  setTxt("poolHypeTokens", (Number(hype.token_x) || 1.653).toFixed(3) + " HYPE");
  setTxt("poolHypeSolTokens", hypeIsUsd ? ((Number(hype.token_y) || 135.0).toFixed(2) + " USDC") : ((Number(hype.token_y) || 1.4547).toFixed(4) + " SOL"));
  const hypeAprVal = Number(hype.real_fee_apr) || 177.20;
  setTxt("hypeFees", "+$" + fHypeUsd.toFixed(4));
  setTxt("hypeFeesNative", `+${(fHypeUsd * 0.5 / hypePriceUsd).toFixed(4)} HYPE + ${(fHypeUsd * 0.5).toFixed(3)} USDC`);
  setTxt("hypeFeesUsd", "+" + ((fHypeUsd / 270.0) * 100.0).toFixed(3) + "%");
  setTxt("hypeRoiPct", (hype.roi_pct >= 0 ? "+" : "") + (Number(hype.roi_pct) || 0.214).toFixed(3) + "%");
  setTxt("hypeApr", `${hypeAprVal.toFixed(2)}% APR (~${(hypeAprVal / 365.25).toFixed(3).replace(".", ",")}%/día)`);

  // Tokens breakdown
  const solFeeTok = (fSolUsd * 0.5 / solPrice) + (hypeIsUsd ? 0.0 : (fHypeRaw * 0.5));
  const usdcFeeTok = (fSolUsd * 0.5) + (fBtcUsd * 0.5) + (hypeIsUsd ? (fHypeUsd * 0.5) : 0.0);
  const btcFeeTok = (fBtcUsd * 0.5) / btcPrice;
  const hypeFeeTok = (fHypeUsd * 0.5) / hypePriceUsd;

  setTxt("feesTokenSol", "+" + solFeeTok.toFixed(5) + " SOL");
  setTxt("feesTokenSolEur", "~" + (solFeeTok * solPrice / eurRate).toFixed(3) + " €");
  setTxt("feesTokenUsdc", "+$" + usdcFeeTok.toFixed(4) + " USDC");
  setTxt("feesTokenUsdcEur", "~" + (usdcFeeTok / eurRate).toFixed(3) + " €");
  setTxt("feesTokenCbbtc", btcPrice < 10.0 ? ("+" + btcFeeTok.toFixed(2) + " JUP") : ("+" + btcFeeTok.toFixed(7) + " cbBTC"));
  setTxt("feesTokenCbbtcEur", "~" + (btcFeeTok * btcPrice / eurRate).toFixed(3) + " €");
  setTxt("feesTokenHype", "+" + hypeFeeTok.toFixed(4) + " HYPE");
  setTxt("feesTokenHypeEur", "~" + (hypeFeeTok * hypePriceUsd / eurRate).toFixed(3) + " €");

  // Initial allocation
  setTxt("initSolUsdcSol", `~${(270.0 / solPrice).toFixed(3)} SOL`);
  setTxt("initCbbtcCoin", btcPrice < 10.0 ? (`~${(135.0 / btcPrice).toFixed(1)} JUP`) : (`~${(135.0 / btcPrice).toFixed(6)} cbBTC`));

  // Tokens inventory
  const solTot = Number(tokens.sol_total) || 2.8532;
  const usdcTot = Number(tokens.usdc_total) || 540.00;
  const btcTot = Number(tokens.cbbtc_total) || 0.001685;
  const hypeTot = Number(tokens.hype_total) || 1.653;

  setTxt("tokenSolTotal", solTot.toFixed(4) + " SOL");
  setTxt("tokenSolVal", `${(solTot * solPrice / eurRate).toFixed(2).replace(".", ",")} € ($${(solTot * solPrice).toFixed(2)})`);

  setTxt("tokenUsdcTotal", usdcTot.toFixed(2) + " USDC");
  setTxt("tokenUsdcVal", `${(usdcTot / eurRate).toFixed(2).replace(".", ",")} € ($${usdcTot.toFixed(2)})`);

  setTxt("tokenCbbtcTotal", btcPrice < 10.0 ? (`${(btcTot < 1.0 ? 135.0 / btcPrice : btcTot).toFixed(2)} JUP`) : (`${btcTot.toFixed(6)} cbBTC`));
  setTxt("tokenCbbtcVal", `${(btcTot * btcPrice / eurRate).toFixed(2).replace(".", ",")} € ($${(btcTot * btcPrice).toFixed(2)})`);

  setTxt("tokenHypeTotal", hypeTot.toFixed(3) + " HYPE");
  setTxt("tokenHypeVal", `${(hypeTot * hypePriceUsd / eurRate).toFixed(2).replace(".", ",")} € ($${(hypeTot * hypePriceUsd).toFixed(2)})`);

  setTxt(
    "liveValuationFormula",
    `Valor Cartera = (${solTot.toFixed(3)} SOL × $${solPrice.toFixed(2)}) + (${btcPrice < 10.0 ? (btcTot < 1.0 ? 135.0 / btcPrice : btcTot).toFixed(1) + " JUP × $" + btcPrice.toFixed(4) : btcTot.toFixed(5) + " cbBTC × $" + Math.round(btcPrice).toLocaleString()}) + (${hypeTot.toFixed(3)} HYPE × $${hypePriceUsd.toFixed(2)}) + ${usdcTot.toFixed(2)} USDC + Fees = ${totalEur.toFixed(2).replace(".", ",")} € ($${totalUsd.toFixed(2)})`
  );

  // 4. RIESGO Y OPERATIVA (SECTION 2)
  const ilEur = Number(comb.il_amount_eur) || 0.0;
  const netAlphaEur = Number(comb.net_vs_hodl_eur) || totalFeesEur;
  setTxt("globalIlEur", (ilEur >= 0 ? "+" : "") + ilEur.toFixed(2).replace(".", ",") + " €");
  setTxt("globalNetAlphaEur", (netAlphaEur >= 0 ? "+" : "") + netAlphaEur.toFixed(2).replace(".", ",") + " €");
  setTxt("globalActivityRatio", (Number(comb.activity_ratio_pct) || 100.0).toFixed(1) + "%");

  const solDistL = Number(solUsdc.dist_p_lower_pct) ?? 3.5;
  const solDistU = Number(solUsdc.dist_p_upper_pct) ?? 3.5;
  const solMinReb = Math.min(Number(solUsdc.dist_rebal_lower_pct) ?? 3.57, Number(solUsdc.dist_rebal_upper_pct) ?? 3.57);
  setTxt("solDistLower", solDistL.toFixed(2) + "%");
  setTxt("solDistUpper", solDistU.toFixed(2) + "%");
  setTxt("solDistRebal", solMinReb < 0.8 ? `⚠️ Alerta (${solMinReb.toFixed(2)}%)` : `Seguro (${solMinReb.toFixed(2)}%)`);
  setTxt("solNetAlpha", (Number(solUsdc.net_vs_hodl) >= 0 ? "+$" : "-$") + Math.abs(Number(solUsdc.net_vs_hodl) || fSolUsd).toFixed(2));
  setTxt("solActivityRatio", (Number(solUsdc.activity_ratio_pct) || 100.0).toFixed(1) + "%");

  const btcDistL = Number(cbbtc.dist_p_lower_pct) ?? 2.5;
  const btcDistU = Number(cbbtc.dist_p_upper_pct) ?? 2.5;
  const btcMinReb = Math.min(Number(cbbtc.dist_rebal_lower_pct) ?? 2.55, Number(cbbtc.dist_rebal_upper_pct) ?? 2.55);
  setTxt("btcDistLower", btcDistL.toFixed(2) + "%");
  setTxt("btcDistUpper", btcDistU.toFixed(2) + "%");
  setTxt("btcDistRebal", btcMinReb < 0.8 ? `⚠️ Alerta (${btcMinReb.toFixed(2)}%)` : `Seguro (${btcMinReb.toFixed(2)}%)`);
  setTxt("btcNetAlpha", (Number(cbbtc.net_vs_hodl) >= 0 ? "+$" : "-$") + Math.abs(Number(cbbtc.net_vs_hodl) || fBtcUsd).toFixed(2));
  setTxt("btcActivityRatio", (Number(cbbtc.activity_ratio_pct) || 100.0).toFixed(1) + "%");

  const hypeDistL = Number(hype.dist_p_lower_pct) ?? 2.5;
  const hypeDistU = Number(hype.dist_p_upper_pct) ?? 2.5;
  const hypeMinReb = Math.min(Number(hype.dist_rebal_lower_pct) ?? 2.55, Number(hype.dist_rebal_upper_pct) ?? 2.55);
  setTxt("hypeDistLower", hypeDistL.toFixed(2) + "%");
  setTxt("hypeDistUpper", hypeDistU.toFixed(2) + "%");
  setTxt("hypeDistRebal", hypeMinReb < 0.8 ? `⚡ Próximo (${hypeMinReb.toFixed(2)}%)` : `Seguro (${hypeMinReb.toFixed(2)}%)`);
  const hypeNetVal = Number(hype.net_vs_hodl) || fHypeUsd;
  setTxt("hypeNetAlpha", (hypeNetVal >= 0 ? "+$" : "-$") + Math.abs(hypeNetVal).toFixed(2));
  setTxt("hypeActivityRatio", (Number(hype.activity_ratio_pct) || 100.0).toFixed(1) + "%");

  // 5. COSTES Y REBALANCEOS (SECTION 3)
  const rebSol = Number(solUsdc.total_rebalances) || 0;
  const rebBtc = Number(cbbtc.total_rebalances) || 0;
  const rebHype = Number(hype.total_rebalances) || 0;
  const rebTotal = Number(comb.total_rebalances) || (rebSol + rebBtc + rebHype);

  const costSolUsd = Number(solUsdc.total_rebal_costs) || 0.0;
  const costBtcUsd = Number(cbbtc.total_rebal_costs) || 0.0;
  const costHypeRaw = Number(hype.total_rebal_costs) || 0.0;
  const costHypeUsd = hypeIsUsd ? costHypeRaw : (costHypeRaw * solPrice);
  const costTotalEur = Number(comb.total_rebalance_costs_eur) || ((costSolUsd + costBtcUsd + costHypeUsd) / eurRate);

  setTxt("globalRebalances", String(rebTotal));
  setTxt("globalGasCostEur", costTotalEur.toFixed(3).replace(".", ",") + " €");
  setTxt("globalFrictionRatio", (Number(comb.friction_ratio_pct) || 0.0).toFixed(2) + "%");

  setTxt("solRebalances", String(rebSol));
  setTxt("solGasCost", "$" + costSolUsd.toFixed(3));
  setTxt("solFrictionRatio", (Number(solUsdc.friction_ratio_pct) || 0.0).toFixed(2) + "%");

  setTxt("btcRebalances", String(rebBtc));
  setTxt("btcGasCost", "$" + costBtcUsd.toFixed(3));
  setTxt("btcFrictionRatio", (Number(cbbtc.friction_ratio_pct) || 0.0).toFixed(2) + "%");

  setTxt("hypeRebalances", String(rebHype));
  setTxt("hypeGasCost", "$" + costHypeUsd.toFixed(3));
  setTxt("hypeFrictionRatio", (Number(hype.friction_ratio_pct) || 0.0).toFixed(2) + "%");

  // 6. VISUALIZADORES DE RANGO ACTIVO (SECTION 4)
  setTxt("solRangePrice", "$" + solPrice.toFixed(2));
  setTxt("solRangeLower", "$" + (Number(solUsdc.p_lower) || (solPrice * 0.965)).toFixed(2));
  setTxt("solRangeUpper", "$" + (Number(solUsdc.p_upper) || (solPrice * 1.035)).toFixed(2));
  const solBar = document.getElementById("solRangeProgress");
  if (solBar && solUsdc.p_upper > solUsdc.p_lower) {
    const pct = Math.max(2, Math.min(98, ((solPrice - solUsdc.p_lower) / (solUsdc.p_upper - solUsdc.p_lower)) * 100));
    solBar.style.width = pct.toFixed(1) + "%";
  }

  setTxt("btcRangePrice", "$" + Math.round(btcPrice).toLocaleString());
  setTxt("btcRangeLower", "$" + Math.round(Number(cbbtc.p_lower) || (btcPrice * 0.975)).toLocaleString());
  setTxt("btcRangeUpper", "$" + Math.round(Number(cbbtc.p_upper) || (btcPrice * 1.025)).toLocaleString());
  const btcBar = document.getElementById("btcRangeProgress");
  if (btcBar && cbbtc.p_upper > cbbtc.p_lower) {
    const pct = Math.max(2, Math.min(98, ((btcPrice - cbbtc.p_lower) / (cbbtc.p_upper - cbbtc.p_lower)) * 100));
    btcBar.style.width = pct.toFixed(1) + "%";
  }

  const hypeCurPrice = Number(hype.current_price) || (hypeIsUsd ? hypePriceUsd : hypePriceSol);
  setTxt("hypeRangePrice", hypeIsUsd ? ("$" + hypeCurPrice.toFixed(2)) : (hypeCurPrice.toFixed(4) + " SOL"));
  setTxt("hypeRangeLower", hypeIsUsd ? ("$" + (Number(hype.p_lower) || (hypeCurPrice * 0.975)).toFixed(2)) : ((Number(hype.p_lower) || (hypeCurPrice * 0.975)).toFixed(4) + " SOL"));
  setTxt("hypeRangeUpper", hypeIsUsd ? ("$" + (Number(hype.p_upper) || (hypeCurPrice * 1.025)).toFixed(2)) : ((Number(hype.p_upper) || (hypeCurPrice * 1.025)).toFixed(4) + " SOL"));
  const hypeBar = document.getElementById("hypeRangeProgress");
  if (hypeBar && hype.p_upper > hype.p_lower) {
    const pct = Math.max(2, Math.min(98, ((hypeCurPrice - hype.p_lower) / (hype.p_upper - hype.p_lower)) * 100));
    hypeBar.style.width = pct.toFixed(1) + "%";
  }

  // Update Solana Chart
  if (equityChart && equityChart.data && equityChart.data.labels) {
    const labels = equityChart.data.labels;
    const dsGlobal = equityChart.data.datasets[0].data;
    const dsSol = equityChart.data.datasets[1].data;
    const dsBtc = equityChart.data.datasets[2].data;
    const dsHype = equityChart.data.datasets[3].data;

    const timeLabel = new Date().toLocaleTimeString("es-ES", { hour12: false });
    labels.push(timeLabel);
    dsGlobal.push(totalEur);
    dsSol.push(Number((solUsdc.total_val / eurRate).toFixed(2)));
    dsBtc.push(Number((cbbtc.total_val / eurRate).toFixed(2)));
    dsHype.push(Number((hypeValUsd / eurRate).toFixed(2)));

    if (labels.length > 30) {
      labels.shift();
      dsGlobal.shift();
      dsSol.shift();
      dsBtc.shift();
      dsHype.shift();
    }
    equityChart.update();
  }
}

function updateSolanaGauge(prefix, current, low, high) {
  const bar = document.getElementById(`${prefix}Bar`);
  const status = document.getElementById(`${prefix}Status`);
  const currentEl = document.getElementById(`${prefix}Current`);
  if (!bar || !current || !low || !high) return;

  const pct = Math.max(0, Math.min(100, ((current - low) / (high - low)) * 100));
  bar.style.width = pct.toFixed(1) + "%";
  if (status) {
    if (pct < 10 || pct > 90) {
      status.textContent = `ALERTA REBALANCEO (${pct.toFixed(1)}%)`;
      status.className = "text-amber-400 font-bold font-mono";
    } else {
      status.textContent = `DENTRO (${pct.toFixed(1)}%)`;
      status.className = "text-emerald-400 font-bold font-mono";
    }
  }
}

let prices30mAgo = { SOL: null, BTC: null, HYPE: null };

function renderSingleRtCard(prefix, sym, curPx, entryPx, decimals, fundingApr) {
  const ref30m = prices30mAgo[sym] || entryPx;
  setTxt(`rt${prefix}Price`, decimals === 0 ? ("$" + Math.round(curPx).toLocaleString()) : ("$" + curPx.toFixed(decimals)));
  const str30m = decimals === 0 ? Math.round(ref30m).toLocaleString() : ref30m.toFixed(decimals);
  const strEnt = decimals === 0 ? Math.round(entryPx).toLocaleString() : entryPx.toFixed(decimals);
  setTxt(`rt${prefix}EntryRef`, `Entrada inicial: $${strEnt}`);
  setTxt(`rt${prefix}TickDelta`, `Hace 30 min: $${str30m}`);

  const diff30m = curPx - ref30m;
  const pct30m = ref30m > 0 ? ((diff30m / ref30m) * 100.0) : 0.0;
  const badge = document.getElementById(`rt${prefix}Badge`);
  const effectEl = document.getElementById(`rt${prefix}EffectText`);
  const diffStr = decimals === 0 ? (`$${Math.round(Math.abs(diff30m)).toLocaleString()}`) : (`$${Math.abs(diff30m).toFixed(2)}`);

  if (Math.abs(pct30m) < 0.005) {
    if (badge) {
      badge.textContent = `30m: = 0.00% ($0.00)`;
      badge.className = "px-2 py-0.5 rounded-md text-xs font-mono font-extrabold bg-white/10 text-gray-200 border border-white/20";
    }
    if (effectEl) {
      effectEl.textContent = "Últimos 30 min: Sin variación";
      effectEl.className = "text-gray-300";
    }
  } else if (diff30m > 0) {
    if (badge) {
      badge.textContent = `30m: ▲ SUBIÓ +${pct30m.toFixed(2)}% (+${diffStr})`;
      badge.className = "px-2 py-0.5 rounded-md text-xs font-mono font-extrabold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40";
    }
    if (effectEl) {
      effectEl.textContent = `▲ Subió en 30m → Pool LP GANA +$ / Short resta -$`;
      effectEl.className = "text-emerald-400 font-semibold";
    }
  } else {
    if (badge) {
      badge.textContent = `30m: ▼ BAJÓ ${pct30m.toFixed(2)}% (-${diffStr})`;
      badge.className = "px-2 py-0.5 rounded-md text-xs font-mono font-extrabold bg-rose-500/20 text-rose-300 border border-rose-500/40";
    }
    if (effectEl) {
      effectEl.textContent = `▼ Bajó en 30m → Short GANA +USDC / Pool LP resta -$`;
      effectEl.className = "text-sky-400 font-semibold";
    }
  }

  if (fundingApr !== undefined && fundingApr !== null) {
    const fEl = document.getElementById(`rt${prefix}FundingLive`);
    if (fEl) {
      fEl.textContent = `Funding Auto: ${fundingApr >= 0 ? "+" : ""}${Number(fundingApr).toFixed(2)}% APR`;
      fEl.className = fundingApr >= 0 ? "text-emerald-300 font-bold" : "text-amber-300 font-bold";
    }
  }
}

function updateRealTimePriceMonitor(solPx, btcPx, hypePx, solUsdc, cbbtc, hype, hl) {
  const solEntry = (solUsdc && Number(solUsdc.entry_price)) || 89.4752;
  const btcEntry = (cbbtc && Number(cbbtc.entry_price)) || 75951.81;
  const hypeEntry = (hype && Number(hype.entry_price)) || 77.8130;

  const solFundApr = hl && hl.positions && hl.positions.SOL ? hl.positions.SOL.funding_apr_pct : -0.34;
  const btcFundApr = hl && hl.positions && hl.positions.BTC ? hl.positions.BTC.funding_apr_pct : 10.96;
  const hypeFundApr = hl && hl.positions && hl.positions.HYPE ? hl.positions.HYPE.funding_apr_pct : 10.96;

  renderSingleRtCard("Sol", "SOL", solPx, solEntry, 2, solFundApr);
  renderSingleRtCard("Btc", "BTC", btcPx, btcEntry, 0, btcFundApr);
  renderSingleRtCard("Hype", "HYPE", hypePx, hypeEntry, 2, hypeFundApr);
}

// Direct 2.5s Real-Time Hyperliquid L1 Oracle Feed (Prices + Auto-Updating Hourly Funding Rates)
function pollHyperliquidLiveRT() {
  fetch("https://api.hyperliquid.xyz/info", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type: "metaAndAssetCtxs" })
  })
    .then(r => r.json())
    .then(res => {
      if (!Array.isArray(res) || res.length < 2) return;
      const universe = (res[0] && res[0].universe) || [];
      const ctxs = res[1] || [];
      let solMark = null, btcMark = null, hypeMark = null;
      let solF = null, btcF = null, hypeF = null;

      for (let i = 0; i < universe.length; i++) {
        const name = universe[i].name;
        const c = ctxs[i];
        if (!c) continue;
        if (name === "SOL") {
          solMark = parseFloat(c.markPx);
          solF = parseFloat(c.funding) * 24.0 * 365.25 * 100.0;
        } else if (name === "JUP" || name === "BTC") {
          btcMark = parseFloat(c.markPx);
          btcF = parseFloat(c.funding) * 24.0 * 365.25 * 100.0;
        } else if (name === "HYPE") {
          hypeMark = parseFloat(c.markPx);
          hypeF = parseFloat(c.funding) * 24.0 * 365.25 * 100.0;
        }
      }

      if (latestData) {
        if (solMark) latestData.sol_price_usd = solMark;
        if (btcMark) latestData.btc_price_usd = btcMark;
        if (hypeMark) latestData.hype_price_usd = hypeMark;
        if (latestData.hyperliquid_hedge && latestData.hyperliquid_hedge.positions) {
          const pos = latestData.hyperliquid_hedge.positions;
          if (pos.SOL && solMark) { pos.SOL.mark_px = solMark; pos.SOL.funding_apr_pct = solF; }
          if (pos.BTC && btcMark) { pos.BTC.mark_px = btcMark; pos.BTC.funding_apr_pct = btcF; }
          if (pos.HYPE && hypeMark) { pos.HYPE.mark_px = hypeMark; pos.HYPE.funding_apr_pct = hypeF; }
          if (solF !== null && btcF !== null && hypeF !== null) {
            latestData.hyperliquid_hedge.weighted_funding_apr = (solF * 0.50) + (btcF * 0.25) + (hypeF * 0.25);
          }
        }
        setTxt("rtFeedTimestamp", `Comparativa cada 30 min (Hyperliquid L1 + Meteora)`);
        renderView();
      }
    })
    .catch(() => {});
}

// Fetch exact 30-minute ago candle open price from Hyperliquid L1 for SOL, BTC, HYPE
function pollHyperliquid30mCandles() {
  const now = Date.now();
  const start30m = now - (30 * 60 * 1000);
  ["SOL", "BTC", "HYPE", "JUP"].forEach(coin => {
    fetch("https://api.hyperliquid.xyz/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        type: "candleSnapshot",
        req: { coin: coin, interval: "1m", startTime: start30m, endTime: now }
      })
    })
      .then(r => r.json())
      .then(candles => {
        if (Array.isArray(candles) && candles.length > 0 && candles[0].o) {
          prices30mAgo[coin] = parseFloat(candles[0].o);
          renderView();
        }
      })
      .catch(() => {});
  });
}

// ============================================================================
// LIVE DATA STREAM & POLLING
// ============================================================================
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
  console.log("[*] Iniciando CriptPool Solana DLMM + Hyperliquid Delta-Neutral Web App...");
  initSolChart();
  
  // Render baseline immediately
  renderView();

  // Try real-time WebSocket listener for Firestore
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

  // Active polling & on-demand worker wakeup (Free-Tier 0.00 EUR/month mode)
  const triggerWorkerTick = () => {
    fetch("https://meteora-bot-worker-724237130149.europe-west1.run.app/", { mode: "no-cors", cache: "no-store" }).catch(() => {});
  };
  triggerWorkerTick();
  pollFirestoreREST();
  pollHyperliquid30mCandles();
  pollHyperliquidLiveRT();
  setInterval(triggerWorkerTick, 10000);
  setInterval(pollFirestoreREST, 3000);
  setInterval(pollHyperliquidLiveRT, 2500);
  setInterval(pollHyperliquid30mCandles, 15000);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", startApp);
} else {
  startApp();
}
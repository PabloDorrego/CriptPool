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
let latestData = null;
let lastUpdateEpoch = Date.now();

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

// Chart.js Setup for Tri-Pool Portfolio
function initChart() {
  const canvas = document.getElementById("equityChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  equityChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Cartera Total (€)",
          borderColor: "#14F195",
          backgroundColor: "rgba(20, 241, 149, 0.08)",
          fill: true,
          tension: 0.25,
          data: [],
          borderWidth: 2.5,
          pointRadius: 2,
          pointHoverRadius: 5
        },
        {
          label: "Pool SOL-USDC (50%)",
          borderColor: "#00C274",
          data: [],
          borderWidth: 1.5,
          tension: 0.25,
          pointRadius: 0
        },
        {
          label: "Pool cbBTC-USDC (25%)",
          borderColor: "#F7931A",
          data: [],
          borderWidth: 1.5,
          tension: 0.25,
          pointRadius: 0
        },
        {
          label: "Pool HYPE-SOL (25%)",
          borderColor: "#38BDF8",
          data: [],
          borderWidth: 1.5,
          tension: 0.25,
          pointRadius: 0
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { labels: { color: "#A0AEC0", font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: function(context) {
              return `${context.dataset.label}: ${context.parsed.y.toFixed(3)} €`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#718096", maxTicksLimit: 8 }
        },
        y: {
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: {
            color: "#718096",
            callback: function(v) { return v.toFixed(2) + " €"; }
          }
        }
      }
    }
  });
}

function renderView() {
  if (!latestData) return;

  const solPrice = Number(latestData.sol_price_usd) || 91.50;
  const btcPrice = Number(latestData.btc_price_usd) || 76800.0;
  const hypePriceSol = Number(latestData.hype_price_sol) || 0.910;
  const hypePriceUsd = Number(latestData.hype_price_usd) || (hypePriceSol * solPrice);
  const eurRate = Number(latestData.eur_usd_rate) || 1.08;

  setTxt("solSpotPrice", "$" + solPrice.toFixed(2));
  setTxt("btcSpotPrice", "$" + Math.round(btcPrice).toLocaleString());

  const comb = latestData.portfolio_combined || {};
  const solUsdc = latestData.sol_usdc || {};
  const cbbtc = latestData.cbbtc_usdc || {};
  const hype = latestData.hype_sol || {};
  const tokens = latestData.tokens || {};

  // ==========================================
  // 0. DESGLOSE DE COMPRA INICIAL (1.000 €)
  // ==========================================
  // 500 € a SOL-USDC (250 € en SOL + 250 € en USDC)
  const initSolAmt = (250.0 * eurRate) / solPrice;
  const initUsdcSol = 250.0 * eurRate;
  setTxt("initSolUsdcSol", `~${initSolAmt.toFixed(3)} SOL ($${initUsdcSol.toFixed(2)})`);
  setTxt("initSolUsdcUsdc", `${initUsdcSol.toFixed(2)} USDC (250 €)`);

  // 250 € a cbBTC-USDC (125 € en cbBTC + 125 € en USDC)
  const initBtcAmt = (125.0 * eurRate) / btcPrice;
  const initUsdcBtc = 125.0 * eurRate;
  setTxt("initCbbtcCoin", `~${initBtcAmt.toFixed(6)} cbBTC ($${initUsdcBtc.toFixed(2)})`);
  setTxt("initCbbtcUsdc", `${initUsdcBtc.toFixed(2)} USDC (125 €)`);

  // 250 € a HYPE-SOL (125 € en HYPE + 125 € en SOL)
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

  // Col 1: Cartera Global Total
  const totalEur = Number(comb.total_portfolio_eur) || 1000.0;
  const totalUsd = Number(comb.total_portfolio_usd) || 1080.0;
  const feesEur = Number(comb.total_fees_eur) || 0.0;
  const feesCapPct = Number(comb.fees_vs_capital_pct) || 0.0;
  const roiPct = Number(comb.combined_roi_pct) || 0.0;
  const realApr = Number(comb.real_fee_apr) || 0.0;
  const realApy = Number(comb.real_fee_apy) || 0.0;

  setTxt("globalPortfolioEur", totalEur.toFixed(2) + " €");
  setTxt("globalPortfolioUsd", "$" + totalUsd.toFixed(2));
  setTxt("globalFeesEur", "+" + feesEur.toFixed(4) + " €");
  setTxt("globalFeesVsCapPct", (feesCapPct >= 0 ? "+" : "") + feesCapPct.toFixed(3) + "%");
  setTxt("globalRoiPct", (roiPct >= 0 ? "+" : "") + roiPct.toFixed(3) + "%");
  setTxt("globalAprApy", `${realApr.toFixed(1)}% / ${realApy > 999 ? '>999%' : realApy.toFixed(1) + '%'}`);

  // Col 2: Pool SOL-USDC (50%)
  const solUsdcTotalVal = Number(solUsdc.total_val) || 540.0;
  const solUsdcFees = Number(solUsdc.accumulated_fees) || 0.0;
  const solUsdcFeesCapPct = Number(solUsdc.fees_vs_capital_pct) || 0.0;
  const solUsdcRoi = Number(solUsdc.roi_pct) || 0.0;
  const solUsdcApr = Number(solUsdc.real_fee_apr) || 0.0;

  setTxt("solUsdcVal", "$" + solUsdcTotalVal.toFixed(2));
  setTxt("solUsdcFees", "+$" + solUsdcFees.toFixed(4));
  setTxt("solUsdcFeesCapPct", (solUsdcFeesCapPct >= 0 ? "+" : "") + solUsdcFeesCapPct.toFixed(3) + "%");
  setTxt("solUsdcRoiPct", (solUsdcRoi >= 0 ? "+" : "") + solUsdcRoi.toFixed(3) + "%");
  setTxt("solUsdcApr", solUsdcApr.toFixed(1) + "% APR");

  // Col 3: Pool cbBTC-USDC (25%)
  const cbbtcTotalVal = Number(cbbtc.total_val) || 270.0;
  const cbbtcFees = Number(cbbtc.accumulated_fees) || 0.0;
  const cbbtcFeesCapPct = Number(cbbtc.fees_vs_capital_pct) || 0.0;
  const cbbtcRoi = Number(cbbtc.roi_pct) || 0.0;
  const cbbtcApr = Number(cbbtc.real_fee_apr) || 0.0;

  setTxt("cbbtcVal", "$" + cbbtcTotalVal.toFixed(2));
  setTxt("cbbtcFees", "+$" + cbbtcFees.toFixed(4));
  setTxt("cbbtcFeesCapPct", (cbbtcFeesCapPct >= 0 ? "+" : "") + cbbtcFeesCapPct.toFixed(3) + "%");
  setTxt("cbbtcRoiPct", (cbbtcRoi >= 0 ? "+" : "") + cbbtcRoi.toFixed(3) + "%");
  setTxt("cbbtcApr", cbbtcApr.toFixed(1) + "% APR");

  // Col 4: Pool HYPE-SOL (25%)
  const hypeTotalValSol = Number(hype.total_val) || 0.0;
  const hypeTotalValUsd = hypeTotalValSol * solPrice;
  const hypeFeesSol = Number(hype.accumulated_fees) || 0.0;
  const hypeFeesUsd = hypeFeesSol * solPrice;
  const hypeRoi = Number(hype.roi_pct) || 0.0;
  const hypeApr = Number(hype.real_fee_apr) || 0.0;

  setTxt("hypeValSol", hypeTotalValSol.toFixed(4) + " SOL");
  setTxt("hypeValUsd", "$" + hypeTotalValUsd.toFixed(2));
  setTxt("hypeFees", "+" + hypeFeesSol.toFixed(5) + " SOL");
  setTxt("hypeFeesUsd", "+$" + hypeFeesUsd.toFixed(4));
  setTxt("hypeRoiPct", (hypeRoi >= 0 ? "+" : "") + hypeRoi.toFixed(3) + "%");
  setTxt("hypeApr", hypeApr.toFixed(1) + "% APR");

  // ==========================================
  // 2. KPIS DE RIESGO Y OPERATIVA
  // ==========================================

  // Global Risk
  const ilEur = Number(comb.il_amount_eur) || 0.0;
  const netAlphaEur = Number(comb.net_vs_hodl_eur) || 0.0;
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
  const solDistLower = Number(solUsdc.dist_p_lower_pct) || 7.5;
  const solDistUpper = Number(solUsdc.dist_p_upper_pct) || 7.5;
  const solDistRebalLower = Number(solUsdc.dist_rebal_lower_pct) || 6.75;
  const solDistRebalUpper = Number(solUsdc.dist_rebal_upper_pct) || 6.75;
  const solMinRebal = Math.min(solDistRebalLower, solDistRebalUpper);
  const solNetAlpha = Number(solUsdc.net_vs_hodl) || 0.0;

  setTxt("solDistLower", solDistLower.toFixed(2) + "%");
  setTxt("solDistUpper", solDistUpper.toFixed(2) + "%");
  setTxt("solDistRebal", solMinRebal > 1.0 ? `Seguro (${solMinRebal.toFixed(1)}%)` : `⚠️ ALERTA (${solMinRebal.toFixed(2)}%)`);
  setTxt("solNetAlpha", (solNetAlpha >= 0 ? "+$" : "-$") + Math.abs(solNetAlpha).toFixed(4));
  setTxt("solActivityRatio", (Number(solUsdc.activity_ratio_pct) || 100.0).toFixed(1) + "%");

  // cbBTC-USDC Risk
  const btcDistLower = Number(cbbtc.dist_p_lower_pct) || 6.0;
  const btcDistUpper = Number(cbbtc.dist_p_upper_pct) || 6.0;
  const btcDistRebalLower = Number(cbbtc.dist_rebal_lower_pct) || 5.4;
  const btcDistRebalUpper = Number(cbbtc.dist_rebal_upper_pct) || 5.4;
  const btcMinRebal = Math.min(btcDistRebalLower, btcDistRebalUpper);
  const btcNetAlpha = Number(cbbtc.net_vs_hodl) || 0.0;

  setTxt("btcDistLower", btcDistLower.toFixed(2) + "%");
  setTxt("btcDistUpper", btcDistUpper.toFixed(2) + "%");
  setTxt("btcDistRebal", btcMinRebal > 1.0 ? `Seguro (${btcMinRebal.toFixed(1)}%)` : `⚠️ ALERTA (${btcMinRebal.toFixed(2)}%)`);
  setTxt("btcNetAlpha", (btcNetAlpha >= 0 ? "+$" : "-$") + Math.abs(btcNetAlpha).toFixed(4));
  setTxt("btcActivityRatio", (Number(cbbtc.activity_ratio_pct) || 100.0).toFixed(1) + "%");

  // HYPE-SOL Risk
  const hypeDistLower = Number(hype.dist_p_lower_pct) || 8.0;
  const hypeDistUpper = Number(hype.dist_p_upper_pct) || 8.0;
  const hypeDistRebalLower = Number(hype.dist_rebal_lower_pct) || 7.2;
  const hypeDistRebalUpper = Number(hype.dist_rebal_upper_pct) || 7.2;
  const hypeMinRebal = Math.min(hypeDistRebalLower, hypeDistRebalUpper);
  const hypeNetAlpha = Number(hype.net_vs_hodl) || 0.0;

  setTxt("hypeDistLower", hypeDistLower.toFixed(2) + "%");
  setTxt("hypeDistUpper", hypeDistUpper.toFixed(2) + "%");
  setTxt("hypeDistRebal", hypeMinRebal > 1.0 ? `Seguro (${hypeMinRebal.toFixed(1)}%)` : `⚠️ ALERTA (${hypeMinRebal.toFixed(2)}%)`);
  setTxt("hypeNetAlpha", (hypeNetAlpha >= 0 ? "+" : "") + hypeNetAlpha.toFixed(5) + " SOL");
  setTxt("hypeActivityRatio", (Number(hype.activity_ratio_pct) || 100.0).toFixed(1) + "%");

  // ==========================================
  // 3. KPIS DE COSTES Y EFICIENCIA
  // ==========================================

  // Global Costs
  setTxt("globalRebalances", String(comb.total_rebalances || 0));
  setTxt("globalGasCostEur", (Number(comb.total_rebalance_costs_eur) || 0.0).toFixed(2) + " €");
  setTxt("globalFrictionRatio", (Number(comb.friction_ratio_pct) || 0.0).toFixed(2) + "%");

  // SOL-USDC Costs
  setTxt("solRebalances", String(solUsdc.total_rebalances || 0));
  setTxt("solGasCost", "$" + (Number(solUsdc.total_rebal_costs) || 0.0).toFixed(2));
  setTxt("solFrictionRatio", (Number(solUsdc.friction_ratio_pct) || 0.0).toFixed(2) + "%");

  // cbBTC-USDC Costs
  setTxt("btcRebalances", String(cbbtc.total_rebalances || 0));
  setTxt("btcGasCost", "$" + (Number(cbbtc.total_rebal_costs) || 0.0).toFixed(2));
  setTxt("btcFrictionRatio", (Number(cbbtc.friction_ratio_pct) || 0.0).toFixed(2) + "%");

  // HYPE-SOL Costs
  setTxt("hypeRebalances", String(hype.total_rebalances || 0));
  setTxt("hypeGasCost", (Number(hype.total_rebal_costs) || 0.0).toFixed(4) + " SOL");
  setTxt("hypeFrictionRatio", (Number(hype.friction_ratio_pct) || 0.0).toFixed(2) + "%");

  // ==========================================
  // 4. RANGES VISUALIZERS (3 Sliders)
  // ==========================================

  // Range 1: SOL-USDC
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

  // Range 2: cbBTC-USDC
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

  // Range 3: HYPE-SOL
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

  // Update Equity Chart
  if (equityChart) {
    const timeLabel = new Date().toLocaleTimeString("es-ES", { hour12: false });
    const labels = equityChart.data.labels;
    const dsGlobal = equityChart.data.datasets[0].data;
    const dsSol = equityChart.data.datasets[1].data;
    const dsBtc = equityChart.data.datasets[2].data;
    const dsHype = equityChart.data.datasets[3].data;

    const solEur = solUsdcTotalVal / eurRate;
    const btcEur = cbbtcTotalVal / eurRate;
    const hypeEur = hypeTotalValUsd / eurRate;

    if (labels.length === 0 || labels[labels.length - 1] !== timeLabel) {
      labels.push(timeLabel);
      dsGlobal.push(totalEur);
      dsSol.push(solEur);
      dsBtc.push(btcEur);
      dsHype.push(hypeEur);

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
}

// REST Fallback for real-time polling
function pollFirestoreREST() {
  fetch("https://firestore.googleapis.com/v1/projects/criptpool-meteora/databases/(default)/documents/meteora_bot/current_state?nocache=" + Date.now())
    .then(r => r.json())
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
    .catch(err => console.warn("[!] Error en REST fallback:", err));
}

// Heartbeat ticker
setInterval(() => {
  const sec = Math.round((Date.now() - lastUpdateEpoch) / 1000);
  setTxt("tickerSeconds", sec + "s");
  const el = document.getElementById("lastUpdated");
  if (el) {
    if (sec <= 10) {
      el.textContent = "Sincronizado ahora mismo";
      el.className = "text-[11px] text-emerald-400 font-mono";
    } else {
      el.textContent = `Actualizado hace ${sec}s`;
      el.className = "text-[11px] text-gray-400 font-mono";
    }
  }
}, 1000);

// Initialize Listeners
window.addEventListener("DOMContentLoaded", () => {
  initChart();

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

  // Polling fallback every 3 seconds
  pollFirestoreREST();
  setInterval(pollFirestoreREST, 3000);
});

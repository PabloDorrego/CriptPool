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
let currentTab = "combined";
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

// Chart.js Setup
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
          label: "Pool SOL-USDC (€)",
          borderColor: "#00C274",
          data: [],
          borderWidth: 1.5,
          tension: 0.25,
          pointRadius: 0
        },
        {
          label: "Pool JitoSOL-SOL (€)",
          borderColor: "#9945FF",
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

function switchTab(tab) {
  currentTab = tab;
  ["combined", "sol_usdc", "jitosol"].forEach(t => {
    const el = document.getElementById(`tab-${t}`);
    if (el) {
      if (t === tab) {
        el.className = "px-4 py-2 rounded-xl text-xs font-semibold border transition-all tab-active flex items-center gap-2";
      } else {
        el.className = "px-4 py-2 rounded-xl text-xs font-semibold border border-transparent text-gray-400 hover:text-white transition-all flex items-center gap-2";
      }
    }
  });
  renderView();
}

function renderView() {
  if (!latestData) return;

  const solPrice = Number(latestData.sol_price_usd) || 93.50;
  const eurRate = Number(latestData.eur_usd_rate) || 1.08;

  setTxt("solSpotPrice", "$" + solPrice.toFixed(2));

  const comb = latestData.portfolio_combined || {};
  const solUsdc = latestData.sol_usdc || {};
  const jito = latestData.jitosol_sol || {};
  const tokens = latestData.tokens || {};

  // 1. EXACT TOKEN BALANCES
  const solFromSolUsdc = Number(solUsdc.token_x) || 0.0;
  const usdcTotal = Number(solUsdc.token_y) || 0.0;
  const jitoTotal = Number(jito.token_x) || 0.0;
  const solFromJito = Number(jito.token_y) || 0.0;

  const totalSolHeld = tokens.sol_total !== undefined ? Number(tokens.sol_total) : (solFromSolUsdc + solFromJito);
  const totalSolUsdVal = totalSolHeld * solPrice;
  const totalSolEurVal = totalSolUsdVal / eurRate;

  const jitoSolRatio = Number(jito.current_price) || 1.3082;
  const jitoTotalUsdVal = jitoTotal * (jitoSolRatio * solPrice);
  const jitoTotalEurVal = jitoTotalUsdVal / eurRate;

  setTxt("tokenSolTotal", totalSolHeld.toFixed(4) + " SOL");
  setTxt("tokenSolUsdVal", `${totalSolEurVal.toFixed(2)} € ($${totalSolUsdVal.toFixed(2)} USD)`);
  setTxt("tokenSolBreakdown", `(${solFromSolUsdc.toFixed(3)} SOL en SOL-USDC + ${solFromJito.toFixed(3)} SOL en JitoSOL-SOL)`);

  setTxt("tokenUsdcTotal", "$" + usdcTotal.toFixed(2) + " USDC");
  setTxt("tokenUsdcUsdVal", `${(usdcTotal / eurRate).toFixed(2)} € ($${usdcTotal.toFixed(2)} USD)`);

  setTxt("tokenJitoTotal", jitoTotal.toFixed(4) + " JitoSOL");
  setTxt("tokenJitoUsdVal", `${jitoTotalEurVal.toFixed(2)} € ($${jitoTotalUsdVal.toFixed(2)} USD)`);
  setTxt("jitoExchangeRate", `Ratio actual: 1 JitoSOL = ${jitoSolRatio.toFixed(4)} SOL (~$${(jitoSolRatio * solPrice).toFixed(2)})`);

  // 2. FINANCIAL VALUATIONS
  const solUsdcValUsd = Number(solUsdc.total_val) || (solFromSolUsdc * solPrice + usdcTotal);
  const solUsdcValEur = solUsdcValUsd / eurRate;
  
  const jitoSolValInSol = Number(jito.total_val) || (jitoTotal * jitoSolRatio + solFromJito);
  const jitoValUsd = jitoSolValInSol * solPrice;
  const jitoValEur = jitoValUsd / eurRate;

  const totalCombUsd = Number(comb.total_portfolio_usd) || (solUsdcValUsd + jitoValUsd);
  const totalCombEur = Number(comb.total_portfolio_eur) || (totalCombUsd / eurRate);

  const totalFeesUsd = Number(comb.total_fees_usd) || 0;
  const totalFeesEur = Number(comb.total_fees_eur) || (totalFeesUsd / eurRate);

  // Sidebar Distribution Boxes
  setTxt("solUsdcValBox", `${solUsdcValEur.toFixed(2)} € ($${solUsdcValUsd.toFixed(2)} USD)`);
  const solRoi = Number(solUsdc.roi_pct) || 0;
  setTxt("solUsdcRoiBox", (solRoi >= 0 ? "+" : "") + solRoi.toFixed(2) + "% ROI");
  
  setTxt("jitoValBox", `${jitoValEur.toFixed(2)} € (~${jitoSolValInSol.toFixed(3)} SOL)`);
  const jitoRoi = Number(jito.roi_pct) || 0;
  setTxt("jitoRoiBox", (jitoRoi >= 0 ? "+" : "") + jitoRoi.toFixed(2) + "% en SOL");
  
  setTxt("totalFeesCombinedBox", `${totalFeesEur.toFixed(4)} € ($${totalFeesUsd.toFixed(4)} USD)`);

  // =========================================================================
  // 3. COMPARATIVE 3-COLUMN KPIS (GLOBAL vs SOL-USDC vs JITOSOL-SOL)
  // =========================================================================

  // --- CATEGORÍA 1: RENDIMIENTO Y RENTABILIDAD ---
  // Col 1: Global
  setTxt("globPortfolioVal", `${totalCombEur.toFixed(2)} € ($${totalCombUsd.toFixed(2)})`);
  setTxt("globAccumFees", `${totalFeesEur.toFixed(4)} € ($${totalFeesUsd.toFixed(4)})`);
  const globApr = Number(comb.real_fee_apr) || 45.0;
  const globApy = Number(comb.real_fee_apy) || globApr;
  setTxt("globAprApy", `${globApr.toFixed(1)}% APR / ${globApy.toFixed(1)}% APY`);
  const globRoi = Number(comb.combined_roi_pct) || 0;
  setTxt("globRoiNeto", (globRoi >= 0 ? "+" : "") + globRoi.toFixed(3) + "% ROI");
  setCls("globRoiNeto", "font-bold font-mono " + (globRoi >= 0 ? "text-emerald-400" : "text-rose-400"));
  const globCapRecov = Number(comb.fees_vs_capital_pct) || ((totalFeesEur / 1000.0) * 100);
  setTxt("globCapRecovPct", `+${globCapRecov.toFixed(4)}% Cap Inicial`);

  // Col 2: SOL-USDC
  setTxt("solUsdcPortfolioVal", `${solUsdcValEur.toFixed(2)} € ($${solUsdcValUsd.toFixed(2)})`);
  const solFeesEur = (Number(solUsdc.accumulated_fees) || 0) / eurRate;
  setTxt("solUsdcAccumFees", `${solFeesEur.toFixed(4)} € ($${(Number(solUsdc.accumulated_fees) || 0).toFixed(4)})`);
  const solApr = Number(solUsdc.real_fee_apr) || 55.0;
  const solApy = Number(solUsdc.real_fee_apy) || solApr;
  setTxt("solUsdcAprApy", `${solApr.toFixed(1)}% APR / ${solApy.toFixed(1)}% APY`);
  setTxt("solUsdcRoiNeto", (solRoi >= 0 ? "+" : "") + solRoi.toFixed(3) + "% ROI");
  setCls("solUsdcRoiNeto", "font-bold font-mono " + (solRoi >= 0 ? "text-emerald-400" : "text-rose-400"));

  // Col 3: JitoSOL-SOL
  setTxt("jitoPortfolioVal", `${jitoValEur.toFixed(2)} € (~${jitoSolValInSol.toFixed(3)} SOL)`);
  const jitoFeesSol = Number(jito.accumulated_fees) || 0;
  const jitoFeesEur = (jitoFeesSol * solPrice) / eurRate;
  setTxt("jitoAccumFees", `${jitoFeesEur.toFixed(4)} € (${jitoFeesSol.toFixed(5)} SOL)`);
  const jitoApr = Number(jito.real_fee_apr) || 24.0;
  setTxt("jitoAprApy", `${jitoApr.toFixed(1)}% APR (+7.5% Staking)`);
  setTxt("jitoRoiNeto", (jitoRoi >= 0 ? "+" : "") + jitoRoi.toFixed(3) + "% en SOL");
  setCls("jitoRoiNeto", "font-bold font-mono " + (jitoRoi >= 0 ? "text-purple-400" : "text-rose-400"));

  // --- CATEGORÍA 2: RIESGO Y OPERATIVA ---
  // Col 1: Global
  const globIlEur = Number(comb.il_amount_eur) || 0;
  const globNetAlphaEur = Number(comb.net_vs_hodl_eur) || (totalFeesEur + globIlEur);
  setTxt("globIlAmount", `${globIlEur >= 0 ? "+" : ""}${globIlEur.toFixed(4)} €`);
  setTxt("globNetAlpha", `${globNetAlphaEur >= 0 ? "+" : ""}${globNetAlphaEur.toFixed(4)} € Net Alpha`);
  const globCoversIl = comb.fees_cover_il !== undefined ? Boolean(comb.fees_cover_il) : (totalFeesEur >= Math.abs(globIlEur));
  if (globCoversIl) {
    setTxt("globIlCoverBadge", "FEES SUPERAN IL");
    setCls("globIlCoverBadge", "px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono text-[10px] font-bold");
  } else {
    setTxt("globIlCoverBadge", "IL TEMPORAL");
    setCls("globIlCoverBadge", "px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 font-mono text-[10px] font-bold");
  }
  const globAct = comb.activity_ratio_pct !== undefined ? Number(comb.activity_ratio_pct) : 100.0;
  setTxt("globActivityRatio", `${globAct.toFixed(1)}% En Bins Activos`);

  // Col 2: SOL-USDC
  const solInRange = Boolean(solUsdc.is_in_range);
  setTxt("solUsdcRangeBadge", solInRange ? "DENTRO DEL RANGO" : "FUERA DE RANGO");
  setCls("solUsdcRangeBadge", solInRange ? "px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono text-[10px] font-bold" : "px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 font-mono text-[10px] font-bold");
  const distSolLow = Number(solUsdc.dist_p_lower_pct) || 7.28;
  const distSolHigh = Number(solUsdc.dist_p_upper_pct) || 7.76;
  setTxt("solUsdcDistBounds", `Inf: -${distSolLow.toFixed(2)}% | Sup: +${distSolHigh.toFixed(2)}%`);
  const solRebalMarg = Number(solUsdc.dist_rebal_lower_pct) || (distSolLow * 0.9);
  setTxt("solUsdcRebalMargin", `${solRebalMarg.toFixed(2)}% antes de recentrar`);
  const solIlUsd = Number(solUsdc.il_amount) || 0;
  const solIlEur = solIlUsd / eurRate;
  setTxt("solUsdcIlAmount", `${solIlEur >= 0 ? "+" : ""}${solIlEur.toFixed(4)} € (${(Number(solUsdc.il_pct) || 0).toFixed(2)}%)`);
  const solAlphaEur = (Number(solUsdc.net_vs_hodl) || 0) / eurRate;
  setTxt("solUsdcNetAlpha", `${solAlphaEur >= 0 ? "+" : ""}${solAlphaEur.toFixed(4)} €`);
  const solAct = solUsdc.activity_ratio_pct !== undefined ? Number(solUsdc.activity_ratio_pct) : 100.0;
  setTxt("solUsdcActivityRatio", `${solAct.toFixed(1)}% en rango`);

  // Col 3: JitoSOL-SOL
  const jitoInRange = Boolean(jito.is_in_range);
  setTxt("jitoRangeBadge", jitoInRange ? "PEGGED EN RANGO" : "FUERA DE RANGO");
  setCls("jitoRangeBadge", jitoInRange ? "px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 font-mono text-[10px] font-bold" : "px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 font-mono text-[10px] font-bold");
  const distJitoLow = Number(jito.dist_p_lower_pct) || 1.20;
  const distJitoHigh = Number(jito.dist_p_upper_pct) || 1.20;
  setTxt("jitoDistBounds", `Inf: -${distJitoLow.toFixed(2)}% | Sup: +${distJitoHigh.toFixed(2)}%`);
  const jitoRebalMarg = Number(jito.dist_rebal_lower_pct) || (distJitoLow * 0.92);
  setTxt("jitoRebalMargin", `${jitoRebalMarg.toFixed(2)}% margen al peg`);
  const jitoAct = jito.activity_ratio_pct !== undefined ? Number(jito.activity_ratio_pct) : 100.0;
  setTxt("jitoActivityRatio", `${jitoAct.toFixed(1)}% en rango`);

  // --- CATEGORÍA 3: COSTES Y EFICIENCIA ---
  // Col 1: Global
  const globRebalCount = Number(comb.total_rebalances) || 0;
  setTxt("globRebalCountBadge", `${globRebalCount} Rebalanceos`);
  const globRebalCostEur = Number(comb.total_rebalance_costs_eur) || 0;
  setTxt("globTotalRebalCost", `${globRebalCostEur.toFixed(4)} € ($${(Number(comb.total_rebalance_costs_usd) || 0).toFixed(4)})`);
  const globFriction = Number(comb.friction_ratio_pct) || 0.0;
  setTxt("globFrictionRatio", `${globFriction.toFixed(1)}% Fricción`);
  setTxt("globNetEfficiency", globFriction === 0 ? "100% Beneficio Neto" : `${(100 - globFriction).toFixed(1)}% Retención`);

  // Col 2: SOL-USDC
  const solRebalCount = Number(solUsdc.total_rebalances) || 0;
  setTxt("solUsdcRebalCount", `${solRebalCount} Eventos`);
  setTxt("solUsdcRebalCost", `${((Number(solUsdc.total_rebal_costs) || 0) / eurRate).toFixed(4)} €`);
  setTxt("solUsdcFrictionRatio", `${(Number(solUsdc.friction_ratio_pct) || 0).toFixed(1)}%`);

  // Col 3: JitoSOL-SOL
  const jitoRebalCount = Number(jito.total_rebalances) || 0;
  setTxt("jitoRebalCount", `${jitoRebalCount} Eventos`);
  setTxt("jitoRebalCost", `${(((Number(jito.total_rebal_costs) || 0) * solPrice) / eurRate).toFixed(4)} €`);
  setTxt("jitoFrictionRatio", `${(Number(jito.friction_ratio_pct) || 0).toFixed(1)}%`);

  // =========================================================================
  // 4. DUAL RANGE VISUALIZERS (SOL-USDC and JitoSOL-SOL)
  // =========================================================================
  // Gauge 1: SOL-USDC
  const pSolLow = Number(solUsdc.p_lower) || (solPrice * 0.925);
  const pSolHigh = Number(solUsdc.p_upper) || (solPrice * 1.075);
  setTxt("solUsdcRangeText", `[$${pSolLow.toFixed(2)} - $${pSolHigh.toFixed(2)}]`);
  setTxt("lowerBoundSol", "$" + pSolLow.toFixed(2));
  setTxt("entryBoundSol", "$" + solPrice.toFixed(2));
  setTxt("upperBoundSol", "$" + pSolHigh.toFixed(2));
  const pinSol = document.getElementById("pricePinSol");
  if (pinSol && pSolHigh > pSolLow) {
    const pct = Math.max(0, Math.min(100, ((solPrice - pSolLow) / (pSolHigh - pSolLow)) * 100));
    pinSol.style.left = pct + "%";
  }
  setTxt("distLowTextSol", "Margen Inf: " + distSolLow.toFixed(1) + "%");
  setTxt("distHighTextSol", "Margen Sup: " + distSolHigh.toFixed(1) + "%");

  // Gauge 2: JitoSOL-SOL
  const pJitoLow = Number(jito.p_lower) || (jitoSolRatio * 0.988);
  const pJitoHigh = Number(jito.p_upper) || (jitoSolRatio * 1.012);
  setTxt("jitoRangeText", `[${pJitoLow.toFixed(4)} - ${pJitoHigh.toFixed(4)} SOL]`);
  setTxt("lowerBoundJito", pJitoLow.toFixed(4));
  setTxt("entryBoundJito", jitoSolRatio.toFixed(4));
  setTxt("upperBoundJito", pJitoHigh.toFixed(4));
  const pinJito = document.getElementById("pricePinJito");
  if (pinJito && pJitoHigh > pJitoLow) {
    const pct = Math.max(0, Math.min(100, ((jitoSolRatio - pJitoLow) / (pJitoHigh - pJitoLow)) * 100));
    pinJito.style.left = pct + "%";
  }
  setTxt("distLowTextJito", "Margen Inf: " + distJitoLow.toFixed(2) + "%");
  setTxt("distHighTextJito", "Margen Sup: " + distJitoHigh.toFixed(2) + "%");

  // Live Chart Real-Time Append
  if (equityChart && totalCombEur > 0) {
    const timeLabel = new Date().toLocaleTimeString();
    const l = equityChart.data.labels;
    if (l.length === 0 || l[l.length - 1] !== timeLabel) {
      if (l.length > 40) {
        l.shift();
        equityChart.data.datasets[0].data.shift();
        equityChart.data.datasets[1].data.shift();
        equityChart.data.datasets[2].data.shift();
      }
      l.push(timeLabel);
      equityChart.data.datasets[0].data.push(totalCombEur);
      equityChart.data.datasets[1].data.push(solUsdcValEur);
      equityChart.data.datasets[2].data.push(jitoValEur);
      equityChart.update("none");
    }
  }

  if (window.lucide) {
    try { lucide.createIcons(); } catch (e) {}
  }
}

// REST poller: Guaranteed 100% update in ALL browsers every 3s
async function pollFirestoreREST() {
  try {
    const url = "https://firestore.googleapis.com/v1/projects/criptpool-meteora/databases/(default)/documents/meteora_bot/current_state";
    const res = await fetch(url + "?t=" + Date.now(), { cache: "no-store" });
    if (res.ok) {
      const json = await res.json();
      const fields = json.fields || {};
      
      const parsed = {
        sol_price_usd: fields.sol_price_usd?.doubleValue || fields.sol_price_usd?.integerValue || 93.5,
        eur_usd_rate: fields.eur_usd_rate?.doubleValue || 1.08,
        portfolio_combined: parseMap(fields.portfolio_combined),
        sol_usdc: parseMap(fields.sol_usdc),
        jitosol_sol: parseMap(fields.jitosol_sol),
        tokens: parseMap(fields.tokens)
      };

      latestData = parsed;
      lastUpdateEpoch = Date.now();
      renderView();
      setTxt("connectionBadge", "EN VIVO (TICK CADA 10s)");
    }
  } catch (err) {
    console.warn("[!] Polling REST error:", err);
  }
}

function parseMap(mapField) {
  if (!mapField || !mapField.mapValue || !mapField.mapValue.fields) return {};
  const f = mapField.mapValue.fields;
  const out = {};
  for (const k in f) {
    if (f[k].doubleValue !== undefined) out[k] = parseFloat(f[k].doubleValue);
    else if (f[k].integerValue !== undefined) out[k] = parseInt(f[k].integerValue, 10);
    else if (f[k].stringValue !== undefined) out[k] = f[k].stringValue;
    else if (f[k].booleanValue !== undefined) out[k] = Boolean(f[k].booleanValue);
  }
  return out;
}

// Setup real-time listeners and second counter
function setupLiveStreams() {
  setInterval(pollFirestoreREST, 3000);
  pollFirestoreREST();

  // Seconds ticking countdown in header
  setInterval(() => {
    const diffSec = Math.floor((Date.now() - lastUpdateEpoch) / 1000);
    const lastEl = document.getElementById("lastUpdated");
    if (lastEl) {
      if (diffSec <= 1) {
        lastEl.textContent = "Sincronizado ahora mismo";
      } else {
        lastEl.textContent = `Actualizado hace ${diffSec}s`;
      }
    }
  }, 1000);

  if (db) {
    try {
      db.collection("meteora_bot").document("current_state").onSnapshot((doc) => {
        if (doc.exists) {
          latestData = doc.data();
          lastUpdateEpoch = Date.now();
          renderView();
        }
      });

      db.collection("meteora_bot").document("history").collection("rebalances")
        .orderBy("timestamp", "desc").limit(10)
        .onSnapshot((querySnapshot) => {
          const tbody = document.getElementById("rebalTableBody");
          if (!tbody || querySnapshot.empty) return;
          tbody.innerHTML = "";
          querySnapshot.forEach((doc) => {
            const ev = doc.data();
            const tr = document.createElement("tr");
            tr.className = "hover:bg-gray-800/30 transition-colors";
            tr.innerHTML = `
              <td class="py-3 px-4 font-mono text-gray-400">${new Date(ev.timestamp).toLocaleString()}</td>
              <td class="py-3 px-4 font-semibold text-white">${ev.pool || 'SOL-USDC'}</td>
              <td class="py-3 px-4 text-amber-400 font-semibold">#${ev.rebalance_number}</td>
              <td class="py-3 px-4 font-mono text-white">${Number(ev.price).toFixed(4)}</td>
              <td class="py-3 px-4 font-mono text-emerald-400">${Number(ev.swap_amount).toFixed(2)}</td>
              <td class="py-3 px-4 font-mono text-gray-400">${Number(ev.cost).toFixed(4)}</td>
              <td class="py-3 px-4 font-mono text-purple-400">[${Number(ev.new_bounds[0]).toFixed(2)} - ${Number(ev.new_bounds[1]).toFixed(2)}]</td>
            `;
            tbody.appendChild(tr);
          });
          setTxt("rebalStatusCount", querySnapshot.size + " eventos registrados");
        });
    } catch (e) {
      console.warn("Firestore onSnapshot error:", e);
    }
  }
}

window.addEventListener("DOMContentLoaded", () => {
  initChart();
  setupLiveStreams();
});

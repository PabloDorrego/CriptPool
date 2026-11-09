// ============================================================================
// CriptPool · Panel de Seguimiento (v30)
// Fuente de verdad: Firestore meteora_bot/current_state (escrito por el worker)
// + meteora_bot/history/snapshots para las series temporales.
// ============================================================================

const firebaseConfig = {
  apiKey: "AIzaSyAtBmFx1xpxc70BnFwkoOWXS9KeHHokwz8",
  authDomain: "criptpool-meteora.firebaseapp.com",
  projectId: "criptpool-meteora",
  storageBucket: "criptpool-meteora.firebasestorage.app",
  messagingSenderId: "724237130149"
};

const CFG = {
  restBase: "https://firestore.googleapis.com/v1/projects/criptpool-meteora/databases/(default)/documents",
  workerUrl: "https://meteora-bot-worker-724237130149.europe-west1.run.app/",
  targetAprMin: 85,
  targetAprMax: 120,
  testDays: 30,
  rebalThresh: 1.05,          // Igual que PositionTracker.rebal_thresh en el worker
  rebalConfirmSec: 1800,      // Igual que REBALANCE_CONFIRM_SEC en el worker
  maxLev: { SOL: 20, HYPE: 10, JUP: 10 } // Para estimar margen de mantenimiento (1 / (2·maxLev))
};

// Mapeo de los 3 pools. El pool SOL-HYPE reemplaza a JUP-USDC manteniendo compatibilidad de claves heredadas.
const POOLS = [
  { keys: ["sol_usdc"], label: "SOL-USDC", base: "SOL", perp: "SOL", volKey: "sol_usdc_24h_vol", color: "#34D399", role: "Motor principal (Bin 10)" },
  { keys: ["sol_hype", "jup_usdc", "cbbtc_usdc"], label: "SOL-HYPE", base: "SOL", perp: "SOL", volKey: "sol_hype_24h_vol", color: "#FBBF24", role: "Ultra-Yield 218% APR (Bin 4)" },
  { keys: ["hype_usdc", "hype_sol"], label: "HYPE-USDC", base: "HYPE", perp: "HYPE", volKey: "hype_sol_24h_vol", color: "#38BDF8", role: "Acelerador HYPE (Bin 20)" }
];

let state = null;          // Último documento current_state
let snapshots = [];        // Snapshots históricos del ciclo actual
let lastFetchMs = 0;
let historyChart = null, bridgeChart = null;
let activeTab = "equity";

// ----------------------------------------------------------------------------
// Formateadores (es-ES)
// ----------------------------------------------------------------------------
const nfCache = {};
const nf = (d) => nfCache[d] || (nfCache[d] = new Intl.NumberFormat("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d }));
const num = (v, fb = 0) => { const n = Number(v); return Number.isFinite(n) ? n : fb; };
const eur = (v, d = 2) => nf(d).format(v) + " €";
const sEur = (v, d = 2) => (v >= 0 ? "+" : "−") + nf(d).format(Math.abs(v)) + " €";
const usd = (v, d = 2) => nf(d).format(v) + " $";
const sUsd = (v, d = 2) => (v >= 0 ? "+" : "−") + nf(d).format(Math.abs(v)) + " $";
const pct = (v, d = 2) => nf(d).format(v) + "%";
const sPct = (v, d = 2) => (v >= 0 ? "+" : "−") + nf(d).format(Math.abs(v)) + "%";
const px = (v) => v < 1 ? nf(4).format(v) : nf(2).format(v);
const tok = (v) => Math.abs(v) >= 100 ? nf(1).format(v) : Math.abs(v) >= 1 ? nf(3).format(v) : nf(5).format(v);
const cls = (v, eps = 1e-9) => v > eps ? "pos" : v < -eps ? "neg" : "neu";
const $ = (id) => document.getElementById(id);
const setTxt = (id, t) => { const e = $(id); if (e) e.textContent = t; };
const setHtml = (id, h) => { const e = $(id); if (e) e.innerHTML = h; };
const setCls = (id, c) => { const e = $(id); if (e) e.className = c; };
const fmtDur = (sec) => {
  if (sec < 3600) return Math.round(sec / 60) + " min";
  if (sec < 86400) return nf(1).format(sec / 3600) + " h";
  return nf(1).format(sec / 86400) + " d";
};
const parseUtc = (s) => s ? new Date(/Z|[+-]\d\d:\d\d$/.test(s) ? s : s + "Z") : null;

// ----------------------------------------------------------------------------
// Modelo: deriva todos los KPIs a partir del documento del worker
// ----------------------------------------------------------------------------
function buildModel(d) {
  const fx = num(d.eur_usd_rate, 1.08);
  const pc = d.portfolio_combined || {};
  const hl = d.hyperliquid_hedge || {};
  const hlPos = hl.positions || {};
  const mli = d.market_link_info || {};
  const initUsd = num(pc.total_initial_usd, num(d.initial_capital_usd, 1080));
  const initEur = num(d.initial_capital_eur, initUsd / fx);

  const pools = POOLS.map((cfg) => {
    const p = cfg.keys.map((k) => d[k]).find(Boolean);
    if (!p) return null;
    const price = num(p.current_price);
    const entry = num(p.entry_price, price);
    const lo = num(p.p_lower, price * 0.97);
    const hi = num(p.p_upper, price * 1.03);
    const tLo = entry - CFG.rebalThresh * (entry - lo);
    const tHi = entry + CFG.rebalThresh * (hi - entry);
    const init = num(p.initial_cap);
    const posVal = num(p.pos_val);
    const fees = num(p.accumulated_fees);
    const comp = num(p.compounded_fees);
    const costs = num(p.total_rebal_costs);
    // Efecto precio "puro": variación del LP sin fees reinvertidas y sin costes descontados del capital
    const pricePure = (posVal - init) - comp + costs;

    const sp = hlPos[cfg.perp] || {};
    const shortTok = num(p.short_tokens, num(sp.size_tokens));
    const mark = num(sp.mark_px, price);
    const shortEntry = num(p.short_entry_price, num(sp.entry_px, entry));
    const shortTxCosts = num(p.short_tx_costs);
    // PnL puro del short (sin restar comisiones de trading, que van a la barra de Costes)
    const shortUnrealized = num(sp.unrealized_pnl_usd, (shortEntry - mark) * shortTok);
    const shortRealized = num(sp.realized_pnl_usd, num(p.realized_short_pnl));
    const shortPnlPure = shortRealized + shortUnrealized;
    const shortPnl = Number.isFinite(Number(sp.pnl_usd)) ? Number(sp.pnl_usd) : (shortPnlPure - shortTxCosts);
    const lpTok = num(p.token_x);
    const lpExpo = lpTok * price;
    const shortExpo = shortTok * mark;

    const days = Math.max(num(p.total_time_sec) / 86400, 1e-6);
    return {
      cfg, raw: p, price, entry, lo, hi, tLo, tHi, init, posVal, fees, comp,
      costs: costs + shortTxCosts, lpCosts: costs, shortTxCosts, pricePure,
      totalVal: num(p.total_val), netProfit: num(p.total_val) - init,
      roi: init > 0 ? ((num(p.total_val) - init) / init) * 100 : 0,
      feeApr: num(p.real_fee_apr), feeAprRaw: init > 0 ? (fees / init) * (365.25 / days) * 100 : 0,
      inRange: !!p.is_in_range, outSec: num(p.out_of_range_sec),
      distLo: num(p.dist_p_lower_pct), distHi: num(p.dist_p_upper_pct),
      distRebal: Math.min(num(p.dist_rebal_lower_pct, 99), num(p.dist_rebal_upper_pct, 99)),
      activity: num(p.activity_ratio_pct, 100), rebals: num(p.total_rebalances),
      shortSyncs: num(p.short_adjustments, num(sp.rebalance_syncs)),
      friction: fees > 0 ? ((costs + shortTxCosts) / fees) * 100 : 0,
      il: num(p.il_amount), ilPct: num(p.il_pct), netVsHodl: num(p.net_vs_hodl),
      tokX: lpTok, tokY: num(p.token_y), symX: cfg.base, symY: p.token_y_symbol || "USDC",
      halfRange: num(p.half_range_pct) * 100, vol24: num(mli[cfg.volKey]),
      shortTok, mark, shortEntry, shortPnl, shortPnlPure, lpExpo, shortExpo, netDelta: lpExpo - shortExpo,
      hedgeRatio: lpTok > 0 ? shortTok / lpTok : null,
      fundingApr: num(sp.funding_apr_pct), funding: num(sp.funding_earned_usd)
    };
  }).filter(Boolean);

  const sum = (f) => pools.reduce((a, p) => a + f(p), 0);
  const days = Math.max(num((d.sol_usdc || {}).total_time_sec, sum((p) => num(p.raw.total_time_sec)) / Math.max(pools.length, 1)) / 86400, 1e-6);

  const fees = sum((p) => p.fees);
  const funding = Number.isFinite(Number(hl.total_funding_usd)) ? Number(hl.total_funding_usd) : sum((p) => p.funding);
  const shortPnl = Number.isFinite(Number(hl.total_short_pnl_usd)) ? Number(hl.total_short_pnl_usd) : sum((p) => p.shortPnl);
  const shortPnlPure = sum((p) => p.shortPnlPure);
  const costs = sum((p) => p.costs);
  const pricePure = sum((p) => p.pricePure);
  const unhedged = num(pc.total_portfolio_usd, sum((p) => p.totalVal));
  const hedged = unhedged + shortPnl + funding;
  const pnl = hedged - initUsd;
  const income = fees + funding;

  const tokens = d.tokens || {};
  const solLpTok = num(tokens.sol_total, num(d.sol_usdc && d.sol_usdc.token_x) + num(d.sol_hype && d.sol_hype.token_x));
  const solLpExpo = num(tokens.sol_usd_val, solLpTok * num(d.sol_price_usd));
  const hypeLpTok = num(tokens.hype_total, num(d.sol_hype && d.sol_hype.token_y) + num(d.hype_usdc && d.hype_usdc.token_x));
  const hypeLpExpo = num(tokens.hype_usd_val, hypeLpTok * num(d.hype_price_usd));

  const perpAssets = [
    {
      sym: "SOL",
      name: "SOL (SOL-PERP)",
      color: "#34D399",
      lpTok: solLpTok,
      lpExpo: solLpExpo,
      shortTok: num(hlPos.SOL && hlPos.SOL.size_tokens, solLpTok),
      shortExpo: num(hlPos.SOL && hlPos.SOL.notional_usd, solLpExpo),
      shortEntry: num(hlPos.SOL && hlPos.SOL.entry_px, num(d.sol_price_usd)),
      mark: num(hlPos.SOL && hlPos.SOL.mark_px, num(d.sol_price_usd)),
      pricePure: -(num(hlPos.SOL && hlPos.SOL.unrealized_pnl_usd, 0)),
      shortPnlPure: num(hlPos.SOL && hlPos.SOL.unrealized_pnl_usd, 0) + num(hlPos.SOL && hlPos.SOL.realized_pnl_usd, 0),
      fundingApr: num(hlPos.SOL && hlPos.SOL.funding_apr_pct, 0),
      funding: num(hlPos.SOL && hlPos.SOL.funding_earned_usd, 0)
    },
    {
      sym: "HYPE",
      name: "HYPE (HYPE-PERP)",
      color: "#38BDF8",
      lpTok: hypeLpTok,
      lpExpo: hypeLpExpo,
      shortTok: num(hlPos.HYPE && hlPos.HYPE.size_tokens, hypeLpTok),
      shortExpo: num(hlPos.HYPE && hlPos.HYPE.notional_usd, hypeLpExpo),
      shortEntry: num(hlPos.HYPE && hlPos.HYPE.entry_px, num(d.hype_price_usd)),
      mark: num(hlPos.HYPE && hlPos.HYPE.mark_px, num(d.hype_price_usd)),
      pricePure: -(num(hlPos.HYPE && hlPos.HYPE.unrealized_pnl_usd, 0)),
      shortPnlPure: num(hlPos.HYPE && hlPos.HYPE.unrealized_pnl_usd, 0) + num(hlPos.HYPE && hlPos.HYPE.realized_pnl_usd, 0),
      fundingApr: num(hlPos.HYPE && hlPos.HYPE.funding_apr_pct, 0),
      funding: num(hlPos.HYPE && hlPos.HYPE.funding_earned_usd, 0)
    }
  ].map((a) => {
    const netDelta = a.lpExpo - a.shortExpo;
    const hedgeRatio = a.lpTok > 0 ? a.shortTok / a.lpTok : 1.0;
    return { ...a, netDelta, hedgeRatio };
  });

  const grossCrypto = solLpExpo + hypeLpExpo > 0 ? (solLpExpo + hypeLpExpo) : sum((p) => p.lpExpo);
  const notional = num(hl.total_short_notional_usd, perpAssets[0].shortExpo + perpAssets[1].shortExpo);
  const collat = num(hl.margin_collateral_usd, 216);
  const hlEquity = collat + shortPnl + funding;
  const lev = num(hl.effective_leverage, hlEquity > 0 ? notional / hlEquity : 3.09);
  const mm = notional > 0 ? ((perpAssets[0].shortExpo * (1 / (2 * 20))) + (perpAssets[1].shortExpo * (1 / (2 * 10)))) / notional : 0.05;
  const liqMove = notional > 0 ? (hlEquity - mm * notional) / (notional * (1 + mm)) * 100 : null;
  const absDelta = Math.abs(perpAssets[0].netDelta) + Math.abs(perpAssets[1].netDelta);
  const netDelta = perpAssets[0].netDelta + perpAssets[1].netDelta;

  const compounded = sum((p) => p.comp);
  const uncompounded = Math.max(fees - compounded, 0);

  return {
    fx, initUsd, initEur, days, pools, perpAssets, fees, funding, shortPnl, shortPnlPure, costs, pricePure, unhedged, hedged, pnl, income,
    priceNet: pricePure + shortPnlPure,
    netApr: (pnl / initUsd) * (365.25 / days) * 100,
    incomeApr: (income / initUsd) * (365.25 / days) * 100,
    feeApr: num(pc.real_fee_apr), fundingAprPortfolio: num(hl.funding_portfolio_apr), weightedFundingApr: num(hl.weighted_funding_apr),
    roiTotalCapital: (pnl / (initUsd + collat)) * 100,
    netDelta, absDelta, grossCrypto,
    notional, collat, hlEquity, lev, liqMove,
    compounded, uncompounded, compoundThreshold: num(hl.auto_compound_threshold_usd, 2.5),
    rebals: sum((p) => p.rebals), shortSyncs: sum((p) => p.shortSyncs), friction: fees > 0 ? (costs / fees) * 100 : 0,
    activity: pools.length ? sum((p) => p.activity) / pools.length : 100,
    inRange: pools.filter((p) => p.inRange).length,
    lastUpdated: parseUtc(d.last_updated),
    startedAt: parseUtc(d.last_updated) ? new Date(parseUtc(d.last_updated).getTime() - days * 86400000) : null,
    hlPos
  };
}

// ----------------------------------------------------------------------------
// Alertas: reglas de seguimiento
// ----------------------------------------------------------------------------
function buildAlerts(M) {
  const A = [];
  const add = (lvl, msg) => A.push({ lvl, msg });
  const ageSec = M.lastUpdated ? (Date.now() - M.lastUpdated.getTime()) / 1000 : Infinity;
  if (ageSec > 900) add("crit", `Datos sin actualizar desde hace ${fmtDur(ageSec)}: revisar el worker de Cloud Run.`);
  else if (ageSec > 180) add("warn", `Último tick del worker hace ${fmtDur(ageSec)}.`);

  M.pools.forEach((p) => {
    const n = p.cfg.label;
    if (!p.inRange) add("crit", `${n} fuera de rango: no genera comisiones.`);
    if (p.outSec > 0) add("warn", `${n} superó el umbral de rebalanceo; se ejecutará en ${fmtDur(Math.max(CFG.rebalConfirmSec - p.outSec, 0))} si no vuelve.`);
    else if (p.inRange && p.distRebal < 1) add("warn", `${n} a ${pct(p.distRebal)} del disparo de rebalanceo.`);
    if (p.fees > 0.05 && p.friction > 50) add("warn", `${n}: los costes consumen el ${pct(p.friction, 0)} de sus comisiones.`);
    if (p.hedgeRatio !== null && p.lpExpo > 5) {
      const dev = Math.abs(p.hedgeRatio - 1) * 100;
      const dir = p.netDelta > 0 ? "infracubierto (largo)" : "sobrecubierto (corto)";
      if (dev > 25) add("crit", `Cobertura ${p.cfg.base} ${dir}: ratio ${pct(p.hedgeRatio * 100, 0)}, delta ${sUsd(p.netDelta, 0)}. Ajustar short.`);
      else if (dev > 10) add("warn", `Cobertura ${p.cfg.base} ${dir}: ratio ${pct(p.hedgeRatio * 100, 0)}, delta ${sUsd(p.netDelta, 0)}.`);
    }
  });

  if (M.lev !== null && M.lev > 3.5) add("warn", `Apalancamiento en Hyperliquid elevado: ${nf(2).format(M.lev)}x.`);
  if (M.liqMove !== null && M.liqMove < 20) add("crit", `Margen a liquidación estimado solo ${pct(M.liqMove, 1)}.`);
  if (M.days >= 1 && M.incomeApr < CFG.targetAprMin) add("info", `APR de ingresos ${pct(M.incomeApr, 1)} por debajo del objetivo mínimo (${CFG.targetAprMin}%).`);
  if (M.fees < Math.abs(M.pools.reduce((a, p) => a + Math.min(p.il, 0), 0))) add("info", "Las comisiones aún no cubren la pérdida impermanente acumulada.");
  return A;
}

// ----------------------------------------------------------------------------
// Render
// ----------------------------------------------------------------------------
function render() {
  if (!state) return;
  const M = buildModel(state);
  const fx = M.fx;

  // Cabecera
  setTxt("hdrCapital", eur(M.initEur, 0));
  setTxt("hdrTestDay", `Día ${nf(1).format(M.days)} / ${CFG.testDays}`);
  $("hdrTestBar").style.width = Math.min(100, (M.days / CFG.testDays) * 100) + "%";
  renderFeed(M);

  // KPI 1: Patrimonio
  setTxt("kEquity", eur(M.hedged / fx));
  setTxt("kPnl", sEur(M.pnl / fx)); setCls("kPnl", "num font-semibold " + cls(M.pnl));
  setTxt("kPnlPct", sPct((M.pnl / M.initUsd) * 100)); setCls("kPnlPct", "num text-xs " + cls(M.pnl));
  setTxt("kEquityUsd", `${usd(M.hedged)} · solo pools ${eur(M.unhedged / fx)}`);

  // KPI 2: Rentabilidad neta anualizada vs objetivo
  setTxt("kNetApr", sPct(M.netApr, 1));
  const aprCls = M.netApr >= CFG.targetAprMin ? "pos" : M.netApr >= 0 ? "warn" : "neg";
  setCls("kNetApr", "num text-3xl font-bold mt-2 " + aprCls);
  setTxt("kTargetLbl", `${CFG.targetAprMin}–${CFG.targetAprMax}%`);
  const scaleMax = Math.max(CFG.targetAprMax * 1.5, M.netApr * 1.1);
  $("kNetAprBar").style.width = Math.max(0, Math.min(100, (M.netApr / scaleMax) * 100)) + "%";
  $("kNetAprBar").className = M.netApr >= CFG.targetAprMin ? "bg-emerald-400" : M.netApr >= 0 ? "bg-amber-400" : "bg-rose-400";
  const zone = $("kTargetZone");
  zone.style.left = (CFG.targetAprMin / scaleMax) * 100 + "%";
  zone.style.width = ((CFG.targetAprMax - CFG.targetAprMin) / scaleMax) * 100 + "%";
  setHtml("kNetAprNote", M.days < 7
    ? `<span class="warn">Muestra de ${nf(1).format(M.days)} días: alta varianza.</span>`
    : `<span class="muted">Sobre ${nf(1).format(M.days)} días de operación.</span>`);

  // KPI 3: Ingresos pasivos
  setTxt("kIncome", sEur(M.income / fx, 2));
  setTxt("kIncomeSplit", `DLMM ${sEur(M.fees / fx)} · Funding ${sEur(M.funding / fx)}`);
  setTxt("kIncomeApr", pct(M.incomeApr, 1));
  setCls("kIncomeApr", "num font-semibold " + (M.incomeApr >= CFG.targetAprMin ? "pos" : "warn"));
  setTxt("kIncome30", sEur((M.income / M.days) * CFG.testDays / fx));

  // KPI 4: Efecto precio neto / cobertura
  setTxt("kPriceNet", sEur(M.priceNet / fx)); setCls("kPriceNet", "num text-3xl font-bold mt-2 " + cls(M.priceNet));
  setTxt("kPriceSplit", `Pools ${sEur(M.pricePure / fx)} · Shorts ${sEur(M.shortPnlPure / fx)}`);
  // Desviación bruta: suma de |delta| por activo (los activos no se compensan entre sí)
  const deltaPct = M.grossCrypto > 0 ? (M.absDelta / M.grossCrypto) * 100 : 0;
  setTxt("kDelta", `${usd(M.absDelta, 0)} (${pct(deltaPct, 0)})`);
  setCls("kDelta", "num font-semibold " + (Math.abs(deltaPct) > 25 ? "neg" : Math.abs(deltaPct) > 10 ? "warn" : "pos"));
  const eff = Math.abs(M.pricePure) > 0.01 ? (-M.shortPnlPure / M.pricePure) * 100 : null;
  setTxt("kHedgeEff", eff === null ? "—" : pct(eff, 0));

  // Alertas y salud
  const alerts = buildAlerts(M);
  const crit = alerts.filter((a) => a.lvl === "crit").length, warn = alerts.filter((a) => a.lvl === "warn").length;
  const sum = $("alertSummary");
  if (crit) { sum.className = "chip chip-crit"; sum.textContent = `${crit} crítica${crit > 1 ? "s" : ""} · ${warn} aviso${warn !== 1 ? "s" : ""}`; }
  else if (warn) { sum.className = "chip chip-warn"; sum.textContent = `${warn} aviso${warn > 1 ? "s" : ""}`; }
  else { sum.className = "chip chip-ok"; sum.textContent = "Todo en orden"; }
  const icon = { crit: "●", warn: "▲", info: "i" };
  setHtml("alertList", alerts.length ? alerts.map((a) =>
    `<div class="flex gap-2 items-start rounded-lg px-3 py-2 bg-white/[0.03]"><span class="chip chip-${a.lvl} !px-1.5">${icon[a.lvl]}</span><span class="text-slate-200">${a.msg}</span></div>`
  ).join("") : `<div class="text-sm muted">Sin incidencias: pools en rango, cobertura equilibrada y datos al día.</div>`);

  setTxt("hInRange", `${M.inRange}/${M.pools.length}`); setCls("hInRange", "num text-lg font-semibold mt-1 " + (M.inRange === M.pools.length ? "pos" : "neg"));
  setTxt("hTimeInRange", pct(M.activity, 1));
  setTxt("hRebal", `${M.rebals} reb · ${M.shortSyncs} sync · ${eur(M.costs / fx)}`);
  setTxt("hFriction", pct(M.friction, 1)); setCls("hFriction", "num text-lg font-semibold mt-1 " + (M.friction > 50 ? "neg" : M.friction > 20 ? "warn" : "pos"));
  setTxt("hLev", M.lev === null ? "—" : nf(2).format(M.lev) + "x"); setCls("hLev", "num text-lg font-semibold mt-1 " + (M.lev > 3.5 ? "warn" : "neu"));
  setTxt("hLiq", M.liqMove === null ? "—" : "+" + pct(M.liqMove, 1)); setCls("hLiq", "num text-lg font-semibold mt-1 " + (M.liqMove < 20 ? "neg" : M.liqMove < 30 ? "warn" : "pos"));

  // Pools, cobertura y gráficos
  renderPools(M);
  renderHedge(M);
  renderBridge(M);
  renderHistory(M);
}

function renderFeed(M) {
  const chip = $("feedChip");
  const ageSec = M && M.lastUpdated ? Math.max(0, (Date.now() - M.lastUpdated.getTime()) / 1000) : null;
  if (ageSec === null) { chip.className = "chip chip-info"; setTxt("feedText", "Conectando…"); return; }
  const lbl = ageSec < 60 ? `${Math.round(ageSec)} s` : fmtDur(ageSec);
  if (ageSec <= 180) { chip.className = "chip chip-ok"; setTxt("feedText", `En vivo · hace ${lbl}`); }
  else if (ageSec <= 900) { chip.className = "chip chip-warn"; setTxt("feedText", `Retraso · hace ${lbl}`); }
  else { chip.className = "chip chip-crit"; setTxt("feedText", `Sin datos · hace ${lbl}`); }
}

function rangeBar(p) {
  // Escala visual: desde el disparo inferior al superior (con margen) para ver rango y umbral de rebalanceo
  const span = p.tHi - p.tLo;
  const min = p.tLo - span * 0.08, max = p.tHi + span * 0.08;
  const pos = (v) => Math.max(0, Math.min(100, ((v - min) / (max - min)) * 100));
  const markerCol = p.inRange ? (p.distRebal < 1 ? "#FBBF24" : "#FFFFFF") : "#FB7185";
  return `
    <div class="relative h-7 mt-1">
      <div class="absolute top-3 left-0 right-0 h-1 rounded bg-white/5"></div>
      <div class="absolute top-2.5 h-2 rounded" style="left:${pos(p.lo)}%;width:${pos(p.hi) - pos(p.lo)}%;background:${p.cfg.color}33;border:1px solid ${p.cfg.color}88"></div>
      <div class="absolute top-1.5 h-4 w-px bg-rose-400/70" style="left:${pos(p.tLo)}%" title="Disparo rebalanceo inferior"></div>
      <div class="absolute top-1.5 h-4 w-px bg-rose-400/70" style="left:${pos(p.tHi)}%" title="Disparo rebalanceo superior"></div>
      <div class="absolute top-1.5 h-4 w-px bg-slate-400/60" style="left:${pos(p.entry)}%" title="Precio de entrada"></div>
      <div class="absolute top-0.5 w-3 h-3 -ml-1.5 rounded-full border-2 border-ink-900" style="left:${pos(p.price)}%;background:${markerCol}" title="Precio actual"></div>
    </div>
    <div class="flex justify-between text-[11px] num muted">
      <span>${px(p.lo)}</span><span class="text-slate-200">${px(p.price)}</span><span>${px(p.hi)}</span>
    </div>`;
}

function renderPools(M) {
  const fx = M.fx;
  const progress = Math.min(100, (M.uncompounded / M.compoundThreshold) * 100);
  setHtml("compoundTxt", `${usd(M.uncompounded)} / ${usd(M.compoundThreshold)} (${pct(progress, 0)}) · reinvertido ${usd(M.compounded)}`);

  setHtml("poolsGrid", M.pools.map((p) => {
    const status = !p.inRange ? `<span class="chip chip-crit">Fuera de rango</span>`
      : p.outSec > 0 ? `<span class="chip chip-warn">Confirmando rebalanceo</span>`
      : p.distRebal < 1 ? `<span class="chip chip-warn">Cerca del borde</span>`
      : `<span class="chip chip-ok">En rango</span>`;
    const aprCls = p.feeApr >= CFG.targetAprMin ? "pos" : p.feeApr >= CFG.targetAprMin / 2 ? "warn" : "neg";
    const row = (k, v, c = "text-slate-200") => `<div class="flex justify-between"><span class="muted">${k}</span><span class="num ${c}">${v}</span></div>`;
    return `
    <div class="card p-4" style="border-top:3px solid ${p.cfg.color}">
      <div class="flex items-start justify-between">
        <div>
          <div class="font-bold text-white">${p.cfg.label}</div>
          <div class="text-[11px] muted">${p.cfg.role} · ${pct((p.init / M.initUsd) * 100, 0)} · rango ±${nf(1).format(p.halfRange)}%</div>
        </div>
        ${status}
      </div>

      <div class="grid grid-cols-3 gap-2 mt-4">
        <div><div class="kpi-label">Valor</div><div class="num font-semibold text-white mt-0.5">${eur(p.totalVal / fx)}</div><div class="num text-[11px] ${cls(p.netProfit)}">${sPct(p.roi)}</div></div>
        <div><div class="kpi-label">Fees</div><div class="num font-semibold pos mt-0.5">${sEur(p.fees / fx, 3)}</div><div class="num text-[11px] muted">${usd(p.fees, 3)}</div></div>
        <div><div class="kpi-label">APR fees</div><div class="num font-semibold mt-0.5 ${aprCls}">${pct(p.feeApr, 1)}</div><div class="num text-[11px] muted">obj. ${CFG.targetAprMin}%</div></div>
      </div>

      <div class="mt-4">
        <div class="flex justify-between text-[11px]"><span class="kpi-label">Rango activo</span><span class="num muted">rebalanceo a ${pct(p.distRebal)}</span></div>
        ${rangeBar(p)}
      </div>

      <div class="mt-4 space-y-1.5 text-xs">
        ${row("Tiempo en rango", pct(p.activity, 1), p.activity >= 90 ? "pos" : "warn")}
        ${row("Distancia a Pmin / Pmax", `${pct(p.distLo)} / ${pct(p.distHi)}`)}
        ${row("Pérdida impermanente", `${sUsd(p.il)} (${sPct(p.ilPct)})`, cls(p.il))}
        ${row("Neto vs HODL 50/50", sUsd(p.netVsHodl), cls(p.netVsHodl))}
        ${row("Rebalanceos · sync short", `${p.rebals} · ${p.shortSyncs} (${usd(p.costs, 3)})`)}
        ${row("Costes / fees", pct(p.friction, 1), p.friction > 50 ? "neg" : p.friction > 20 ? "warn" : "pos")}
        ${row("Inventario", `${tok(p.tokX)} ${p.symX} + ${nf(2).format(p.tokY)} ${p.symY}`)}
        ${row("Volumen 24h pool", p.vol24 ? usd(p.vol24, 0) : "—")}
      </div>
    </div>`;
  }).join(""));
}

function renderHedge(M) {
  const ratioCell = (r) => {
    if (r === null) return `<span class="muted">—</span>`;
    const dev = Math.abs(r - 1) * 100;
    const c = dev > 25 ? "chip-crit" : dev > 10 ? "chip-warn" : "chip-ok";
    return `<span class="chip ${c}">${pct(r * 100, 0)}</span>`;
  };
  setHtml("hedgeBody", (M.perpAssets || []).map((p) => `
    <tr>
      <td class="font-sans"><span class="inline-block w-2 h-2 rounded-full mr-2" style="background:${p.color}"></span><span class="font-semibold text-white">${p.name}</span></td>
      <td>${tok(p.lpTok)}<div class="text-[11px] muted">${usd(p.lpExpo, 0)}</div></td>
      <td>−${tok(p.shortTok)}<div class="text-[11px] muted">${usd(p.shortExpo, 0)} · ent. ${px(p.shortEntry)}</div></td>
      <td>${ratioCell(p.hedgeRatio)}</td>
      <td class="${Math.abs(p.netDelta) > 0.25 * p.lpExpo ? "neg" : Math.abs(p.netDelta) > 0.1 * p.lpExpo ? "warn" : "pos"}">${sUsd(p.netDelta, 0)}</td>
      <td class="${cls(p.pricePure)}">${sUsd(p.pricePure)}</td>
      <td class="${cls(p.shortPnlPure)}">${sUsd(p.shortPnlPure)}</td>
      <td class="${cls(p.pricePure + p.shortPnlPure)} font-semibold">${sUsd(p.pricePure + p.shortPnlPure)}</td>
      <td class="${cls(p.fundingApr)}">${sPct(p.fundingApr)}</td>
      <td class="${cls(p.funding)}">${sUsd(p.funding, 3)}</td>
    </tr>`).join(""));
  setHtml("hedgeFoot", `
    <tr>
      <td class="font-sans text-slate-300">Total</td>
      <td>${usd(M.grossCrypto, 0)}</td>
      <td>${usd(M.notional, 0)}</td>
      <td>${M.grossCrypto > 0 ? pct((M.notional / M.grossCrypto) * 100, 0) : "—"}</td>
      <td class="${cls(M.netDelta)}">${sUsd(M.netDelta, 0)}</td>
      <td class="${cls(M.pricePure)}">${sUsd(M.pricePure)}</td>
      <td class="${cls(M.shortPnlPure)}">${sUsd(M.shortPnlPure)}</td>
      <td class="${cls(M.priceNet)}">${sUsd(M.priceNet)}</td>
      <td>${sPct(M.weightedFundingApr)}</td>
      <td class="${cls(M.funding)}">${sUsd(M.funding, 3)}</td>
    </tr>`);

  setTxt("mCollat", usd(M.collat));
  setTxt("mEquity", `${usd(M.hlEquity)} (${sUsd(M.hlEquity - M.collat)})`);
  setTxt("mNotional", `${usd(M.notional, 0)} · ${M.lev ? nf(2).format(M.lev) + "x" : "—"}`);
  setTxt("mFundApr", `${sPct(M.weightedFundingApr)} → ${sPct(M.fundingAprPortfolio)} cartera`);
  setTxt("mRoiTotal", sPct(M.roiTotalCapital, 3)); setCls("mRoiTotal", "num mt-1 " + cls(M.roiTotalCapital));
}

// ----------------------------------------------------------------------------
// Gráficos
// ----------------------------------------------------------------------------
Chart.defaults.color = "#8B98AD";
Chart.defaults.font.family = "Inter, system-ui, sans-serif";
Chart.defaults.font.size = 11;
const gridColor = "rgba(255,255,255,0.05)";

function renderBridge(M) {
  const fx = M.fx;
  const steps = [
    ["Fees DLMM", M.fees / fx],
    ["Funding", M.funding / fx],
    ["Precio pools", M.pricePure / fx],
    ["Shorts", M.shortPnlPure / fx],
    ["Costes", -M.costs / fx]
  ];
  const labels = [], data = [], colors = [];
  let acc = 0;
  steps.forEach(([l, v]) => {
    labels.push(l); data.push([acc, acc + v]); colors.push(v >= 0 ? "#34D399" : "#FB7185"); acc += v;
  });
  labels.push("PnL neto"); data.push([0, acc]); colors.push(acc >= 0 ? "#38BDF8" : "#F472B6");

  if (!bridgeChart) {
    bridgeChart = new Chart($("bridgeChart"), {
      type: "bar",
      data: { labels, datasets: [{ data, backgroundColor: colors, borderRadius: 4, borderSkipped: false }] },
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 250 },
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => { const [a, b] = c.raw; return sEur(c.dataIndex === labels.length - 1 ? b : b - a); } } } },
        scales: { x: { grid: { display: false } }, y: { grid: { color: gridColor }, ticks: { callback: (v) => nf(1).format(v) + " €" } } }
      }
    });
  } else {
    bridgeChart.data.labels = labels;
    bridgeChart.data.datasets[0].data = data;
    bridgeChart.data.datasets[0].backgroundColor = colors;
    bridgeChart.update("none");
  }
}

function historySeries(M) {
  // Reconstruye el patrimonio cubierto de cada snapshot: los shorts son de tamaño fijo (modo manual),
  // así que su PnL histórico se obtiene con el precio del snapshot. El funding se prorratea en el tiempo.
  const start = M.startedAt ? M.startedAt.getTime() : null;
  if (!start) return [];
  const nowH = M.days * 24;
  const shortDefs = M.pools.map((p) => ({ perp: p.cfg.perp, size: p.shortTok, entry: p.shortEntry }));
  const priceOf = (s, perp) => perp === "SOL" ? num(s.sol_price_usd) : (perp === "HYPE" ? num(s.hype_price_usd) : num(s.btc_price_usd, num(s.sol_price_usd)));

  const pts = snapshots.map((s) => {
    const t = parseUtc(s.timestamp);
    if (!t) return null;
    const h = (t.getTime() - start) / 3600000;
    if (h < -0.1 || h > nowH + 0.1) return null;
    const shortPnl = shortDefs.reduce((a, d) => { const pr = priceOf(s, d.perp); return a + (pr > 0 ? (d.entry - pr) * d.size : 0); }, 0);
    const funding = nowH > 0 ? M.funding * Math.max(h, 0) / nowH : 0;
    const lpUsd = num(s.total_portfolio_usd, num(s.total_portfolio_eur) * M.fx);
    return {
      h: Math.max(h, 0),
      lpEur: lpUsd / M.fx,
      hedgedEur: (lpUsd + shortPnl + funding) / M.fx,
      incomeEur: (num(s.total_fees_usd, num(s.total_fees_eur) * M.fx) + funding) / M.fx
    };
  }).filter(Boolean);
  pts.unshift({ h: 0, lpEur: M.initEur, hedgedEur: M.initEur, incomeEur: 0 });
  pts.push({ h: nowH, lpEur: M.unhedged / M.fx, hedgedEur: M.hedged / M.fx, incomeEur: M.income / M.fx });
  return pts.sort((a, b) => a.h - b.h);
}

function renderHistory(M) {
  const pts = historySeries(M);
  if (!pts.length) return;
  const start = M.startedAt.getTime();
  const maxH = Math.max(pts[pts.length - 1].h, 1);
  const tgt = (apr) => [{ x: 0, y: activeTab === "equity" ? M.initEur : 0 }, { x: maxH, y: (activeTab === "equity" ? M.initEur : 0) + M.initEur * (apr / 100) * (maxH / 24 / 365.25) }];

  let datasets;
  if (activeTab === "equity") {
    datasets = [
      { label: "Patrimonio neto (cubierto)", data: pts.map((p) => ({ x: p.h, y: p.hedgedEur })), borderColor: "#34D399", backgroundColor: "rgba(52,211,153,0.08)", fill: true, tension: 0.25, pointRadius: 0, borderWidth: 2 },
      { label: "Solo pools (sin cobertura)", data: pts.map((p) => ({ x: p.h, y: p.lpEur })), borderColor: "#94A3B8", borderDash: [4, 4], tension: 0.25, pointRadius: 0, borderWidth: 1.5 },
      { label: `Senda objetivo ${CFG.targetAprMin}% APR`, data: tgt(CFG.targetAprMin), borderColor: "#FBBF24", borderDash: [2, 4], pointRadius: 0, borderWidth: 1.5 }
    ];
  } else {
    datasets = [
      { label: "Ingresos acumulados (fees + funding)", data: pts.map((p) => ({ x: p.h, y: p.incomeEur })), borderColor: "#38BDF8", backgroundColor: "rgba(56,189,248,0.1)", fill: true, tension: 0.25, pointRadius: 0, borderWidth: 2 },
      { label: `Objetivo ${CFG.targetAprMin}% APR`, data: tgt(CFG.targetAprMin), borderColor: "#FBBF24", borderDash: [4, 4], pointRadius: 0, borderWidth: 1.5 },
      { label: `Objetivo ${CFG.targetAprMax}% APR`, data: tgt(CFG.targetAprMax), borderColor: "#34D399", borderDash: [2, 4], pointRadius: 0, borderWidth: 1.5 }
    ];
  }

  const fmtX = (h) => new Date(start + h * 3600000).toLocaleString("es-ES", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  const yFmt = (v) => activeTab === "equity" ? nf(0).format(v) + " €" : nf(2).format(v) + " €";

  if (!historyChart) {
    historyChart = new Chart($("historyChart"), {
      type: "line",
      data: { datasets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 250 }, parsing: false,
        interaction: { mode: "nearest", axis: "x", intersect: false },
        plugins: {
          legend: { labels: { boxWidth: 12, usePointStyle: true } },
          tooltip: { callbacks: { title: (items) => fmtX(items[0].parsed.x), label: (c) => `${c.dataset.label}: ${nf(activeTab === "equity" ? 2 : 3).format(c.parsed.y)} €` } }
        },
        scales: {
          x: { type: "linear", min: 0, grid: { color: gridColor }, ticks: { maxTicksLimit: 8, callback: (v) => fmtX(v) } },
          y: { grid: { color: gridColor }, ticks: { callback: yFmt } }
        }
      }
    });
  } else {
    historyChart.data.datasets = datasets;
    historyChart.options.scales.x.max = maxH;
    historyChart.options.scales.y.ticks.callback = yFmt;
    historyChart.update("none");
  }
  setTxt("historyNote", `${pts.length - 2} snapshots desde ${fmtX(0)} · el patrimonio cubierto se reconstruye con el precio de cada snapshot (shorts de tamaño fijo) y funding prorrateado.`);
}

document.querySelectorAll("#chartTabs .tab").forEach((b) => b.addEventListener("click", () => {
  activeTab = b.dataset.tab;
  document.querySelectorAll("#chartTabs .tab").forEach((x) => x.className = "tab px-2.5 py-1 rounded-md " + (x === b ? "bg-white/10 text-white" : "text-slate-400 hover:text-white"));
  if (historyChart) { historyChart.destroy(); historyChart = null; }
  render();
}));

// ----------------------------------------------------------------------------
// Datos: Firestore (listener + REST de respaldo) y snapshots históricos
// ----------------------------------------------------------------------------
function parseFsValue(v) {
  if (!v) return null;
  if (v.doubleValue !== undefined) return Number(v.doubleValue);
  if (v.integerValue !== undefined) return Number(v.integerValue);
  if (v.stringValue !== undefined) return v.stringValue;
  if (v.booleanValue !== undefined) return v.booleanValue;
  if (v.timestampValue !== undefined) return v.timestampValue;
  if (v.mapValue !== undefined) { const o = {}; const f = v.mapValue.fields || {}; for (const k in f) o[k] = parseFsValue(f[k]); return o; }
  if (v.arrayValue !== undefined) return (v.arrayValue.values || []).map(parseFsValue);
  return null;
}
const parseFsDoc = (doc) => { const o = {}; for (const k in (doc.fields || {})) o[k] = parseFsValue(doc.fields[k]); return o; };

function onState(d) {
  if (!d) return;
  const prevStart = state ? buildModel(state).startedAt : null;
  state = d;
  lastFetchMs = Date.now();
  render();
  const newStart = buildModel(state).startedAt;
  // Recarga el histórico si cambia el ciclo o si aún no se ha cargado
  if (!snapshots.length || (prevStart && newStart && Math.abs(newStart - prevStart) > 3600000)) loadSnapshots();
}

function pollState() {
  return fetch(`${CFG.restBase}/meteora_bot/current_state`, { cache: "no-store" })
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((doc) => onState(parseFsDoc(doc)))
    .catch((e) => console.warn("[!] REST current_state:", e));
}

function loadSnapshots() {
  if (!state) return;
  const M = buildModel(state);
  if (!M.startedAt) return;
  const since = new Date(M.startedAt.getTime() - 5 * 60000).toISOString().replace("Z", "");
  const body = {
    structuredQuery: {
      from: [{ collectionId: "snapshots" }],
      where: { fieldFilter: { field: { fieldPath: "timestamp" }, op: "GREATER_THAN_OR_EQUAL", value: { stringValue: since } } },
      orderBy: [{ field: { fieldPath: "timestamp" } }],
      limit: 2000
    }
  };
  fetch(`${CFG.restBase}/meteora_bot/history:runQuery`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
    .then((r) => r.json())
    .then((rows) => {
      snapshots = (Array.isArray(rows) ? rows : []).filter((r) => r.document).map((r) => parseFsDoc(r.document));
      render();
    })
    .catch((e) => console.warn("[!] Snapshots:", e));
}

window.forceRefresh = function () {
  setTxt("feedText", "Actualizando…");
  wakeWorker();
  pollState().then(loadSnapshots);
};

// El worker de Cloud Run ejecuta un tick bajo demanda al recibir una petición HTTP (modo free-tier).
function wakeWorker() {
  fetch(CFG.workerUrl, { mode: "no-cors", cache: "no-store" }).catch(() => {});
}

function start() {
  try {
    if (typeof firebase !== "undefined") {
      firebase.initializeApp(firebaseConfig);
      firebase.firestore().collection("meteora_bot").doc("current_state")
        .onSnapshot((doc) => { if (doc.exists) onState(doc.data()); }, (err) => console.warn("[!] Listener Firestore:", err));
    }
  } catch (e) { console.warn("[!] Firebase SDK:", e); }

  wakeWorker();
  pollState();
  setInterval(wakeWorker, 20000);
  setInterval(pollState, 15000);
  setInterval(loadSnapshots, 10 * 60000);
  setInterval(() => { if (state) renderFeed(buildModel(state)); }, 1000);
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
else start();

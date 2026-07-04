// Widok "Przegląd ogólny": Core Web Vitals, dwa boxy podsumowania (Serwis/Blog),
// trend, regresje i rekomendacje. Renderuje do DOM na podstawie store.DATA.
import { store } from "./store.js";
import { THRESHOLDS, META, PILL, LEVER, LVL, esc, fmt, rate, convRisk } from "./format.js";
import { lineChart } from "./charts.js";
import { $ } from "./dom.js";

/* ---------- Kondycja serwisu (nagłówek + opis + kafle) ---------- */
function renderHealth() {
  const s = store.DATA.summary[store.state.strat];
  $("healthHeadline").textContent = s.health.headline;
  $("healthDesc").textContent = s.health.desc;
  $("hGood").textContent = s.counts.good;
  $("hWarn").textContent = s.counts["needs-improvement"];
  $("hPoor").textContent = s.counts.poor;
}

/* ---------- Core Web Vitals ---------- */
function renderCWV() {
  const s = store.DATA.summary[store.state.strat], box = $("cwv");
  box.innerHTML = "";
  ["LCP", "CLS", "TTFB", "INP"].forEach(m => {
    const p50 = s.medians[m], p90 = (s.p90 || {})[m], t = THRESHOLDS[m], meta = META[m];
    const c50 = PILL[rate(m, p50)], c90 = PILL[rate(m, p90)];
    // Strefy paska (dobra/uwaga/słaba) skalowane do progów; marker = pozycja p50.
    const scale = t.poor / 0.8;
    const zGood = Math.min(100, t.good / scale * 100);
    const zWarn = Math.min(100 - zGood, (t.poor - t.good) / scale * 100);
    const zPoor = Math.max(0, 100 - zGood - zWarn);
    const marker = p50 == null ? 0 : Math.max(0, Math.min(100, p50 / scale * 100));
    box.innerHTML += `<div class="cwvcol">
      <div class="cwv-top"><span class="cwv-key">${m}</span>
        <span class="cwv-dot" style="background:${c50.c}"></span>
        <span class="cwv-stat" style="color:${c50.c}">${c50.label}</span></div>
      <div class="cwv-title">${meta.human}</div>
      <div class="cwv-p50">${fmt(m, p50)}</div>
      <div class="cwv-cap">P50 · TYPOWA</div>
      <div class="zone"><div class="bar">
        <div style="width:${zGood}%;background:#cfefd8"></div>
        <div style="width:${zWarn}%;background:#ffe4c2"></div>
        <div style="width:${zPoor}%;background:#f9d2d2"></div></div>
        <div class="marker" style="left:${marker}%"></div></div>
      <div class="cwv-p90"><span class="l">P90 · OGON</span>
        <span class="v">${fmt(m, p90)}<span class="cwv-dot" style="background:${c90.c}"></span></span></div>
      <div class="cwv-target">Cel ${fmt(m, t.good)} · Słaby > ${fmt(m, t.poor)}</div>
      <p class="cwv-desc">${meta.desc}</p></div>`;
  });
}

/* ---------- Podsumowanie (dwa boxy: Serwis / Blog) ---------- */
function drawBar(el, c) {
  const total = Math.max(1, c.good + c["needs-improvement"] + c.poor);
  const seg = (n, col) => n > 0 ? `<div style="width:${n / total * 100}%;background:${col}"></div>` : "";
  el.innerHTML = seg(c.good, "var(--good)") + seg(c["needs-improvement"], "var(--warn)") + seg(c.poor, "var(--poor)");
}
function drawCounts(el, c) {
  el.innerHTML =
    `<span><span class="dot dot-good"></span>${c.good} w normie</span>` +
    `<span><span class="dot dot-warn"></span>${c["needs-improvement"]} do poprawy</span>` +
    `<span><span class="dot dot-poor"></span>${c.poor} pilne</span>`;
}
function renderSummary() {
  const s = store.DATA.summary[store.state.strat];
  const seoMap = { "niski": "Niski", "średni": "Średni", "wysoki": "Wysoki" };
  // Werdykt dla zarządu - jedno zdanie wiodące (executive summary).
  $("verdict").textContent = s.verdict;

  // Box 1: Lejek konwersji (strony tier 1 - na przychód)
  const conv = s.funnel.conversion;
  $("lejekTotal").textContent = conv.total;
  drawBar($("lejekBar"), conv.counts);
  drawCounts($("lejekCounts"), conv.counts);
  const cr = convRisk(conv.counts);
  const cv = $("srvConv"); cv.textContent = cr.t; cv.style.color = cr.col;
  $("srvSeo").textContent = seoMap[s.seo_impact] || s.seo_impact;

  // Box 2: Kampanie i promocje (landingi płatnego ruchu)
  const camp = (s.funnel.by_group || {}).campaign || { counts: { good: 0, "needs-improvement": 0, poor: 0 }, total: 0, ads: 0 };
  $("campTotal").textContent = camp.total;
  drawBar($("campBar"), camp.counts);
  drawCounts($("campCounts"), camp.counts);
  $("campAds").textContent = camp.ads + (camp.ads === 1 ? " strona" : (camp.ads >= 2 && camp.ads <= 4 ? " strony" : " stron"));
  const cpc = convRisk(camp.counts);
  const cr2 = $("campRisk"); cr2.textContent = cpc.t; cr2.style.color = cpc.col;

  // Box 3: Blog (SEO)
  const bc = s.by_category.blog;
  $("blogTotal").textContent = bc.total;
  drawBar($("blogBar"), bc.counts);
  drawCounts($("blogCounts"), bc.counts);
  const ml = bc.median_lcp;
  $("blogLcp").innerHTML = ml == null ? "–"
    : `${fmt("LCP", ml)} <span style="font-size:11px;color:${PILL[rate("LCP", ml)].c};font-weight:700">· ${PILL[rate("LCP", ml)].label}</span>`;
  const crit = $("blogCrit");
  crit.textContent = bc.counts.poor ? bc.counts.poor : "Brak";
  crit.style.color = bc.counts.poor ? "var(--poor)" : "var(--good)";
}

/* ---------- Trend + regresje ---------- */
export function renderTrend() {
  const st = store.state;
  $("trendLegLbl").textContent = st.metric + " (mediana serwisu)";
  const m = st.metric, ctx = $("trendChart");
  let runs = store.HIST.runs.slice();
  if (st.range > 0) runs = runs.slice(-Math.max(2, Math.ceil(st.range / 3)));
  const labels = runs.map(r => r.timestamp.slice(5, 10));
  const note = $("trendNote");
  if (note) note.textContent = store.HIST.runs.length < 2
    ? "Wykres zapełnia się od pierwszego pomiaru - kolejne punkty dojdą przy następnych przebiegach (raz dziennie)." : "";
  const series = runs.map(run => {
    const pts = (run.series || []).filter(x => x.strategy === st.strat);
    const vals = pts.map(x => x[m]).filter(v => v != null);
    if (!vals.length) return null;
    vals.sort((a, b) => a - b);
    return vals[Math.floor(vals.length / 2)];
  });
  if (store.trendChart) store.trendChart.destroy();
  store.trendChart = lineChart(ctx, { labels, data: series, metric: m });
}
function renderReg() {
  const regs = (store.DATA.regressions || []).filter(r => r.strategy === store.state.strat);
  const b = $("regBody");
  if (!regs.length) {
    b.innerHTML = `<div style="display:flex;align-items:center;gap:10px;margin-top:14px">
      <span style="width:9px;height:9px;border-radius:50%;background:var(--good)"></span>
      <span style="font-size:17px;font-weight:700;color:var(--good);letter-spacing:-.01em">Brak pogorszeń</span></div>
      <p style="margin:8px 0 0;font-size:12.5px;color:var(--muted);font-weight:500;line-height:1.5">Wydajność stabilna względem poprzednich przebiegów.</p>`;
    return;
  }
  const top = regs[0];
  b.innerHTML = `<div style="display:flex;align-items:center;gap:10px;margin-top:14px">
    <span style="width:9px;height:9px;border-radius:50%;background:var(--poor)"></span>
    <span style="font-size:17px;font-weight:700;color:var(--poor)">${regs.length} pogorszeń</span></div>
    <p style="margin:8px 0 0;font-size:12.5px;color:var(--muted);font-weight:500">Największe: <b>${esc(top.label)}</b> — ${top.metric} ▲${top.delta_pct}%.</p>`;
}

/* ---------- Rekomendacje ---------- */
function renderRecs() {
  const box = $("recs"); box.innerHTML = "";
  (store.DATA.recommendations || []).forEach(r => {
    const lv = LVL[r.priority] || LVL["Niski"];
    box.innerHTML += `<div class="rec">
      <span class="lvl" style="background:${lv.bg};color:${lv.fg}">${esc(r.priority)}</span>
      <div class="body"><div class="title">${esc(r.action)}</div>
        <div class="sub">${esc(r.label)} · metryka ${esc(r.metric)}</div>
        <div class="meta"><span class="lever">${LEVER[r.metric] || "UX"}</span>
          <span class="desc">${esc(r.business_impact)}</span></div></div>
      <span class="ms">~${esc(r.savings_ms)} ms</span></div>`;
  });
}
export function copyRecs() {
  const md = (store.DATA.recommendations || []).map((r, i) =>
    `${i + 1}. [${r.priority}] ${r.action} - ${r.label} (${r.metric}, ~${r.savings_ms} ms)\n   Wpływ: ${r.business_impact}`).join("\n");
  navigator.clipboard.writeText("# Rekomendacje wydajności inpostpay.pl\n\n" + md).then(() => {
    const b = $("copyRecs"); b.textContent = "✓ Skopiowano";
    setTimeout(() => b.textContent = "Kopiuj listę dla deweloperów", 1800);
  });
}

export function renderOverview() { renderHealth(); renderCWV(); renderSummary(); renderTrend(); renderReg(); renderRecs(); }

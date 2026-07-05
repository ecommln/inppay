// Widok "Szczegóły per URL": tabela z filtrem sekcji (wszystkie/serwis/blog)
// oraz karta pojedynczego URL (metryki mobile+desktop, trend, wynik Lighthouse).
import { store, rows } from "./store.js";
import { META, LEVER, LVL, esc, fmt, val, pillOf, pillTag } from "./format.js";
import { lineChart } from "./charts.js";
import { $ } from "./dom.js";

// Etykiety lejków (grupy biznesowe) - spójne z config.json > business.funnel_labels.
const FUNNEL_PL = {
  merchant: "Lejek B2B (sklepy)", consumer: "Konsument / aplikacja",
  campaign: "Kampanie i promocje", support: "Wsparcie i informacje", seo: "Blog (SEO)",
};

// Grupa biznesowa wiersza: conversion=lejek (tier 1), campaign/support=funnel, blog=kategoria.
function inGroup(r, g) {
  if (!g || g === "all") return true;
  if (g === "conversion") return r.tier === 1;
  if (g === "blog") return (r.category || "core") === "blog";
  return r.funnel === g;
}
function scopeFlag(r) {
  return r.field_scope === "origin"
    ? ' <span title="Dane dla całej domeny (origin)" style="color:var(--muted2);cursor:help">*</span>' : "";
}
// Tagi biznesowe wiersza: Lejek (tier 1) + Ads (cel płatnego ruchu).
function rowTags(r) {
  return (r.tier === 1 ? '<span class="rtag funnel">Lejek</span>' : '') +
         (r.ads ? '<span class="rtag ads">Ads</span>' : '');
}
function groupCounts() {
  const seen = new Set(), rs = [];
  store.DATA.results.forEach(r => { if (seen.has(r.url)) return; seen.add(r.url); rs.push(r); });
  const n = g => rs.filter(r => inGroup(r, g)).length;
  return { all: rs.length, conversion: n("conversion"), campaign: n("campaign"), support: n("support"), blog: n("blog") };
}
function resultFor(url, strat) { return store.DATA.results.find(r => r.url === url && r.strategy === strat); }

/* ---------- Lista (tabela) ---------- */
export function renderDetail() {
  const body = $("detailBody");
  if (!body) return;
  if (store.state.drill) { renderDrill(body); return; }
  const st = store.state, sc = groupCounts();
  let rs = rows().filter(r => inGroup(r, st.section));
  const order = { good: 0, "needs-improvement": 1, poor: 2, B: -1 };
  rs.sort((a, b) => {
    let A, B;
    if (st.sort === "label") { A = a.label; B = b.label; }
    else if (st.sort === "overall") { A = order[a.status.overall]; B = order[b.status.overall]; }
    else if (st.sort === "score") { A = (a.lab || {}).score || 0; B = (b.lab || {}).score || 0; }
    else { A = val(a, st.sort) || 0; B = val(b, st.sort) || 0; }
    if (A < B) return st.dir; if (A > B) return -st.dir; return 0;
  });
  const tab = (k, lbl, n) => `<button class="tab ${st.section === k ? 'active' : ''}" data-sec="${k}">${lbl} <span class="cnt">${n}</span></button>`;
  let h = `<div class="sec" style="margin-top:0;border-top:1px solid var(--line);padding-top:22px">
    <div style="font-size:11px;font-weight:700;letter-spacing:.06em;color:var(--muted2);text-transform:uppercase">Sekcja biznesowa</div>
    <div class="tabs">${tab("all", "Wszystkie", sc.all)}${tab("conversion", "🎯 Lejek konwersji", sc.conversion)}${tab("campaign", "Kampanie", sc.campaign)}${tab("support", "Wsparcie", sc.support)}${tab("blog", "Blog", sc.blog)}</div>
    <p style="margin:16px 0 0;font-size:12.5px;color:var(--muted);font-weight:500">Kliknij wiersz, aby otworzyć kartę URL — mobile i desktop, trend i rekomendacje. <span class="rtag funnel">Lejek</span> = strona na przychód, <span class="rtag ads">Ads</span> = cel płatnego ruchu.</p></div>
    <div class="utable-wrap"><table class="ut"><thead><tr>
      <th data-sort="label">PODSTRONA</th><th data-sort="LCP">LCP</th><th data-sort="CLS">CLS</th>
      <th data-sort="TTFB">TTFB</th><th data-sort="INP">INP</th><th data-sort="score">WYNIK</th><th data-sort="overall">STATUS</th>
    </tr></thead><tbody>`;
  rs.forEach(r => {
    const cell = m => `<td><b>${fmt(m, val(r, m))}</b> ${pillTag(m, val(r, m))}</td>`;
    const p = pillOf(r.status.overall);
    h += `<tr class="row" data-url="${esc(r.url)}">
      <td><div class="uname">${esc(r.label)}${scopeFlag(r)}${rowTags(r)}</div><div class="upath">${esc(r.url.replace('https://inpostpay.pl', '') || '/')}</div></td>
      ${cell("LCP")}${cell("CLS")}${cell("TTFB")}${cell("INP")}
      <td style="font-weight:800;font-size:14px">${(r.lab || {}).score ?? "–"}</td>
      <td><span class="pill big" style="background:${p.c}">${p.label}</span><span class="rowmore">szczegóły ›</span></td></tr>`;
  });
  body.innerHTML = h + `</tbody></table></div>`;
  body.querySelectorAll(".tab").forEach(t => t.onclick = () => { store.state.section = t.dataset.sec; renderDetail(); });
  body.querySelectorAll("th[data-sort]").forEach(th => th.onclick = () => {
    const s = th.dataset.sort; st.dir = (st.sort === s) ? -st.dir : -1; st.sort = s; renderDetail();
  });
  body.querySelectorAll("tr.row").forEach(tr => tr.onclick = () => {
    store.state.drill = tr.dataset.url; renderDetail(); window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

/* ---------- Karta pojedynczego URL ---------- */
function drillRows(r) {
  if (!r) return `<div class="drow"><span class="k">Brak pomiaru</span></div>`;
  const row = m => `<div class="drow"><span class="k"><b>${m}</b> · <span>${META[m].human}</span></span>
    <span class="v"><b>${fmt(m, val(r, m))}</b>${pillTag(m, val(r, m))}</span></div>`;
  const sc = (r.lab || {}).score;
  return row("LCP") + row("CLS") + row("TTFB") + row("INP") +
    `<div class="drow"><span class="k">Wynik Lighthouse</span><span class="v"><b>${sc ?? "–"} / 100</b></span></div>`;
}
// Mapa audytów Lighthouse -> metryka, na którą wpływają (spójna z scripts/recommendations.py).
// Nieznane ID trafiają domyślnie na LCP (tak jak w pipeline'ie).
const OPP_METRIC = {
  "unused-javascript": "LCP", "render-blocking-resources": "LCP", "modern-image-formats": "LCP",
  "uses-responsive-images": "LCP", "uses-optimized-images": "LCP", "efficient-animated-content": "LCP",
  "unminified-javascript": "LCP", "unminified-css": "LCP", "unused-css-rules": "LCP",
  "server-response-time": "TTFB", "redirects": "TTFB", "uses-text-compression": "TTFB", "uses-long-cache-ttl": "TTFB",
  "unsized-images": "CLS", "layout-shifts": "CLS", "font-display": "CLS",
};
// Priorytet = oszczędność (ms) x waga strony - te same progi co w recommendations.py.
function priorityLabel(score) { return score >= 2000 ? "Wysoki" : score >= 700 ? "Średni" : "Niski"; }

// Rekomendacje deweloperskie dla jednego URL: audyty Lighthouse (opportunities) z
// mobile i desktop, priorytetyzowane, z dźwignią biznesową i szacowaną oszczędnością.
function drillRecs(rM, rD) {
  const items = [];
  [["mobile", "📱", rM], ["desktop", "🖥", rD]].forEach(([strat, icon, r]) => {
    if (!r) return;
    const w = r.weight || 1;
    (r.opportunities || []).forEach(o => {
      const metric = OPP_METRIC[o.id] || "LCP", savings = o.savings_ms || 0;
      items.push({ strat, icon, metric, savings, priority: priorityLabel(savings * w), title: o.title });
    });
  });
  if (!items.length)
    return `<p class="rec-sub" style="margin-top:14px">✓ Lighthouse nie wykrył istotnych wąskich gardeł na tej podstronie - brak rekomendacji.</p>`;
  items.sort((a, b) => b.savings - a.savings);
  return items.map(it => {
    const lv = LVL[it.priority] || LVL["Niski"];
    return `<div class="rec">
      <span class="lvl" style="background:${lv.bg};color:${lv.fg}">${it.priority}</span>
      <div class="body"><div class="title">${esc(it.title)}</div>
        <div class="sub">${it.icon} ${it.strat === "mobile" ? "Mobile" : "Desktop"} · metryka ${it.metric}</div>
        <div class="meta"><span class="lever">${LEVER[it.metric] || "UX"}</span>
          <span class="desc">${esc(META[it.metric].desc)}</span></div></div>
      <span class="ms">~${it.savings} ms</span></div>`;
  }).join("");
}

function renderDrill(body) {
  const url = store.state.drill, rM = resultFor(url, "mobile"), rD = resultFor(url, "desktop"), any = rM || rD;
  if (!any) { body.innerHTML = `<div class="sec">Brak danych.</div>`; return; }
  const funnelLbl = FUNNEL_PL[any.funnel] || "Serwis";
  const tags = (any.tier === 1 ? '<span class="rtag funnel">Lejek konwersji</span>' : '') +
               (any.ads ? '<span class="rtag ads">Cel Ads</span>' : '');
  const dbox = (title, r) => {
    const p = pillOf(r ? r.status.overall : null);
    return `<div class="dbox"><div class="dbox-head"><span class="t">${title}</span>
      <span class="pill" style="background:${p.c}">${p.label}</span></div>${drillRows(r)}</div>`;
  };
  body.innerHTML = `<div class="sec" style="margin-top:0;border-top:1px solid var(--line);padding-top:22px">
    <button class="drill-back" id="drillBack">← Wróć do listy</button>
    <div class="drill-head"><h2>${esc(any.label)}</h2>
      <span class="secbadge">${esc(funnelLbl)}</span>${tags}
      <a class="rowmore" style="margin:0" href="https://pagespeed.web.dev/analysis?url=${encodeURIComponent(url)}" target="_blank">Pełny raport PSI ↗</a></div>
    <div class="drill-url">${esc(url)}</div>
    <div class="dboxes">${dbox("📱 MOBILE", rM)}${dbox("🖥 DESKTOP", rD)}</div>
    <div style="margin-top:40px">
      <div style="font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted2)">🛠 Rekomendacje dla deweloperów</div>
      <p class="rec-sub">Konkretne działania z audytu Lighthouse dla tej podstrony - priorytet ważony wartością strony, oszczędność = szacowany zysk czasu ładowania.</p>
      <div class="recs">${drillRecs(rM, rD)}</div></div>
    <div style="margin-top:40px">
      <div style="font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted2)">Trend tego URL · ${store.state.strat === "mobile" ? "Mobile" : "Desktop"} · ${store.state.metric}</div>
      <canvas id="drillChart" height="90" style="margin-top:14px"></canvas>
      <div class="sec-sub" id="drillNote" style="margin-top:6px"></div></div></div>`;
  $("drillBack").onclick = () => { store.state.drill = ""; renderDetail(); };
  drawDrillTrend(url);
}
export function drawDrillTrend(url) {
  const ctx = $("drillChart");
  if (!ctx) return;
  const m = store.state.metric, runs = store.HIST.runs.slice(), labels = runs.map(r => r.timestamp.slice(5, 10));
  const series = runs.map(run => {
    const p = (run.series || []).find(x => x.url === url && x.strategy === store.state.strat);
    return p ? p[m] : null;
  });
  const note = $("drillNote");
  if (note) note.textContent = store.HIST.runs.length < 2 ? "Jeden pomiar - trend zapełni się przy kolejnych przebiegach." : "";
  if (store.drillChart) store.drillChart.destroy();
  store.drillChart = lineChart(ctx, { labels, data: series, metric: m });
}

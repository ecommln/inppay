// Moduł wejściowy: ładuje dane, renderuje widoki i podpina interakcje
// (nawigacja, motyw dzień/noc, przełącznik mobile/desktop, filtry trendu).
import { store } from "./store.js";
import { applyThresholds } from "./format.js";
import { renderOverview, renderTrend, copyRecs } from "./overview.js";
import { renderDetail, drawDrillTrend } from "./detail.js";
import { $ } from "./dom.js";

function setView(v) {
  store.state.view = v;
  store.state.drill = "";
  $("viewOverview").classList.toggle("hidden", v !== "overview");
  $("viewUrls").classList.toggle("hidden", v !== "urls");
  document.querySelectorAll(".nav a").forEach(a => a.classList.toggle("active", a.dataset.view === v));
  if (v === "urls") renderDetail(); else renderTrend();  // przerysuj wykres w widocznym kontenerze
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setStrat(s) {
  store.state.strat = s;
  document.querySelectorAll("[data-strat-tabs] button").forEach(b => b.classList.toggle("active", b.dataset.strat === s));
  renderOverview();
  if (store.state.view === "urls") renderDetail();
  renderHead();
}

function setTheme(t) {
  // Klasa na <html> (nie na #app), żeby zmienne CSS objęły też body i główny obszar.
  document.documentElement.classList.toggle("theme-dark", t === "dark");
  document.querySelectorAll("#themeToggle button").forEach(b => b.classList.toggle("active", b.dataset.theme === t));
  try { localStorage.setItem("cwv-theme", t); } catch (e) {}
  if (store.trendChart) renderTrend();
  if (store.drillChart && store.state.drill) drawDrillTrend(store.state.drill);
}

function renderHead() {
  const ts = "Ostatni pomiar " + new Date(store.DATA.timestamp).toLocaleString("pl-PL") +
    " · " + (store.state.strat === "mobile" ? "Widok mobilny" : "Widok desktopowy");
  $("lastRunO").textContent = ts;
  $("lastRunU").textContent = ts;
}

async function boot() {
  try {
    store.DATA = await (await fetch("data/latest.json?_=" + Date.now())).json();
    store.HIST = await (await fetch("data/history-index.json?_=" + Date.now())).json();
  } catch (e) {
    document.querySelector("#viewOverview h1").textContent = "Nie udało się wczytać danych";
    return;
  }
  applyThresholds(store.DATA.thresholds);

  let th = "light";
  try { th = localStorage.getItem("cwv-theme") || "light"; } catch (e) {}
  setTheme(th);

  $("sideStatus").innerHTML = store.DATA.mock
    ? `<span class="dot dot-warn"></span>Dane demonstracyjne`
    : `<span class="dot dot-good"></span>Dane na żywo`;
  if (store.DATA.mock) {
    $("mockbar").innerHTML = `<div class="mockbar">⚠️ <b>Dane demonstracyjne.</b> Po podpięciu klucza Google API zobaczysz realne pomiary inpostpay.pl.</div>`;
  }

  renderHead();
  renderOverview();

  $("nav").querySelectorAll("a").forEach(a => a.onclick = e => { e.preventDefault(); setView(a.dataset.view); });
  document.querySelectorAll("[data-strat-tabs] button").forEach(b => b.onclick = () => setStrat(b.dataset.strat));
  document.querySelectorAll("#themeToggle button").forEach(b => b.onclick = () => setTheme(b.dataset.theme));
  $("fMetric").onchange = e => { store.state.metric = e.target.value; renderTrend(); };
  $("fRange").onchange = e => { store.state.range = +e.target.value; renderTrend(); };
  $("copyRecs").onclick = copyRecs;

  // "Zobacz szczegóły" w boxach podsumowania -> widok URL przefiltrowany na sekcję.
  document.querySelectorAll("[data-goto]").forEach(b => b.onclick = () => {
    store.state.section = b.dataset.goto;
    setView("urls");
  });
}

boot();

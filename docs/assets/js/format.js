// Stałe progów/etykiet + funkcje czyste (formatowanie, statusy). Bez efektów
// ubocznych i bez dostępu do DOM - łatwe do testowania i ponownego użycia.

// Progi Google (LCP/TTFB/INP w ms, CLS bezwymiarowe). Nadpisywane danymi z
// latest.json przez applyThresholds() - jedno źródło prawdy o progach.
export const THRESHOLDS = {
  LCP: { good: 2500, poor: 4000 },
  CLS: { good: 0.1, poor: 0.25 },
  TTFB: { good: 800, poor: 1800 },
  INP: { good: 200, poor: 500 },
};
export function applyThresholds(t) { if (t) Object.assign(THRESHOLDS, t); }

// Ludzka nazwa + jednozdaniowy wpływ biznesowy każdej metryki.
export const META = {
  LCP: { human: "Szybkość ładowania", desc: "Jak szybko widać główną treść. Wolno = porzucenia i wyższy koszt Google Ads." },
  CLS: { human: "Stabilność strony", desc: "Czy układ przeskakuje podczas ładowania. Skoki = błędne kliknięcia i porzucone formularze." },
  TTFB: { human: "Reakcja serwera", desc: "Jak szybko serwer zaczyna odpowiadać. Wolno = gorsze SEO i dłuższe wejścia." },
  INP: { human: "Płynność klikania", desc: "Jak szybko strona reaguje na kliknięcia. Wolno = frustracja użytkownika." },
};

export const PILL = {
  D: { label: "Dobry", c: "var(--good)" },
  U: { label: "Uwaga", c: "var(--warn)" },
  S: { label: "Słaby", c: "var(--poor)" },
  B: { label: "Brak danych", c: "#9ca3af" },
};
// Status pipeline'u (good/needs-improvement/poor) -> klucz PILL. Lokalne (używa pillOf).
const ST = { good: "D", "needs-improvement": "U", poor: "S" };
export const LEVER = { LCP: "Konwersja", CLS: "Konwersja", TTFB: "SEO", INP: "UX" };
export const LVL = {
  "Wysoki": { bg: "#fbe4ee", fg: "#c01a6e" },
  "Średni": { bg: "#fdeede", fg: "#a85a00" },
  "Niski": { bg: "#eaeeff", fg: "#3a4db0" },
};

// Escapowanie treści wstrzykiwanej przez innerHTML (etykiety mogą pochodzić z API PSI).
export function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Format wartości metryki: przecinek dziesiętny, sekundy dla LCP/TTFB, ms dla INP.
export function fmt(m, v) {
  if (v == null) return "–";
  if (m === "CLS") return v.toFixed(3).replace(".", ",");
  if (m === "INP") return Math.round(v) + " ms";
  if (m === "score") return Math.round(v);
  return (v / 1000).toFixed(2).replace(".", ",") + " s";
}

// Status metryki wg progów Google: D(obry)/U(waga)/S(łaby)/B(rak danych).
export function rate(m, v) {
  if (v == null) return "B";
  const t = THRESHOLDS[m];
  if (!t) return "B";
  if (v < t.good) return "D";
  if (v <= t.poor) return "U";
  return "S";
}

export function pillOf(status) { return PILL[ST[status] || "B"]; }

// Wartość metryki wiersza: preferuj field (realni użytkownicy), fallback lab.
export function val(r, m) {
  const f = r.field || {};
  if (f[m] != null) return f[m];
  const l = r.lab || {};
  return l[m] != null ? l[m] : null;
}

// Etykieta pill dla wartości metryki (HTML).
export function pillTag(m, v) {
  const p = PILL[rate(m, v)];
  return `<span class="pill" style="background:${p.c}">${p.label}</span>`;
}

// Ryzyko dla konwersji na podstawie rozkładu statusów (lejek konwersji).
export function convRisk(c) {
  if (c.poor > 0) return { t: "Wysokie", col: "var(--poor)" };
  if (c["needs-improvement"] > 2) return { t: "Średnie", col: "var(--warn)" };
  if (c["needs-improvement"] > 0) return { t: "Niskie-średnie", col: "var(--warn)" };
  return { t: "Niskie", col: "var(--good)" };
}

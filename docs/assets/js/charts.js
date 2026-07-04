// Wspólny builder wykresu liniowego (trend serwisu i trend pojedynczego URL
// dzielą tę samą konfigurację). Jedno miejsce na kolory i skalę osi.
import { THRESHOLDS } from "./format.js";

// Kolory wykresów (Chart.js nie czyta zmiennych CSS, więc trzymamy je tutaj -
// jedno źródło, spójne z paletą w styles.css).
const CHART = { accent: "#ec0e6e", good: "#16a34a", poor: "#ef4444" };

// Tworzy wykres: seria metryki + dwie linie progów (dobry/słaby). Zwraca instancję.
export function lineChart(ctx, { labels, data, metric }) {
  const t = THRESHOLDS[metric];
  const threshold = (y, color) => ({
    data: labels.map(() => y), borderColor: color, borderDash: [5, 5],
    pointRadius: 0, borderWidth: 1.2,
  });
  return new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: metric, data, borderColor: CHART.accent,
          backgroundColor: "rgba(236,14,110,.07)", tension: .3, fill: true,
          pointRadius: 3, borderWidth: 2.5,
        },
        Object.assign(threshold(t.good, CHART.good), { label: "próg dobry" }),
        Object.assign(threshold(t.poor, CHART.poor), { label: "próg słaby" }),
      ],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: { y: { ticks: { callback: v => metric === "CLS" ? v : (metric === "INP" ? v : (v / 1000) + "s") } } },
    },
  });
}

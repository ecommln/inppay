// Współdzielony stan aplikacji. Jeden obiekt zamiast zmiennych globalnych,
// żeby moduły mogły czytać i mutować te same dane (DATA, HIST, instancje wykresów).
export const store = {
  DATA: null,
  HIST: null,
  trendChart: null,
  drillChart: null,
  state: {
    view: "overview",   // "overview" | "urls"
    strat: "mobile",    // "mobile" | "desktop"
    metric: "LCP",      // metryka wykresu trendu
    range: 0,           // 0 = cały zakres, inaczej liczba dni
    section: "all",     // filtr tabeli: "all" | "serwis" | "blog"
    drill: "",          // URL otwarty w karcie szczegółów (pusty = lista)
    sort: "overall",
    dir: -1,
  },
};

// Wiersze bieżącej strategii (mobile/desktop) - używane w przeglądzie i tabeli.
export function rows() {
  return store.DATA.results.filter(r => r.strategy === store.state.strat);
}

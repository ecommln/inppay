# -*- coding: utf-8 -*-
"""Rekomendacje optymalizacji dla deweloperów.

Buduje priorytetową listę działań z audytów Lighthouse (`opportunities`),
tłumaczy techniczne ID na czytelne działania PL, przypisuje dźwignię biznesową
i priorytet ważony wartością strony (`weight`).
"""

# Wpływ biznesowy per metryka (jedno zdanie, język decydenta).
BUSINESS_IMPACT = {
    "LCP":  "Wolne ładowanie głównej treści zwiększa porzucenia koszyka i podnosi "
            "koszt kliknięcia w Google Ads (niższa jakość strony docelowej).",
    "CLS":  "Skaczący układ strony powoduje błędne kliknięcia i porzucone formularze "
            "- bezpośrednie ryzyko utraty konwersji.",
    "TTFB": "Wolna odpowiedź serwera pogarsza ocenę strony w Google (SEO) i wydłuża "
            "każde wejście użytkownika.",
    "INP":  "Opóźniona reakcja na kliknięcia frustruje użytkownika i obniża zaangażowanie.",
}

# Słownik audytów Lighthouse -> (działanie PL, metryka, na którą wpływa).
OPP_DICT = {
    "unused-javascript":         ("Usuń nieużywany kod JavaScript (code-splitting, tree-shaking)", "LCP"),
    "render-blocking-resources": ("Odblokuj renderowanie: odrocz nieistotne CSS/JS (defer/async)", "LCP"),
    "modern-image-formats":      ("Przekonwertuj obrazy do WebP/AVIF", "LCP"),
    "uses-responsive-images":    ("Serwuj obrazy w rozmiarze dopasowanym do ekranu", "LCP"),
    "uses-optimized-images":     ("Skompresuj obrazy (bezstratnie/stratnie)", "LCP"),
    "efficient-animated-content":("Zamień ciężkie GIF-y na wideo (WebM/MP4)", "LCP"),
    "server-response-time":      ("Skróć czas odpowiedzi serwera (cache, CDN, optymalizacja backendu)", "TTFB"),
    "redirects":                 ("Wyeliminuj zbędne przekierowania", "TTFB"),
    "uses-text-compression":     ("Włącz kompresję tekstu (gzip/brotli)", "TTFB"),
    "uses-long-cache-ttl":       ("Wydłuż czas cache zasobów statycznych", "TTFB"),
    "unminified-javascript":     ("Zminifikuj pliki JavaScript", "LCP"),
    "unminified-css":            ("Zminifikuj pliki CSS", "LCP"),
    "unsized-images":            ("Ustaw wymiary width/height na obrazach (stabilny układ)", "CLS"),
    "layout-shifts":             ("Zarezerwuj miejsce na elementy ładowane dynamicznie", "CLS"),
    "font-display":              ("Ustaw font-display: swap, by tekst pojawiał się od razu", "CLS"),
}

PRIORITY_LABEL = [(2000, "Wysoki"), (700, "Średni"), (0, "Niski")]


def priority_label(score):
    for threshold, label in PRIORITY_LABEL:
        if score >= threshold:
            return label
    return "Niski"


def build_recommendations(results):
    """Top 10 działań, priorytet = szacowana oszczędność (ms) x waga strony.
    Deduplikuje to samo działanie na tej samej stronie (mobile+desktop)."""
    recs = []
    for r in results:
        weight = r.get("weight", 1)
        for opp in r.get("opportunities", []):
            action, metric = OPP_DICT.get(opp["id"], (opp["title"], "LCP"))
            savings = opp.get("savings_ms", 0)
            score = savings * weight
            recs.append({
                "action": action,
                "url": r["url"],
                "label": r["label"],
                "strategy": r["strategy"],
                "metric": metric,
                "savings_ms": savings,
                "priority_score": score,
                "priority": priority_label(score),
                "business_impact": BUSINESS_IMPACT.get(metric, ""),
            })
    merged = {}
    for rec in recs:
        key = (rec["label"], rec["action"])
        if key not in merged or rec["priority_score"] > merged[key]["priority_score"]:
            merged[key] = rec
    out = sorted(merged.values(), key=lambda x: x["priority_score"], reverse=True)
    return out[:10]

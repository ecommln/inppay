# -*- coding: utf-8 -*-
"""Generator danych DEMONSTRACYJNYCH (bez klucza API).

Tworzy kilka przebiegów w historii, żeby dashboard, wykres trendu, regresje
i alert działały od razu - zanim podepniemy GOOGLE_API_KEY i pobierzemy realne
dane z inpostpay.pl. Dane są realistyczne, ale ZMYŚLONE i tak oznaczone
(pole "mock": true w każdym przebiegu -> dashboard pokazuje baner).

Scenariusz wpisany w dane, żeby pokazać wszystkie funkcje narzędzia:
  * mobile generalnie gorszy niż desktop (mobile-first ma znaczenie),
  * "Dla biznesu (landing)" na mobile PSUJE SIĘ w czasie -> kończy w statusie
    'poor' (odpala alert + regresję),
  * jedna podstrona bez danych field (fallback na lab),
  * wszędzie realistyczne 'opportunities' -> rekomendacje mają z czego powstać.

Uruchom:  py scripts/seed_mock.py
"""
import hashlib
import random
from datetime import datetime, timedelta, timezone

from common import (
    load_config, ensure_dirs, write_json,
    HISTORY_DIR, LATEST_PATH, publish_to_docs,
)

random.seed(42)  # deterministycznie - te same dane przy każdym uruchomieniu


def stable_int(s):
    """Stabilny hash stringa (wbudowany hash() jest losowany per proces przez
    PYTHONHASHSEED - psułoby to powtarzalność danych demo)."""
    return int(hashlib.md5(s.encode("utf-8")).hexdigest(), 16)

# Bazowe (dobre) wartości per strategia; mobile słabszy
BASE = {
    "mobile":  {"LCP": 2200, "CLS": 0.06, "TTFB": 650, "INP": 180, "FCP": 1600, "score": 78},
    "desktop": {"LCP": 1500, "CLS": 0.03, "TTFB": 480, "INP": 120, "FCP": 1050, "score": 93},
}

# Katalog realistycznych audytów Lighthouse (id -> tytuł PL, typowa oszczędność)
OPP_POOL = [
    ("unused-javascript",        "Zredukuj nieużywany JavaScript",              (300, 900)),
    ("render-blocking-resources","Wyeliminuj zasoby blokujące renderowanie",    (250, 700)),
    ("modern-image-formats",     "Użyj nowoczesnych formatów obrazów (WebP/AVIF)", (200, 800)),
    ("uses-responsive-images",   "Dostosuj rozmiar obrazów do wyświetlania",    (150, 600)),
    ("server-response-time",     "Skróć czas odpowiedzi serwera (TTFB)",        (200, 700)),
    ("uses-text-compression",    "Włącz kompresję tekstu (gzip/brotli)",        (100, 400)),
    ("uses-long-cache-ttl",      "Wydłuż czas cache zasobów statycznych",       (100, 350)),
    ("unminified-javascript",    "Zminifikuj JavaScript",                       (100, 300)),
]


def _jitter(v, pct=0.02):
    # Mały szum: realne CrUX p75/28 dni jest stabilne między przebiegami,
    # więc regresje mają wynikać ze scenariusza, a nie z losowości.
    return v * (1 + random.uniform(-pct, pct))


def _opps_for(url_hash, strategy, severity):
    """Kilka opportunities; im gorsza strona, tym większe oszczędności."""
    picks = random.sample(OPP_POOL, k=random.randint(3, 5))
    out = []
    for oid, title, (lo, hi) in picks:
        base = random.uniform(lo, hi) * (1 + severity)
        out.append({"id": oid, "title": title, "savings_ms": int(round(base))})
    out.sort(key=lambda o: o["savings_ms"], reverse=True)
    return out[:5]


def _measure(entry, strategy, severity, field_mode="url"):
    """severity 0..1 pogarsza wszystkie metryki proporcjonalnie.
    field_mode: 'url' = dane field dla URL, 'origin' = tylko dla domeny
    (typowe dla artykułów bloga o małym ruchu), 'none' = brak field (fallback lab)."""
    b = BASE[strategy]
    weight = entry.get("weight", 1)
    lcp = _jitter(b["LCP"]) * (1 + 1.6 * severity)
    cls = _jitter(b["CLS"]) * (1 + 2.5 * severity)
    ttfb = _jitter(b["TTFB"]) * (1 + 1.3 * severity)
    inp = _jitter(b["INP"]) * (1 + 1.4 * severity)
    fcp = _jitter(b["FCP"]) * (1 + 1.4 * severity)  # FCP rośnie razem z TTFB/LCP
    score = max(20, min(100, b["score"] - 45 * severity + random.uniform(-3, 3)))

    lab = {
        "LCP": int(round(lcp)),
        "CLS": round(cls, 3),
        "TTFB": int(round(ttfb)),
        "FCP": int(round(fcp)),
        "score": int(round(score)),
    }
    if field_mode == "none":
        field, scope = None, None
    else:
        # field zwykle nieco inny niż lab (realni użytkownicy), ale stabilny w czasie
        field = {
            "LCP": int(round(lcp * random.uniform(0.97, 1.03))),
            "CLS": round(cls * random.uniform(0.97, 1.03), 3),
            "TTFB": int(round(ttfb * random.uniform(0.98, 1.04))),
            "INP": int(round(inp)),
            "FCP": int(round(fcp * random.uniform(0.97, 1.03))),
        }
        scope = field_mode  # 'url' lub 'origin'
    return {
        "url": entry["url"],
        "label": entry["label"],
        "weight": weight,
        "category": entry.get("category", "core"),
        "strategy": strategy,
        "field": field,
        "field_scope": scope,
        "lab": lab,
        "lab_measured": True,
        "opportunities": _opps_for(hash(entry["url"]), strategy, severity),
    }


def _demo_entries(cfg):
    """Lista URL do danych demo (offline, bez sitemapy): strony serwisu z
    core_overrides + garść przykładowych artykułów bloga, żeby w dashboardzie
    było widać segmentację serwis/blog jeszcze przed pierwszym realnym pomiarem."""
    site = cfg["site"]
    entries = []
    for path, meta in cfg.get("core_overrides", {}).items():
        entries.append({"url": site + path, "label": meta["label"],
                        "weight": meta.get("weight", 2), "category": "core"})
    demo_blog = [
        "jak-bezpiecznie-kupowac-przez-internet-przydatne-wskazowki-i-porady",
        "jak-placic-blikiem-w-sklepie-internetowym",
        "co-jest-m-commerce-dowiedz-sie-wiecej-o-tym-modelu-sprzedazy",
        "czym-jest-konwersja-w-e-commerce-jakie-jest-jej-znaczenie",
        "page-speed-co-jest-i-jak-wplywa-na-sklep-internetowy",
        "porzucony-koszyk-co-oznacza-w-e-commerce",
        "jak-zadbac-o-ux-swojego-sklepu-internetowego",
        "trendy-w-platnosciach-internetowych-globalne-zmiany",
    ]
    for slug in demo_blog:
        label = slug.replace("-", " ")
        entries.append({"url": f"{site}/aktualnosci-{slug}",
                        "label": label[:1].upper() + label[1:],
                        "weight": 1, "category": "blog"})
    return entries


def build_run(cfg, timestamp, progress):
    """progress 0..1 = jak daleko w czasie (do modelowania regresji)."""
    results = []
    for i, entry in enumerate(_demo_entries(cfg)):
        for strategy in cfg["strategies"]:
            # Bazowa "trudność" strony (deterministyczna per URL)
            base_sev = (stable_int(entry["url"]) % 30) / 100.0  # 0..0.29

            # Scenariusz regresji: landing "dlabiznesu" na mobile psuje się w czasie
            if entry["url"].endswith("/dlabiznesu") and strategy == "mobile":
                base_sev = 0.15 + 0.75 * progress  # dochodzi do ~0.9 => poor

            # Jeden artykuł bloga ze słabym wynikiem na mobile (ciężki obraz w szablonie)
            if "/aktualnosci-page-speed" in entry["url"] and strategy == "mobile":
                base_sev = 0.8

            # Zakres danych field:
            #  - /b2bform: brak danych field (mały ruch) -> fallback na lab,
            #  - artykuły bloga: dane tylko origin (poziom domeny) - realny wzorzec,
            #  - reszta stron serwisu: dane URL-scope.
            if entry["url"].endswith("/b2bform"):
                field_mode = "none"
            elif entry.get("category") == "blog":
                field_mode = "origin"
            else:
                field_mode = "url"

            results.append(_measure(entry, strategy, base_sev, field_mode=field_mode))
    return {
        "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "site": cfg["site"],
        "mock": True,
        "results": results,
    }


def main(runs=6, step_days=3):
    cfg = load_config()
    ensure_dirs()
    # Wyczyść starą historię mock, żeby nie mieszać przebiegów
    for f in HISTORY_DIR.glob("*.json"):
        f.unlink()

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    latest = None
    for k in range(runs):
        # najstarszy pierwszy; ostatni = teraz
        idx = runs - 1 - k
        ts = now - timedelta(days=step_days * idx)
        progress = k / (runs - 1)
        run = build_run(cfg, ts, progress)
        fname = run["timestamp"].replace(":", "").replace("-", "")
        write_json(HISTORY_DIR / f"{fname}.json", run)
        latest = run

    write_json(LATEST_PATH, latest)
    publish_to_docs()
    print(f"seed_mock.py: wygenerowano {runs} przebiegów demonstracyjnych "
          f"(co {step_days} dni). Najnowszy: {latest['timestamp']}.")
    print("Teraz uruchom:  py scripts/evaluate.py")


if __name__ == "__main__":
    main()

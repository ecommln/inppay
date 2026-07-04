# -*- coding: utf-8 -*-
"""Kolektor danych Core Web Vitals dla inpostpay.pl.

Lista URL jest budowana automatycznie z sitemap.xml serwisu (bez hardkodu),
dzięki czemu narzędzie samo nadąża za nowymi podstronami. Każdy URL jest
klasyfikowany jako strona serwisu ('core') lub artykuł bloga ('blog').

Dla każdej pary (URL x strategia) pobiera:
  * dane FIELD z Chrome UX Report API (realni użytkownicy, p75 z 28 dni) -
    główne źródło statusów, POBIERANE DLA WSZYSTKICH URL (pełne pokrycie serwisu),
  * dane LAB z PageSpeed Insights API (Lighthouse) - Performance Score
    i 'opportunities', czyli surowiec do rekomendacji dla deweloperów.

Lighthouse jest wolny (~10-25 s/URL), a artykuły bloga dzielą jeden szablon,
więc lab pobieramy wg 'discovery.lab_scope' w config.json:
  * 'all'              - lab dla każdego URL (pełne, ale wolne: setki wywołań),
  * 'core_plus_sample' - lab dla wszystkich stron core + N reprezentantów bloga
                         + każdego URL, który field oznaczył jako słaby.

Wynik: data/history/<timestamp>.json + data/latest.json, a następnie kopie
do docs/data (dla dashboardu na GitHub Pages).

Wymaga zmiennej środowiskowej GOOGLE_API_KEY (jeden klucz, w GCP włączone
oba API: PageSpeed Insights API i Chrome UX Report API).
"""
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

from common import (
    load_config, ensure_dirs, write_json,
    HISTORY_DIR, LATEST_PATH, publish_to_docs, rate_status,
)
from discovery import discover_urls

CRUX_URL = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"
PSI_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# Ile zapytań równolegle. PSI sam się dławi latencją (~15 s/wywołanie), więc
# 8 wątków to bezpiecznie ~0,5 req/s. CrUX jest szybkie, dlatego dodatkowo
# ograniczamy je limiterem tempa (limit API to 150 zapytań/min na klucz).
MAX_WORKERS = 8


class RateLimiter:
    """Prosty globalny throttle - gwarantuje min. odstęp między zapytaniami
    niezależnie od liczby wątków. Dla CrUX: min_interval 0,45 s => ~133 req/min,
    z zapasem poniżej limitu 150/min."""
    def __init__(self, min_interval):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            sleep_for = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.min_interval
        if sleep_for > 0:
            time.sleep(sleep_for)


CRUX_LIMITER = RateLimiter(0.45)
_print_lock = threading.Lock()

# Mapowanie: nasze nazwy strategii -> formFactor CrUX / strategy PSI
FORM_FACTOR = {"mobile": "PHONE", "desktop": "DESKTOP"}

# Mapowanie metryk CrUX -> nasze skróty
CRUX_METRICS = {
    "largest_contentful_paint": "LCP",
    "cumulative_layout_shift": "CLS",
    "experimental_time_to_first_byte": "TTFB",
    "interaction_to_next_paint": "INP",
}


def _redact(text, key):
    """Usuwa klucz API z komunikatu, zanim trafi do logów lub publicznego JSON-a."""
    if key and text:
        text = text.replace(key, "***")
    return text


def _api_key():
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        sys.exit(
            "BŁĄD: brak zmiennej GOOGLE_API_KEY.\n"
            "Ustaw klucz z Google Cloud (włączone PageSpeed Insights API + "
            "Chrome UX Report API), np.:\n"
            "  PowerShell:  $env:GOOGLE_API_KEY = 'twoj_klucz'\n"
            "  bash:        export GOOGLE_API_KEY=twoj_klucz\n"
            "Do samego zbudowania dashboardu bez klucza użyj: py scripts/seed_mock.py"
        )
    return key


# ---------------------------------------------------------------------------
# Odkrywanie URL z sitemap.xml (zamiast ręcznej listy w configu)
# ---------------------------------------------------------------------------

def fetch_field_crux(url, strategy, key):
    """Dane field z CrUX API. 404 = brak danych dla URL (NORMALNE dla podstron
    o małym ruchu) -> fallback na 'origin' (cała domena). Zwraca (dane, scope)."""
    form_factor = FORM_FACTOR[strategy]

    def _query(body_key, body_val):
        body = {
            body_key: body_val,
            "formFactor": form_factor,
            "metrics": list(CRUX_METRICS.keys()),
        }
        CRUX_LIMITER.wait()  # trzymaj tempo poniżej limitu 150/min (praca wielowątkowa)
        return requests.post(f"{CRUX_URL}?key={key}", json=body, timeout=30)

    for scope, (bk, bv) in (("url", ("url", url)), ("origin", ("origin", url))):
        try:
            resp = _query(bk, bv)
        except requests.RequestException as e:
            print(f"     CrUX błąd sieci ({scope}): {_redact(str(e), key)}")
            continue
        if resp.status_code == 404:
            continue  # brak danych w tym zakresie - spróbuj origin, potem odpuść
        if resp.status_code != 200:
            # np. 403 (zły/niewłączony klucz), 429 (limit), 5xx - NIE mylić z 404.
            # Logujemy, żeby błąd konfiguracji nie wyglądał jak "brak danych field".
            print(f"     CrUX HTTP {resp.status_code} ({scope}) - sprawdź klucz/limit API")
            continue
        metrics = resp.json().get("record", {}).get("metrics", {})
        out = {}
        for crux_name, short in CRUX_METRICS.items():
            p75 = metrics.get(crux_name, {}).get("percentiles", {}).get("p75")
            if p75 is None:
                continue
            # LCP/TTFB/INP w ms (int), CLS jako float (przychodzi stringiem)
            out[short] = float(p75) if short == "CLS" else int(round(float(p75)))
        if out:
            return out, scope
    return None, None


def fetch_lab_psi(url, strategy, key):
    """Dane lab z PSI (Lighthouse): metryki + score + top opportunities."""
    params = {
        "url": url,
        "strategy": strategy,
        "key": key,
        "category": "performance",
        "locale": "pl",
    }
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.get(PSI_URL, params=params, timeout=120)
            if resp.status_code == 200:
                return _parse_psi(resp.json())
            last_err = f"HTTP {resp.status_code}"
        except requests.RequestException as e:
            # WAŻNE: treść wyjątku requests może zawierać pełny URL z key=...,
            # a ten błąd trafia do JSON publikowanego na Pages. Redagujemy klucz.
            last_err = _redact(str(e), key)
        time.sleep(2 * (attempt + 1))  # backoff
    return {"error": last_err or "nieznany błąd PSI"}


def _parse_psi(data):
    lh = data.get("lighthouseResult", {})
    audits = lh.get("audits", {})

    def num(audit_id):
        return audits.get(audit_id, {}).get("numericValue")

    lcp = num("largest-contentful-paint")
    cls = num("cumulative-layout-shift")
    ttfb = num("server-response-time")
    score = lh.get("categories", {}).get("performance", {}).get("score")

    opportunities = []
    for aid, audit in audits.items():
        details = audit.get("details", {})
        savings = details.get("overallSavingsMs")
        if isinstance(savings, (int, float)) and savings > 0:
            opportunities.append({
                "id": aid,
                "title": audit.get("title", aid),
                "savings_ms": int(round(savings)),
            })
    opportunities.sort(key=lambda o: o["savings_ms"], reverse=True)

    return {
        "LCP": int(round(lcp)) if lcp is not None else None,
        "CLS": round(float(cls), 3) if cls is not None else None,
        "TTFB": int(round(ttfb)) if ttfb is not None else None,
        "score": int(round(score * 100)) if score is not None else None,
        "opportunities": opportunities[:5],
    }


def _progress(done, total, phase):
    with _print_lock:
        if done == total or done % 50 == 0:
            print(f"     {phase}: {done}/{total}")


def _run_parallel(jobs, fn, phase):
    """Uruchamia fn(*args) dla listy (key, args) równolegle. Zwraca {key: wynik}."""
    out = {}
    total = len(jobs)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(fn, *args): key for key, args in jobs}
        for done, fut in enumerate(as_completed(futs), 1):
            out[futs[fut]] = fut.result()
            _progress(done, total, phase)
    return out


def _select_lab_urls(urls, field_map, strategies, thresholds, lab_scope, blog_lab_sample):
    """Zbiór URL, dla których uruchamiamy wolny audyt PSI/Lighthouse.
    'all' = wszystkie; inaczej: strony core + N reprezentantów bloga
    + artykuły, które field (URL-scope) oznaczył jako słabe."""
    selected, blog_labbed = set(), 0
    for entry in urls:  # urls są posortowane: core najpierw, potem blog
        url, cat = entry["url"], entry["category"]
        if lab_scope == "all" or cat == "core":
            selected.add(url)
            continue
        if blog_labbed < blog_lab_sample:
            selected.add(url)
            blog_labbed += 1
            continue
        # próbka wyczerpana - dołóż tylko wyraźnie słabe artykuły (dane URL-scope)
        for strategy in strategies:
            field, scope = field_map.get((url, strategy), (None, None))
            if scope != "url" or not field:
                continue
            if any(rate_status(m, field.get(m), thresholds) == "poor"
                   for m in ("LCP", "CLS", "TTFB")):
                selected.add(url)
                break
    return selected


def collect():
    cfg = load_config()
    key = _api_key()
    ensure_dirs()
    thresholds = cfg["thresholds"]
    strategies = cfg["strategies"]

    d = cfg.get("discovery", {})
    lab_scope = d.get("lab_scope", "core_plus_sample")
    blog_lab_sample = d.get("blog_lab_sample", 4)

    urls = discover_urls(cfg)
    n_core = sum(1 for u in urls if u["category"] == "core")
    n_blog = len(urls) - n_core
    print(f"  Do zmierzenia: {len(urls)} URL ({n_core} core + {n_blog} blog) x "
          f"{len(strategies)} strategie. lab_scope='{lab_scope}', {MAX_WORKERS} wątków.")

    # --- Faza 1: field (CrUX) dla WSZYSTKICH (url x strategia) - pełne pokrycie ---
    print("  Faza 1/2: CrUX (field) dla wszystkich URL...")
    field_jobs = [((u["url"], s), (u["url"], s, key)) for u in urls for s in strategies]
    field_map = _run_parallel(field_jobs, fetch_field_crux, "CrUX")

    # --- Wybór URL do audytu lab ---
    lab_urls = _select_lab_urls(urls, field_map, strategies, thresholds,
                                lab_scope, blog_lab_sample)
    print(f"  Faza 2/2: PSI (lab/Lighthouse) dla {len(lab_urls)} URL "
          f"({len(lab_urls) * len(strategies)} wywołań)...")
    lab_jobs = [((u, s), (u, s, key)) for u in lab_urls for s in strategies]
    lab_map = _run_parallel(lab_jobs, fetch_lab_psi, "PSI")

    # --- Złożenie wyników (kolejność jak w sitemap: core najpierw) ---
    results = []
    for entry in urls:
        url = entry["url"]
        run_lab = url in lab_urls
        for strategy in strategies:
            field, scope = field_map.get((url, strategy), (None, None))
            lab, opportunities = None, []
            if run_lab:
                lab = lab_map.get((url, strategy))
                opportunities = lab.pop("opportunities", []) if isinstance(lab, dict) else []
            results.append({
                "url": url,
                "label": entry["label"],
                "weight": entry["weight"],
                "category": entry["category"],
                "funnel": entry.get("funnel", "support"),
                "tier": entry.get("tier", 2),
                "ads": entry.get("ads", False),
                "strategy": strategy,
                "field": field,
                "field_scope": scope,
                "lab": lab,
                "lab_measured": run_lab,
                "opportunities": opportunities,
            })

    run = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "site": cfg["site"],
        "results": results,
    }
    ts = run["timestamp"].replace(":", "").replace("-", "")
    write_json(HISTORY_DIR / f"{ts}.json", run)
    write_json(LATEST_PATH, run)
    print(f"Zapisano przebieg: {run['timestamp']} ({len(results)} pomiarów, "
          f"lab dla {len(lab_urls)} URL)")
    return run


if __name__ == "__main__":
    collect()
    publish_to_docs()
    print("collect.py: gotowe. Uruchom evaluate.py, aby policzyć statusy i rekomendacje.")

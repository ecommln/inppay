# -*- coding: utf-8 -*-
"""Wspólne narzędzia dla kolektora, ewaluatora i alertów.

Cały pipeline (collect -> evaluate -> alert) korzysta z tych samych ścieżek,
progów i logiki statusów, żeby dashboard i e-mail mówiły dokładnie to samo.
"""
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

# Konsola Windows domyślnie cp1250 - wymuś UTF-8, żeby print() z polskimi
# znakami i emoji (np. w temacie alertu) nie wywalał skryptu.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# --- Ścieżki repo (wszystko względem katalogu głównego repo) ---
ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "config.json"
DATA_DIR = ROOT / "data"
HISTORY_DIR = DATA_DIR / "history"
LATEST_PATH = DATA_DIR / "latest.json"
DOCS_DATA_DIR = ROOT / "docs" / "data"
DOCS_ALERTS_DIR = ROOT / "docs" / "alerts"

# Metryki objęte alertami. INP jest bonusem (poza briefem) - liczymy status, ale bez alertu.
ALERT_METRICS = ["LCP", "CLS", "TTFB"]


def load_env():
    """Wczytuje zmienne z pliku .env w katalogu głównym repo do os.environ.

    Nie nadpisuje zmiennych już ustawionych w środowisku (np. GitHub Secrets
    mają pierwszeństwo). Nigdy nie wypisuje wartości - sekrety zostają sekretami.
    Format pliku: KEY=VALUE, jedna para na linię, '#' to komentarz.
    """
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value


# Wczytaj .env przy imporcie, żeby wszystkie skrypty miały dostęp do kluczy.
load_env()


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def metric_value(result, metric):
    """Wartość metryki wiersza: preferuj field (realni użytkownicy), fallback lab.
    Zwraca (wartość, źródło), gdzie źródło to 'field'/'lab', albo (None, None)."""
    field = result.get("field") or {}
    if metric in field and field[metric] is not None:
        return field[metric], "field"
    lab = result.get("lab") or {}
    if metric in lab and lab[metric] is not None:
        return lab[metric], "lab"
    return None, None


def classify_business(url, category, cfg):
    """Zwraca (funnel, tier, ads) dla URL wg core_overrides w configu.
    Blog -> zawsze funnel 'seo', tier 3. Nieopisana strona core -> 'support', tier 2.
    Używane i przez kolektor (zapis do wyniku), i przez ewaluator (uzupełnienie
    starszych przebiegów bez tych pól) - jedno źródło prawdy o biznesie."""
    if category == "blog":
        return "seo", 3, False
    path = urlparse(url).path or "/"
    o = cfg.get("core_overrides", {}).get(path, {})
    return o.get("funnel", "support"), int(o.get("tier", 2)), bool(o.get("ads", False))


def ensure_dirs():
    for d in (HISTORY_DIR, DOCS_DATA_DIR, DOCS_ALERTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def rate_status(metric, value, thresholds):
    """Zwraca 'good' / 'needs-improvement' / 'poor' wg progów Google.

    Wartości brzegowe: dokładnie na progu 'good' to już 'needs-improvement'
    (LCP=2500 -> needs-improvement), zgodnie z definicją Google.
    """
    if value is None:
        return None
    t = thresholds.get(metric)
    if not t:
        return None
    if value < t["good"]:
        return "good"
    if value <= t["poor"]:
        return "needs-improvement"
    return "poor"


def worst_status(statuses):
    order = {"good": 0, "needs-improvement": 1, "poor": 2}
    present = [s for s in statuses if s in order]
    if not present:
        return None
    return max(present, key=lambda s: order[s])


def write_json(path, data):
    """Zapis UTF-8 bez ucieczek unicode - polskie znaki zostają czytelne."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def publish_to_docs():
    """Kopiuje latest.json do docs/data i buduje history-index.json (lekki,
    tylko serie czasowe potrzebne do wykresu trendu) - żeby dashboard nie
    musiał pobierać dziesiątek plików historii."""
    ensure_dirs()
    if LATEST_PATH.exists():
        latest = read_json(LATEST_PATH)
        write_json(DOCS_DATA_DIR / "latest.json", latest)

    runs = sorted(HISTORY_DIR.glob("*.json"))
    index = {"runs": []}
    for run_path in runs:
        try:
            run = read_json(run_path)
        except Exception:
            continue
        series = []
        for r in run.get("results", []):
            src = r.get("field") or r.get("lab") or {}
            series.append({
                "url": r.get("url"),
                "label": r.get("label"),
                "strategy": r.get("strategy"),
                "LCP": src.get("LCP"),
                "CLS": src.get("CLS"),
                "TTFB": src.get("TTFB"),
                "INP": (r.get("field") or {}).get("INP"),
            })
        index["runs"].append({"timestamp": run.get("timestamp"), "series": series})
    write_json(DOCS_DATA_DIR / "history-index.json", index)

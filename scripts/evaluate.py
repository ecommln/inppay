# -*- coding: utf-8 -*-
"""Ocena pomiarów: statusy metryk + regresje, spina rekomendacje i podsumowanie.

Wejście:  data/latest.json (z collect.py lub seed_mock.py)
Wyjście:  wzbogacony data/latest.json + kopie do docs/data.

Logika biznesowa jest rozbita na moduły:
  * recommendations.py - lista działań dla deweloperów (z audytów Lighthouse),
  * summary.py         - podsumowanie dla zarządu (kondycja, werdykt, lejek konwersji).
Ten plik trzyma tylko statusy, regresje i orkiestrację.
"""
from datetime import datetime

from common import (
    load_config, read_json, write_json, publish_to_docs,
    LATEST_PATH, HISTORY_DIR, ALERT_METRICS,
    rate_status, worst_status, classify_business, metric_value,
)
from recommendations import build_recommendations
from summary import build_summary


def evaluate_statuses(results, thresholds):
    """Nadaje każdemu wierszowi status per metryka + 'overall' (najgorszy z LCP/CLS/TTFB)."""
    for r in results:
        status = {}
        for metric in ("LCP", "CLS", "TTFB", "INP"):
            val, _ = metric_value(r, metric)
            status[metric] = rate_status(metric, val, thresholds)
        status["overall"] = worst_status([status["LCP"], status["CLS"], status["TTFB"]])
        r["status"] = status
    return results


def _find_baseline_run(current_ts, lookback_days):
    """Znajdź przebieg najbliższy 'lookback_days' wstecz (fallback: poprzedni)."""
    runs = sorted(HISTORY_DIR.glob("*.json"))
    parsed = []
    for p in runs:
        try:
            run = read_json(p)
            ts = datetime.strptime(run["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
            parsed.append((ts, run))
        except Exception:
            continue
    if len(parsed) < 2:
        return None
    cur = datetime.strptime(current_ts, "%Y-%m-%dT%H:%M:%SZ")
    target = cur.timestamp() - lookback_days * 86400
    past = [(ts, run) for ts, run in parsed if ts.timestamp() < cur.timestamp() - 1]
    if not past:
        return None
    best = min(past, key=lambda x: abs(x[0].timestamp() - target))
    return best[1]


def build_regressions(current, thresholds, cfg):
    """Metryki, które pogorszyły się o >= min_delta_pct względem przebiegu bazowego.
    Liczone na danych field (realni użytkownicy); brak field -> pomijamy."""
    lookback = cfg.get("regressions", {}).get("lookback_days", 7)
    min_delta = cfg.get("regressions", {}).get("min_delta_pct", 10)
    baseline = _find_baseline_run(current["timestamp"], lookback)
    if not baseline:
        return []

    base_idx = {(r["url"], r["strategy"]): r for r in baseline["results"]}
    regressions = []
    for r in current["results"]:
        past = base_idx.get((r["url"], r["strategy"]))
        if not past:
            continue
        for metric in ALERT_METRICS:
            now_field = (r.get("field") or {}).get(metric)
            past_field = (past.get("field") or {}).get(metric)
            if now_field is None or past_field is None or past_field == 0:
                continue
            delta_pct = (now_field - past_field) / past_field * 100
            if delta_pct >= min_delta:  # wzrost wartości = pogorszenie
                regressions.append({
                    "url": r["url"],
                    "label": r["label"],
                    "strategy": r["strategy"],
                    "metric": metric,
                    "from": past_field,
                    "to": now_field,
                    "delta_pct": round(delta_pct, 1),
                    "crossed_threshold": (
                        rate_status(metric, now_field, thresholds) == "poor"
                        and rate_status(metric, past_field, thresholds) != "poor"
                    ),
                })
    regressions.sort(key=lambda x: x["delta_pct"], reverse=True)
    return regressions


def main():
    cfg = load_config()
    thresholds = cfg["thresholds"]
    latest = read_json(LATEST_PATH)

    results = evaluate_statuses(latest["results"], thresholds)
    # Uzupełnij pola biznesowe (funnel/tier/ads) - dla przebiegów zebranych przed
    # wprowadzeniem warstwy biznesowej; klasyfikacja z tego samego źródła co kolektor.
    for r in results:
        if not r.get("funnel"):
            f, t, ads = classify_business(r["url"], r.get("category", "core"), cfg)
            r["funnel"], r["tier"], r["ads"] = f, t, ads
    latest["results"] = results
    latest["recommendations"] = build_recommendations(results)
    latest["regressions"] = build_regressions(latest, thresholds, cfg)
    latest["summary"] = build_summary(results, cfg)
    latest["thresholds"] = thresholds

    write_json(LATEST_PATH, latest)
    publish_to_docs()

    s = latest["summary"]["mobile"]["counts"]
    print(f"evaluate.py: gotowe. Mobile - dobry:{s['good']} "
          f"uwaga:{s['needs-improvement']} słaby:{s['poor']}. "
          f"Rekomendacji: {len(latest['recommendations'])}, "
          f"regresji: {len(latest['regressions'])}.")


if __name__ == "__main__":
    main()

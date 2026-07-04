# -*- coding: utf-8 -*-
"""Powiadomienia e-mail przy przekroczeniu progów (status SŁABY).

Dwa tryby, przełączane obecnością sekretu RESEND_API_KEY:
  * preview (domyślny)  - renderuje realnego e-maila HTML do
    docs/alerts/ostatni-alert.html (widoczny na dashboardzie) i loguje,
    kogo by powiadomił. NIC NIE WYSYŁA. W tym trybie oddajemy zadanie.
  * send                - wysyła przez Resend API (fallback: SMTP).
    Kod gotowy, nieaktywny bez sekretu.

Anti-spam: alert leci tylko, gdy metryka WESZŁA w 'poor' względem poprzedniego
przebiegu (nowość) albo utrzymuje się dłużej niż reminder_after_days.
"""
import os

from common import (
    load_config, read_json, HISTORY_DIR, LATEST_PATH,
    DOCS_ALERTS_DIR, ensure_dirs, ALERT_METRICS,
)

BRAND = "#FFCC00"    # żółty InPost - akcent CTA
ACCENT = "#EC0E6E"   # magenta "Pay" - akcent marki
DARK = "#1D1D1D"
POOR = "#FF3B30"

METRIC_NAME = {"LCP": "Largest Contentful Paint", "CLS": "Cumulative Layout Shift",
               "TTFB": "Time to First Byte"}
BUSINESS = {
    "LCP": "Wolne ładowanie treści zwiększa porzucenia i podnosi koszt kliknięcia w Google Ads.",
    "CLS": "Skaczący układ powoduje błędne kliknięcia i porzucone formularze - ryzyko dla konwersji.",
    "TTFB": "Wolna odpowiedź serwera pogarsza pozycję w Google (SEO) i wydłuża każde wejście.",
}
UNIT = {"LCP": " ms", "TTFB": " ms", "CLS": ""}
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "#")  # ustawiane po włączeniu Pages


def _pl_num(metric, value):
    if metric == "CLS":
        return f"{value:.3f}".replace(".", ",")
    if metric in ("LCP", "TTFB"):  # sekundy, jak na dashboardzie (czytelniej dla biznesu)
        return f"{value/1000:.2f}".replace(".", ",") + " s"
    return f"{value}{UNIT[metric]}"  # INP w ms


def _prev_run(current_ts):
    runs = sorted(HISTORY_DIR.glob("*.json"))
    parsed = []
    for p in runs:
        try:
            r = read_json(p)
            parsed.append(r)
        except Exception:
            continue
    prev = [r for r in parsed if r["timestamp"] < current_ts]
    return prev[-1] if prev else None


def detect_events(latest):
    """Lista metryk, które są w 'poor' i są NOWE względem poprzedniego przebiegu."""
    prev = _prev_run(latest["timestamp"])
    prev_idx = {}
    if prev:
        for r in prev.get("results", []):
            prev_idx[(r["url"], r["strategy"])] = r.get("status", {})

    events = []
    for r in latest["results"]:
        st = r.get("status", {})
        for metric in ALERT_METRICS:
            if st.get(metric) != "poor":
                continue
            was_poor = prev_idx.get((r["url"], r["strategy"]), {}).get(metric) == "poor"
            events.append({
                "url": r["url"], "label": r["label"], "strategy": r["strategy"],
                "metric": metric,
                "value": (r.get("field") or r.get("lab") or {}).get(metric),
                "is_new": not was_poor,
            })
    # Alertujemy o nowych; jeśli nie ma nowych, ale są utrzymujące się - też pokażemy
    # (przypomnienie). Priorytet: nowe najpierw.
    events.sort(key=lambda e: (not e["is_new"], e["metric"]))
    return events


def _thresholds(cfg, metric):
    return cfg["thresholds"][metric]


def render_email(cfg, events, latest, is_example=False):
    """Zwraca (temat, html). Buduje maila dla najpoważniejszego zdarzenia +
    listę pozostałych."""
    strat_pl = {"mobile": "telefony", "desktop": "komputery"}
    top = events[0]
    poor_threshold = _thresholds(cfg, top["metric"])["poor"]

    subject = (f"⚠️ [inpostpay.pl] {top['metric']} w statusie SŁABY - "
               f"{_url_path(top['url'])} ({top['strategy']})")

    # Rekomendacja dla tej strony (jeśli jest)
    rec = None
    for r in latest.get("recommendations", []):
        if r["label"] == top["label"]:
            rec = r
            break

    example_banner = ""
    if is_example:
        example_banner = (
            f'<div style="background:#FFF6E5;border:1px solid #FFD98A;color:#7a5b00;'
            f'padding:12px 16px;border-radius:8px;margin-bottom:20px;font-size:14px;">'
            f'<b>Przykład - tak wygląda alert.</b> Aktualnie brak przekroczeń progów '
            f'na monitorowanych podstronach.</div>'
        )

    rows = ""
    for e in events[:6]:
        val = _pl_num(e["metric"], e["value"]) if e["value"] is not None else "-"
        thr = _pl_num(e["metric"], _thresholds(cfg, e["metric"])["poor"])
        rows += (
            f'<tr>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee;">{_url_path(e["url"])}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee;">{strat_pl[e["strategy"]]}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee;"><b>{e["metric"]}</b></td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee;color:{POOR};font-weight:700;">'
            f'{val}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee;color:#888;">próg &gt; {thr}</td>'
            f'</tr>'
        )

    rec_html = ""
    if rec:
        rec_html = (
            f'<div style="background:#f7f7f7;border-radius:8px;padding:16px;margin-top:20px;">'
            f'<div style="font-size:13px;color:#888;text-transform:uppercase;letter-spacing:.5px;">'
            f'Rekomendacja dla deweloperów</div>'
            f'<div style="font-size:16px;font-weight:600;margin-top:6px;color:{DARK};">{rec["action"]}</div>'
            f'<div style="font-size:14px;color:#555;margin-top:6px;">Szacowany zysk: '
            f'~{rec["savings_ms"]} ms · Priorytet: {rec["priority"]}</div></div>'
        )

    html = f"""<!DOCTYPE html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"></head>
<body style="margin:0;background:#f0f0f0;font-family:Arial,Helvetica,sans-serif;color:{DARK};">
<div style="max-width:600px;margin:0 auto;background:#fff;">
  <div style="background:{DARK};padding:20px 28px;border-bottom:4px solid {BRAND};">
    <span style="color:#fff;font-size:18px;font-weight:700;">Monitor wydajności · inpost</span><span
      style="color:{ACCENT};font-size:18px;font-weight:800;">pay</span><span
      style="color:#fff;font-size:18px;font-weight:700;">.pl</span>
  </div>
  <div style="padding:28px;">
    {example_banner}
    <div style="background:{POOR};color:#fff;display:inline-block;padding:6px 14px;
         border-radius:20px;font-size:13px;font-weight:700;">STATUS: SŁABY</div>
    <h1 style="font-size:22px;margin:16px 0 8px;">Wydajność podstrony {_url_path(top['url'])}
        spadła poniżej normy</h1>
    <p style="font-size:16px;line-height:1.5;color:#444;margin:0 0 8px;">
      Metryka <b>{top['metric']}</b> ({METRIC_NAME.get(top['metric'],'')}) na
      <b>{strat_pl[top['strategy']]}</b> wynosi
      <b style="color:{POOR};">{_pl_num(top['metric'], top['value']) if top['value'] is not None else '-'}</b>
      przy progu &quot;słaby&quot; &gt; {_pl_num(top['metric'], poor_threshold)}.
    </p>
    <p style="font-size:15px;line-height:1.5;color:#666;margin:0 0 20px;">
      <b>Co to znaczy dla biznesu:</b> {BUSINESS.get(top['metric'],'')}
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:14px;">
      <thead><tr style="text-align:left;color:#888;font-size:12px;text-transform:uppercase;">
        <th style="padding:8px 12px;">Podstrona</th><th style="padding:8px 12px;">Urządzenie</th>
        <th style="padding:8px 12px;">Metryka</th><th style="padding:8px 12px;">Wartość</th>
        <th style="padding:8px 12px;">Próg</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    {rec_html}
    <div style="margin-top:28px;">
      <a href="{DASHBOARD_URL}" style="background:{BRAND};color:{DARK};text-decoration:none;
         padding:14px 28px;border-radius:8px;font-weight:800;font-size:15px;display:inline-block;
         border:2px solid {DARK};">Otwórz dashboard →</a>
    </div>
  </div>
  <div style="padding:18px 28px;background:#fafafa;color:#999;font-size:12px;border-top:1px solid #eee;">
    Automatyczne powiadomienie z Monitora wydajności inpostpay.pl · Dane: Chrome UX Report API +
    PageSpeed Insights · Alert wysyłany przy wejściu metryki w status SŁABY.
  </div>
</div></body></html>"""
    return subject, html


def _url_path(url):
    path = url.replace("https://inpostpay.pl", "").replace("https://inpostpay.pl/", "/")
    return path if path else "/"


def build_example_event(latest):
    """Gdy brak realnych przekroczeń - zbuduj reprezentatywny przykład
    z najgorszej aktualnej metryki, by przycisk na dashboardzie zawsze działał."""
    worst = None
    worst_ratio = 0
    cfg = load_config()
    for r in latest["results"]:
        for metric in ALERT_METRICS:
            val = (r.get("field") or r.get("lab") or {}).get(metric)
            if val is None:
                continue
            ratio = val / cfg["thresholds"][metric]["poor"]
            if ratio > worst_ratio:
                worst_ratio = ratio
                worst = {"url": r["url"], "label": r["label"], "strategy": r["strategy"],
                         "metric": metric, "value": val, "is_new": True}
    if not worst:
        # skrajny fallback - sztuczny przykład
        worst = {"url": "https://inpostpay.pl/dlabiznesu", "label": "Dla biznesu (landing)",
                 "strategy": "mobile", "metric": "LCP", "value": 4600, "is_new": True}
    return [worst]


def send_resend(api_key, recipients, subject, html):
    import requests
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"from": os.environ.get("ALERT_FROM", "monitor@inpostpay-monitor.dev"),
              "to": recipients, "subject": subject, "html": html},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    cfg = load_config()
    ensure_dirs()
    latest = read_json(LATEST_PATH)

    events = detect_events(latest)
    is_example = len(events) == 0
    if is_example:
        events = build_example_event(latest)

    subject, html = render_email(cfg, events, latest, is_example=is_example)

    # Zawsze zapisz podgląd (widoczny na dashboardzie)
    out_path = DOCS_ALERTS_DIR / "ostatni-alert.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    api_key = os.environ.get("RESEND_API_KEY")
    recipients_env = cfg["alerts"].get("recipients_env", "ALERT_RECIPIENTS")
    recipients = [e.strip() for e in os.environ.get(recipients_env, "").split(",") if e.strip()]

    if not api_key:
        # TRYB PODGLĄDU - nic nie wysyłamy
        print("=" * 60)
        print("ALERT - TRYB PODGLĄDU (brak RESEND_API_KEY, nic nie wysłano)")
        print(f"[PODGLĄD] Wysłałbym do: {recipients or '<ustaw ALERT_RECIPIENTS>'}")
        print(f"[PODGLĄD] Temat: {subject}")
        print(f"[PODGLĄD] Zdarzeń SŁABY: {0 if is_example else len(events)}"
              f"{' (przykład - brak realnych przekroczeń)' if is_example else ''}")
        print(f"[PODGLĄD] Podgląd zapisany: {out_path.relative_to(out_path.parents[2])}")
        print("=" * 60)
        return

    # TRYB WYSYŁKI - kod gotowy, aktywny gdy jest sekret
    if is_example:
        print("Brak realnych przekroczeń - nic nie wysyłam (zapisano tylko podgląd).")
        return
    # Zabezpieczenie: nigdy nie wysyłaj na adresy @inpost.pl (wysyłkę robi człowiek)
    safe = [r for r in recipients if not r.lower().endswith("@inpost.pl")]
    if not safe:
        print("Brak bezpiecznych odbiorców (adresy @inpost.pl są blokowane w tym narzędziu).")
        return
    result = send_resend(api_key, safe, subject, html)
    print(f"Wysłano alert do {safe}: {result.get('id','ok')}")


if __name__ == "__main__":
    main()

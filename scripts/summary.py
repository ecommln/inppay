# -*- coding: utf-8 -*-
"""Podsumowanie dla zarządu (warstwa biznesowa).

Liczy per strategia (mobile/desktop): kondycję serwisu, werdykt ważony wartością
(lejek konwersji tier 1 najpierw), agregaty p50/p90, rozbicie na kategorie
(serwis/blog) i grupy funnel. Cała logika jest tu, a nie w dashboardzie, żeby
dało się ją testować i żeby e-mail alertu mówił to samo, co strona.
"""
import statistics

from common import metric_value


def _percentile(vals, q):
    """Percentyl q (0-100) z interpolacją liniową. Liczony w poprzek podstron."""
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    idx = (len(s) - 1) * q / 100.0
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def _plural_pl(n, one, few, many):
    """Polska odmiana liczebnika: 1 artykuł / 2-4 artykuły / 5+ artykułów."""
    n = abs(int(n))
    if n == 1:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _health(counts):
    """Krótki nagłówek + ludzki opis kondycji serwisu (język zarządu) na
    podstawie rozkładu statusów stron core. Bez żargonu, bez liczb 0-100."""
    g, ni, p = counts["good"], counts["needs-improvement"], counts["poor"]
    st = lambda n: _plural_pl(n, "strona", "strony", "stron")
    if p == 0 and ni == 0:
        return {"headline": "Serwis w pełni sprawny",
                "desc": "Wszystkie kluczowe strony działają w normie - bez działań."}
    if p == 0:
        return {"headline": "Prawie dobrze - kilka rzeczy do poprawy",
                "desc": (f"Większość serwisu działa sprawnie. {ni} {st(ni)} wymaga drobnych "
                         f"poprawek - zajmij się nimi w kolejności poniżej, zaczynając od góry.")}
    if p == 1:
        extra = f" i {ni} {st(ni)} do poprawy" if ni else ""
        return {"headline": "Prawie dobrze - jedna strona wymaga uwagi",
                "desc": (f"Większość serwisu działa sprawnie. Jest jednak jedna wyraźnie wolna "
                         f"strona{extra}. Zajmij się nimi w kolejności poniżej - zaczynając od góry.")}
    extra = f" i {ni} {st(ni)} do poprawy" if ni else ""
    return {"headline": f"{p} {st(p)} wymaga pilnej uwagi",
            "desc": (f"{p} kluczowych {st(p)} ładuje się zbyt wolno{extra}. To bezpośrednie "
                     f"ryzyko dla konwersji - zacznij od góry listy poniżej.")}


def _count_statuses(rows):
    counts = {"good": 0, "needs-improvement": 0, "poor": 0}
    for r in rows:
        ov = r.get("status", {}).get("overall")
        if ov in counts:
            counts[ov] += 1
    return counts


def _worst_label(rows):
    poor = [r for r in rows if r.get("status", {}).get("overall") == "poor"]
    return poor[0]["label"] if poor else None


def build_summary(results, cfg):
    """Podsumowanie per strategia + werdykt dla zarządu (język biznesu).

    Nagłówkowe statystyki liczymy na stronach serwisu ('core'). Dodatkowo
    wyodrębniamy LEJEK KONWERSJI (strony tier 1: pozyskanie sklepów B2B + wejście
    konsumenta/aplikacja) - werdykt i ryzyko liczymy przez pryzmat wartości
    biznesowej, nie samej liczby stron. Blog (SEO) raportujemy jako grupę."""
    business = cfg.get("business", {})
    conv_tiers = set(business.get("conversion_tiers", [1]))
    summary = {}
    for strategy in ("mobile", "desktop"):
        all_rows = [r for r in results if r["strategy"] == strategy]
        rows = [r for r in all_rows if r.get("category", "core") == "core"]
        blog_rows = [r for r in all_rows if r.get("category") == "blog"]
        if not rows:  # brak stron core (np. tryb fallback) - nie gubmy danych
            rows = all_rows
        counts = _count_statuses(rows)
        total = len(rows)

        # Rozbicie na kategorie - do segmentacji widoku (CMO: serwis vs blog).
        blog_lcp = [v for r in blog_rows for v in [metric_value(r, "LCP")[0]] if v is not None]
        by_category = {
            "core": {"counts": counts, "total": total},
            "blog": {
                "counts": _count_statuses(blog_rows), "total": len(blog_rows),
                "median_lcp": round(statistics.median(blog_lcp)) if blog_lcp else None,
            },
        }
        # Agregaty liczone W POPRZEK monitorowanych podstron:
        # p50 (mediana) = typowa podstrona, p90 = gorszy ogon (10% podstron wypada gorzej).
        medians, p90 = {}, {}
        for metric in ("LCP", "CLS", "TTFB", "INP", "score"):
            vals = []
            for r in rows:
                if metric == "score":
                    v = (r.get("lab") or {}).get("score")
                else:
                    v, _ = metric_value(r, metric)
                if v is not None:
                    vals.append(v)
            medians[metric] = round(statistics.median(vals), 3) if vals else None
            # score: gorszy ogon to NIŻSZY wynik, więc dla score bierzemy p10
            q = 10 if metric == "score" else 90
            p90[metric] = round(_percentile(vals, q), 3) if vals else None

        worst = None
        poor_rows = [r for r in rows if r.get("status", {}).get("overall") == "poor"]
        if poor_rows:
            worst = poor_rows[0]["label"]

        # Wpływ na SEO w języku biznesu
        if counts["poor"] == 0 and counts["needs-improvement"] <= 1:
            seo = "niski"
        elif counts["poor"] <= 2:
            seo = "średni"
        else:
            seo = "wysoki"

        ok = counts["good"]

        # --- LEJEK KONWERSJI (tier 1) - serce oceny biznesowej ---
        # To strony bezpośrednio pracujące na przychód: pozyskanie sklepów (B2B)
        # i wejście konsumenta / pobranie aplikacji. Ich stan waży więcej niż liczba.
        conv_rows = [r for r in rows if r.get("tier") in conv_tiers]
        conv_counts = _count_statuses(conv_rows)
        conv_total = len(conv_rows)
        conv_worst = _worst_label(conv_rows)

        # Grupy funnel (segmentacja widoku szczegółów): merchant / consumer / campaign / support
        by_funnel = {}
        for r in rows:
            f = r.get("funnel", "support")
            g = by_funnel.setdefault(f, {
                "counts": {"good": 0, "needs-improvement": 0, "poor": 0}, "total": 0, "ads": 0})
            ov = r.get("status", {}).get("overall")
            if ov in g["counts"]:
                g["counts"][ov] += 1
            g["total"] += 1
            if r.get("ads"):
                g["ads"] += 1

        # --- Werdykt: najpierw lejek konwersji, potem reszta serwisu, potem blog ---
        if conv_total == 0:
            verdict = ""
        elif conv_counts["poor"]:
            wt = f" (najsłabsza: {conv_worst})" if conv_worst else ""
            verdict = (f"Lejek konwersji: {conv_counts['poor']} z {conv_total} kluczowych stron "
                       f"ładuje się zbyt wolno{wt}. Bezpośrednie ryzyko dla pozyskania sklepów "
                       f"i pobrań aplikacji.")
        elif conv_counts["needs-improvement"]:
            verdict = (f"Lejek konwersji w większości sprawny - {conv_counts['needs-improvement']} "
                       f"z {conv_total} kluczowych stron do poprawy, zanim wpłynie na konwersję.")
        else:
            verdict = f"Lejek konwersji zdrowy - wszystkie {conv_total} kluczowe strony w normie."

        # Reszta serwisu (poza lejkiem) - jednym zdaniem, żeby nie gubić kontekstu.
        rest_poor = counts["poor"] - conv_counts["poor"]
        rest_ni = counts["needs-improvement"] - conv_counts["needs-improvement"]
        if rest_poor or rest_ni:
            verdict += (f" Pozostała część serwisu: {rest_poor} słabych, {rest_ni} do poprawy.")

        # Blog (szablon Drupala) - żeby werdykt obejmował cały serwis.
        bc = by_category["blog"]
        if bc["total"]:
            npoor = bc["counts"]["poor"]
            if npoor:
                slowo = _plural_pl(npoor, "artykuł", "artykuły", "artykułów")
                verdict += (f" Blog ({bc['total']} art.): {npoor} {slowo} ze słabym wynikiem "
                            f"- poprawka szablonu zadziała na wszystkie naraz.")
            else:
                verdict += f" Blog ({bc['total']} art.) monitorowany - bez problemów krytycznych."

        summary[strategy] = {
            "counts": counts,
            "total": total,
            "ok_pages": ok,
            "medians": medians,
            "p90": p90,
            "worst_page": worst,
            "seo_impact": seo,
            "action_needed": counts["poor"] + counts["needs-improvement"],
            "health": _health(counts),
            "by_category": by_category,
            "funnel": {
                "conversion": {"counts": conv_counts, "total": conv_total, "worst": conv_worst},
                "by_group": by_funnel,
            },
            "verdict": verdict,
        }
    return summary

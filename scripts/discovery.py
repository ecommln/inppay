# -*- coding: utf-8 -*-
"""Odkrywanie monitorowanych URL z sitemap.xml (zamiast ręcznej listy).

Buduje listę stron: czyta sitemap serwisu, klasyfikuje każdy URL na 'core'/'blog',
nadaje etykiety (curated z core_overrides albo wyprowadzone ze sluga), wagi oraz
pola biznesowe (funnel/tier/ads). Fallback: 'fallback_urls' z configu, gdy sitemap
niedostępny - narzędzie działa nawet bez sieci do sitemapy.
"""
import re
from urllib.parse import urlparse

import requests

from common import classify_business


def _prettify_slug(path, strip_prefix=""):
    """Zamienia slug URL na czytelną etykietę: '/aktualnosci-jak-placic' ->
    'Jak placic'. Bez polskich znaków (slug ich nie ma) - to i tak tylko
    etykieta pomocnicza dla artykułów bloga."""
    s = path.strip("/")
    if strip_prefix and s.startswith(strip_prefix):
        s = s[len(strip_prefix):]
    s = s.replace("-", " ").strip()
    if not s:
        return "Strona główna"
    label = s[:1].upper() + s[1:]
    return label if len(label) <= 75 else label[:72].rstrip() + "…"


def _fetch_sitemap_locs(sitemap_url):
    """Pobiera <loc> z sitemap.xml. Zwraca listę URL w kolejności z pliku."""
    resp = requests.get(sitemap_url, timeout=30)
    resp.raise_for_status()
    # Namespace-agnostycznie - prostym regexem, sitemapy bywają różnie sformatowane.
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", resp.text)


def discover_urls(cfg):
    """Buduje listę monitorowanych URL z sitemapy (jeśli discovery.enabled),
    inaczej z fallback_urls. Zwraca listę słowników: url/label/weight/category
    + funnel/tier/ads."""
    d = cfg.get("discovery", {})
    overrides = cfg.get("core_overrides", {})
    blog_prefix = d.get("blog_pattern", "aktualnosci-")
    exclude = set(d.get("exclude_paths", []))

    locs = []
    if d.get("enabled"):
        try:
            locs = _fetch_sitemap_locs(d["sitemap"])
            print(f"  sitemap: {len(locs)} URL z {d['sitemap']}")
        except Exception as e:
            print(f"  UWAGA: nie udało się pobrać sitemap ({e}) - używam fallback_urls z configu.")
            locs = []

    if not locs:
        items = []
        for entry in cfg.get("fallback_urls", []):
            path = urlparse(entry["url"]).path or "/"
            category = "blog" if blog_prefix in path else "core"
            funnel, tier, ads = classify_business(entry["url"], category, cfg)
            items.append({
                "url": entry["url"], "label": entry["label"],
                "weight": entry.get("weight", 2), "category": category,
                "funnel": funnel, "tier": tier, "ads": ads,
            })
        return items

    items = []
    for url in locs:
        path = urlparse(url).path or "/"
        if path in exclude:
            continue
        is_blog = blog_prefix in path
        if path in overrides:
            label = overrides[path]["label"]
            weight = overrides[path].get("weight", 2)
        elif is_blog:
            label = _prettify_slug(path, strip_prefix=blog_prefix)
            weight = 1
        else:
            label = _prettify_slug(path)
            weight = 2
        category = "blog" if is_blog else "core"
        funnel, tier, ads = classify_business(url, category, cfg)
        items.append({
            "url": url, "label": label, "weight": weight,
            "category": category, "funnel": funnel, "tier": tier, "ads": ads,
        })

    # Core najpierw (wg wagi malejąco), potem blog - żeby ważne strony poszły
    # jako pierwsze i żeby próbka lab dla bloga była deterministyczna.
    items.sort(key=lambda x: (x["category"] == "blog", -x["weight"], x["url"]))
    return items

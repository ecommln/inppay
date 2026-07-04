# Monitor wydajności inpostpay.pl

Narzędzie do stałego monitorowania **Core Web Vitals** serwisu inpostpay.pl
(LCP, CLS, TTFB + bonusowo INP), z podziałem na **mobile i desktop**. Pokazuje
statusy, trendy i **regresje**, tłumaczy każdą metrykę na język biznesu
(konwersja / SEO / UX), generuje **rekomendacje dla deweloperów** i wysyła
**alerty e-mail** przy przekroczeniu progów.

Zbudowane tak, by działało **bez serwera i bez kosztów**: GitHub Actions liczy,
repozytorium przechowuje dane, GitHub Pages serwuje dashboard.

- **Dashboard (żywy link):** _uzupełnij po włączeniu GitHub Pages_
- **Diagram procesu dla zarządu:** [`workflow-diagram/index.html`](workflow-diagram/index.html)
- **Opis decyzji (1 str.):** [`OPIS.md`](OPIS.md)

---

## Jak to działa (architektura)

```
GitHub Actions (cron 2×/dzień + ręcznie)
   │
   ├─ collect.py   → CrUX API (dane realnych użytkowników) + PSI API (Lighthouse)
   ├─ evaluate.py  → statusy wg progów Google, rekomendacje, regresje, podsumowanie
   ├─ alert.py     → e-mail przy statusie SŁABY (tryb podglądu / wysyłki)
   │
   ├─ data/            → historia pomiarów (baza danych = pliki JSON w repo)
   └─ docs/            → dashboard (GitHub Pages), czyta docs/data/*.json
```

**Źródła danych** (jeden klucz Google, dwa API):
- **CrUX API** - dane *field* (realni użytkownicy, p75 z 28 dni). Główne źródło statusów;
  to na tych danych Google opiera ranking. Braki (404 dla podstron o małym ruchu) →
  fallback na dane całej domeny → w ostateczności tylko dane lab.
- **PSI API (Lighthouse)** - dane *lab*, Performance Score i `opportunities`
  (surowiec rekomendacji dla deweloperów).

Progi Google (mobile i desktop osobno):

| Metryka | Dobry | Słaby |
|---|---|---|
| LCP  | < 2,5 s | > 4,0 s |
| CLS  | < 0,1   | > 0,25  |
| TTFB | < 0,8 s | > 1,8 s |
| INP (bonus) | < 200 ms | > 500 ms |

---

## Uruchomienie lokalne

Wymaga Pythona 3.11+. Zależności trzymamy w **wirtualnym środowisku** (`.venv`).

```bash
python -m venv .venv
# Windows:
.venv\Scripts\python -m pip install -r requirements.txt
# Linux/macOS:
.venv/bin/pip install -r requirements.txt
```

### Wariant A - realne dane (wymaga klucza Google)

```bash
# 1. Klucz z Google Cloud (patrz niżej), ustaw jako zmienną środowiskową:
#    PowerShell:  $env:GOOGLE_API_KEY = "twoj_klucz"
#    bash:        export GOOGLE_API_KEY=twoj_klucz
python scripts/collect.py     # pomiar CrUX + PSI dla wszystkich podstron
python scripts/evaluate.py    # statusy, rekomendacje, regresje
python scripts/alert.py       # render alertu (tryb podglądu bez RESEND_API_KEY)
```

### Wariant B - dane demonstracyjne (bez klucza)

```bash
python scripts/seed_mock.py   # generuje realistyczne dane przykładowe
python scripts/evaluate.py
python scripts/alert.py
```

### Podgląd dashboardu lokalnie

`fetch()` nie działa z `file://`, więc uruchom mały serwer:

```bash
cd docs
python -m http.server 8000
# otwórz http://localhost:8000
```

---

## Klucz Google API (jednorazowo)

1. Wejdź na <https://console.cloud.google.com/> → utwórz/wybierz projekt.
2. **APIs & Services → Enable APIs** → włącz **oba**:
   - *PageSpeed Insights API*
   - *Chrome UX Report API*
3. **APIs & Services → Credentials → Create credentials → API key**.
4. Skopiuj klucz. To jedyny sekret potrzebny, żeby narzędzie działało end-to-end.

---

## Wdrożenie (GitHub Actions + Pages)

1. Wrzuć repo na GitHub (publiczne - Actions i Pages są wtedy darmowe).
2. **Settings → Secrets and variables → Actions → New repository secret:**
   - `GOOGLE_API_KEY` - **wymagany**.
   - `RESEND_API_KEY` - *opcjonalny*; bez niego alerty działają w trybie podglądu (nic nie wysyłają).
   - `ALERT_RECIPIENTS` - *opcjonalny*; lista e-maili po przecinku (odbiorcy alertów).
3. **Settings → Variables → Actions:** `DASHBOARD_URL` = adres Pages (do linku w mailu).
4. **Settings → Pages:** źródło = branch `main`, katalog `/docs`.
5. **Actions → Monitor wydajności → Run workflow** - pierwszy przebieg ręcznie.
   Kolejne lecą automatycznie 2×/dzień.

---

## Utrzymanie przez zespół (bez programisty)

Wszystko konfiguruje się w [`config/config.json`](config/config.json):

- **Lista podstron jest automatyczna** - narzędzie czyta `sitemap.xml` serwisu przy każdym
  przebiegu (`discovery.enabled`), więc nowe strony dochodzą same. Ważnym stronom nadajesz
  czytelną etykietę i priorytet w `core_overrides` (`label`, `weight`); resztę narzędzie
  nazywa samo ze sluga.
- **Zasięg audytu Lighthouse** - `discovery.lab_scope`: `core_plus_sample` (domyślnie: strony
  serwisu + `blog_lab_sample` reprezentantów bloga + strony słabe) albo `all` (każdy URL, wolniej).
  Field (CrUX) i tak pokrywa cały serwis niezależnie od tego ustawienia.
- **Wyłączyć auto-discovery** - `discovery.enabled: false`; wtedy monitorowane są `fallback_urls`.
- **Zmienić progi** - sekcja `thresholds` (wartości w ms; CLS bez jednostki).
- **Dodać odbiorcę alertu** - dopisz e-mail do sekretu `ALERT_RECIPIENTS` (nie do kodu).
- **Częstotliwość pomiarów** - `cron` w `.github/workflows/monitor.yml`.

---

## Struktura repo

```
config/config.json          konfiguracja (URL-e, progi, alerty) - jedyne miejsce do edycji
scripts/collect.py          pomiar (CrUX + PSI, wielowątkowo)
scripts/discovery.py        odkrywanie URL z sitemap.xml + klasyfikacja
scripts/evaluate.py         statusy + regresje + orkiestracja
scripts/recommendations.py  lista działań dla deweloperów (z Lighthouse)
scripts/summary.py          podsumowanie dla zarządu (kondycja, werdykt, lejek)
scripts/alert.py            alerty e-mail (podgląd/wysyłka)
scripts/seed_mock.py        dane demonstracyjne (bez klucza)
scripts/common.py           wspólne narzędzia (ścieżki, progi, statusy, klasyfikacja)
data/                       historia pomiarów (JSON)
docs/index.html             dashboard - sam markup (GitHub Pages)
docs/assets/styles.css      style dashboardu (motyw jasny/ciemny)
docs/assets/js/             logika dashboardu w modułach ES:
                              dom.js     - helper $ (getElementById)
                              store.js   - współdzielony stan
                              format.js  - progi, etykiety, formatowanie
                              charts.js  - wspólny builder wykresów
                              overview.js- widok "Przegląd ogólny"
                              detail.js  - widok "Szczegóły per URL"
                              main.js     - wejście: dane + interakcje
docs/data/                  dane czytane przez dashboard
docs/alerts/                wyrenderowany podgląd alertu
workflow-diagram/           diagram procesu dla zarządu
.github/workflows/          automatyzacja (GitHub Actions)
```

## Bezpieczeństwo

- Sekrety (klucze) **nigdy w kodzie/commitach** - tylko GitHub Secrets / zmienne środowiskowe.
- `alert.py` z zasady **nie wysyła** na adresy `@inpost.pl` - finalną wysyłkę robi człowiek.
- Wszystkie pliki UTF-8; treści dla odbiorcy po polsku, z poprawną typografią (przecinek dziesiętny).

# Monitor wydajności inpostpay.pl - opis rozwiązania

## Co zbudowałem i dlaczego tak
Narzędzie stale mierzy Core Web Vitals wszystkich kluczowych podstron inpostpay.pl
(mobile i desktop), pokazuje statusy i trendy, wykrywa **regresje**, generuje
rekomendacje dla deweloperów i wysyła alerty przy przekroczeniu progów. Świadomie
wybrałem architekturę **bezserwerową i bezkosztową** (GitHub Actions + repozytorium
jako baza danych + GitHub Pages), bo w 100% pokrywa wymagania, daje trwały publiczny
link i historię pomiarów za darmo, bez ingerencji w kod serwisu. Narzędzie celowo mówi
do **trzech poziomów odbiorcy**: **zarząd** (Podsumowanie dla zarządu + diagram procesu -
język biznesu, zero żargonu), **marketing/PM** (statusy, filtry, trendy, regresje) i
**deweloperzy** (priorytetowa lista rekomendacji). To rola MarTech, gdzie liczy się
przełożenie techniki na decyzje biznesowe - dlatego każda metryka ma obok interpretację:
co znaczy dla **konwersji, SEO i UX**.

## Kluczowe decyzje
- **Pełne pokrycie serwisu z automatu.** Lista podstron nie jest wpisana na sztywno - narzędzie
  co przebieg czyta **`sitemap.xml`** inpostpay.pl (obecnie ~340 URL) i samo nadąża za nowymi
  stronami. Każdy URL klasyfikuję na **stronę serwisu** (produktowe/funkcyjne, ~17) lub
  **artykuł bloga** (~323, wspólny szablon).
- **Dwa źródła danych, rozdzielone rolą i pokryciem.** *Field* z **CrUX API** (realni
  użytkownicy, p75/28 dni) pobieram dla **wszystkich URL** - to daje pełne pokrycie serwisu
  statusami CWV i jest źródłem rankingowym Google (future-proof, bo Google wygasza CrUX w PSI).
  *Lab* z **PSI/Lighthouse** (Performance Score + `opportunities` = surowiec rekomendacji) jest
  wolny (~10-25 s/URL), a 323 artykuły bloga dzielą jeden szablon, więc audyt lab uruchamiam dla
  **wszystkich stron serwisu + reprezentantów szablonu bloga + każdego URL, który field oznaczył
  jako słaby**. To świadomy kompromis koszt/wartość (sterowany w `config.json`, tryb `all` włącza
  pełny audyt). Brak danych field dla URL → fallback na całą domenę (origin) → lab.
- **Segmentacja w widoku.** Dashboard rozdziela strony serwisu od bloga: zegar kondycji i kafle
  liczę na stronach serwisu (mają odrębny sygnał per URL), a blog raportuję jako grupę - bo
  poprawka jednego szablonu działa na wszystkie artykuły naraz.
- **Priorytet biznesowy zamiast płaskiej listy stron.** inpostpay.pl to lejek akwizycji
  (pozyskanie sklepów B2B + pobrania aplikacji + SEO z bloga), nie sklep transakcyjny. Dlatego
  każda strona ma przypisany **lejek** (merchant / consumer / campaign / support / seo) i **tier**.
  Dashboard wyróżnia **Lejek konwersji** (tier 1: strona główna, lejek B2B, „Zapłać za 30 dni") -
  jego stan waży w werdykcie i ryzyku bardziej niż liczba stron, bo to on pracuje na przychód.
  Landingi kampanii dostają znacznik **Ads** (wolny LCP = wyższy CPC w Google Ads). Klasyfikacja
  siedzi w `config.json` (`business` + `core_overrides`), więc zespół zmienia ją bez kodu.
- **Interpretacja biznesowa zamiast surowych liczb.** Nie mając dostępu do danych konwersji
  inpostpay.pl, zaczepiam ją o cytowalne zależności branżowe (wolne LCP → porzucenia; skoki
  CLS → porzucone formularze; wolny TTFB → wyższy CPC w Ads) i priorytetyzuję strony
  konwersyjne (waga ×2).
- **Regresje jako warstwa proaktywna** - „co się pogorszyło względem zeszłego tygodnia",
  by reagować **zanim** metryka wpadnie w status słaby.
- **Alerty świadomie w trybie podglądu.** System powiadomień jest w pełni zbudowany i
  przetestowany, a gotowy e-mail widać na dashboardzie („Podgląd przykładowego alertu").
  Nie podpinałem wysyłki pod skrzynkę, bo w zadaniu rekrutacyjnym nie generuję ruchu e-mail
  na cudzym adresie - **uruchomienie produkcyjne to jeden sekret (`RESEND_API_KEY`) + lista
  odbiorców, bez zmian w kodzie.**
- **Mobile-first** jako widok domyślny (Google indeksuje mobile-first); INP dorzucony jako
  bonus poza briefem; alerty tylko na zmianę stanu (anti-spam).

## Technologie
**CrUX API** i **PSI API** (dane), **Python + requests** (pipeline), **GitHub Actions**
(harmonogram i obliczenia - darmowe), **GitHub Pages** (dashboard - trwały publiczny link),
**Chart.js** (wykresy). Konfiguracja i utrzymanie przez `config.json` + README - zespół
dodaje podstronę, próg czy odbiorcę alertu bez programisty.

## Co rozwinąłbym przy większych zasobach
- **Przechowywanie danych.** Ta wersja to **MVP**: dane trzymam w plikach JSON w repozytorium,
  żeby szybko i bez kosztów pokazać założenia i działający link (przy okazji historia i backup
  za darmo w gicie). **Wersję produkcyjną budowałbym od startu na bazie danych** - plik jest
  tylko po to, by zademonstrować koncept. Baza jest potrzebna, gdy zaczynamy zbierać dane od
  realnych użytkowników i chcemy je swobodnie odpytywać oraz zarządzać retencją; wybór i
  wdrożenie tej warstwy to zadanie dla zespołu developerskiego.
- **Więcej odbiorców alertów** - powiadomienia na Slack/Teams obok e-maila.
- **Powiązanie z realną konwersją** - zestawienie wydajności z danymi z Google Analytics, żeby
  pokazywać wpływ na sprzedaż na twardych liczbach, a nie tylko regułach branżowych.
- **Monitoring konkurencji** - to samo narzędzie działa dla dowolnej domeny, więc łatwo dołożyć
  porównanie inpostpay.pl do konkurentów.
- **Kontrola przy wdrożeniach** - automatyczne sprawdzenie wydajności przed publikacją zmian,
  żeby nowy deploy nie pogorszył kluczowych stron.

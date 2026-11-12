# Tracking gryfu — zmiany 2026-09-15

Build: `artifacts/app-tracking-quality/motion_trace_win.exe`.

## Zakres

Silnik 0.6.0, tracker `shaft-lk-4`. Model `ai/models/shaft-v1.pt` pozostaje ten sam (SHA256 `cd930d56a2e2a63fcbed362d461a96a358200d6a3d9adafe247db982c3809e10`). Nie przeprowadzono nowego treningu. Hash kodu silnika uczestniczy w kluczu cache; należy ponownie uruchomić Analyze video w nowym buildzie.

- Przypisanie gryfu uwzględnia dłonie przy barkach w squacie i obie dłonie poniżej bioder w deadlifcie. Są to wskazówki przypisania osoby, nie etykiety z nowego klasyfikatora ćwiczeń.
- Widoczny leżący zawodnik wyklucza przypisanie stojącemu spotterowi na podstawie samych dłoni poniżej bioder. Kontekst jest utrzymywany maksymalnie 2 s po utracie tej wskazówki. Słabsze punkty tułowia mogą wykluczyć spottera, lecz nie wystarczają do przypisania mu lub zawodnikowi sztangi.
- Brak detekcji można podtrzymać do 150 ms tylko wtedy, gdy działa śledzenie obrazu LK. Brak świeżej detekcji obniża jakość; po przekroczeniu limitu tor jest urywany.
- Ponowne wykrycie bliskiego, zgodnie skierowanego fragmentu może zachować ID gryfu. Duże odległości, zmiany kąta i sprzeczne znane przypisania wykluczają połączenie.
- W C# bliskie niepokrywające się fragmenty mogą zachować ciągłość z jakością Reduced. Maksymalnie dwa kolejne niepewne przejścia; przerwy ponad 150 ms pozostają rozdzielone.
- Dla szybkiego ruchu statyczny limit przesunięcia ma dodatkową ścieżkę: mierzony ruch wspólnego fragmentu musi zgadzać się z kilkoma ostatnimi wiarygodnymi odczytami prędkości, kierunkiem i kątem. Prognoza tylko wybiera pasujące zmierzone przesunięcie; nie zastępuje brakujących klatek pozycjami przewidywanymi. Sprzeczne kandydatury przerywają tor.
- Zachowano wybór torów przez dominującego właściciela. Jedna błędna etykieta osoby w środku tego samego toru nie powinna usuwać repa. Tory przypisane dominująco innej osobie pozostają wykluczone.

## Odrzucony eksperyment

Przetestowano powtórną detekcję na wycinku ostatniego położenia gryfu. W IJSK5035 liczba klatek z wynikiem wzrosła z 110 do 307, ale inspekcja obrazów wykazała śledzenie elementu konstrukcji w tle podczas części podnoszenia. Zwiększona liczba wykryć nie oznaczała większej poprawności. Funkcja została usunięta z kodu aplikacji.

Źródło eksperymentu zachowano w `artifacts/tracking-roi-experiment-source`; przykłady w `artifacts/tracking-v3-production-roi/review-ijs.jpg`. Warianty `tracking-v2-production`, `tracking-v3-production-roi`, `tracking-v3-final-production` i `tracking-final-production` są pośrednimi eksperymentami, nie wynikami wydanej wersji.

## Weryfikacja

- Testy .NET: 109/109. Testy Python: 28/28. Publish WinUI Release x64: sukces.
- Testy regresji obejmują spottera przy bench, krótką utratę jego kontekstu, squat/deadlift, przerwę w detekcji, zmianę widocznego fragmentu, szybkie odkładanie z brakującą klatką oraz odrzucenie skoku, przeciwnego kierunku, innego kąta, właściciela i niejednoznacznych fragmentów.
- Porównanie zachowuje te same pozy, model gryfu i oryginalne timestampy 6 filmów. Ponownie wykonuje detekcję i tracking gryfu; pomiar faz korzysta z ręcznie podanego ćwiczenia. Nie jest to pomiar dokładności automatycznej klasyfikacji ćwiczenia ani m/s.
- Surowe wyniki wydanej wersji: `artifacts/tracking-release-production/`. Skrypt: `research/barbell/retrack_quality.py --output artifacts/<nowy-katalog>`. Skrypt nie nadpisuje istniejącego katalogu.

## Wynik porównania wydanej wersji

Porównanie względem `artifacts/phase-comparison-final/comparison.json` (ten sam model, wcześniejszy tracker) wykryło 8/10 oznaczonych repów wobec 7/10. Brak dodatkowych niedopasowanych repów na tej partii. Wyniki: `artifacts/tracking-release-comparison/comparison.json`.

| Film | Przed | Po |
|---|---:|---:|
| Bench 100kg x 5 | 5/5 | 5/5 |
| Bench VID_20260424_214030~2 | 1/1 | 1/1 |
| Squat IMG_0365 | 0/1 | 1/1 |
| Squat VID_20260420_175856~2 | 0/1 | 0/1 |
| Deadlift IJSK5035 | 0/1 | 0/1 |
| Deadlift VID_20260214_210811~2 (1) | 1/1 | 1/1 |

W bench błędy granic faz nie zmieniły się; analiza toru wybranego zawodnika 2 również zwraca odpowiednio 5 i 1 rep. Odzyskany squat ma błędy granic -0.067 / -0.033 / 0.000 / -0.033 s (początek/koniec opuszczania, początek/koniec podnoszenia), także po wyborze zawodnika 3.

Deadlift VID zachowuje błąd początku/końca podnoszenia -0.280/-0.200 s. Wcześniej brakowało fazy odkładania; teraz jest dostępna, ale z błędami +0.080 s początku i +0.881 s końca. Nie należy traktować odzyskania fazy jako potwierdzenia jej dokładności. Ten sam rep jest dostępny po wybraniu zawodnika 1.

To mały zbiór rozwojowy, nie niezależny test dokładności. Nie potwierdzono poprawności wszystkich przypisań osób ani fizycznej prędkości. Nie deklarujemy przyspieszenia analizy; zapisane czasy ponownego trackingu nie obejmują obliczania pozy.

## Pozostałe ograniczenia

Poprawa ciągłości nie usuwa błędów faz. Na kandydującym modelu z wcześniejszego treningu połączenie przerwy squatu około 43.17 s nie wystarczyło do odzyskania repa: dryf po lockoucie przesuwał punkt końcowy, a późniejsza przerwa kończyła niedomknięty ruch. W deadlifcie można odzyskać ciągłość odkładania, a nadal błędnie wyznaczyć jego koniec. Te przypadki wymagają dalszej walidacji faz i trajektorii.

Pozostają niejednoznaczności przy kilku sztangach/osobach, słabym kącie i zasłonięciach. Automatyczny klasyfikator ćwiczenia nadal obsługuje BenchPress / Unknown; pozostałe ćwiczenia wybiera się ręcznie. Niniejsza zmiana nie obiecuje pełnego rozpoznawania squat/deadlift.

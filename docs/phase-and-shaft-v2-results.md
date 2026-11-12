# Gryfy i fazy — wyniki pilotażu 2026-09-15

## Decyzja

Poprawki faz są w `artifacts/app-phase-quality-v2/motion_trace_win.exe`.
Kandydat detektora jest w `artifacts/shaft_multiexercise_v2_run2/candidate.pt`.
Model produkcyjny `ai/models/shaft-v1.pt` nie został zastąpiony: pełne nagrania nadal ujawniają przerwy trajektorii, których lepsze wyniki segmentacji nie usunęły.

## Dane i trening

- 300 wcześniejszych klatek bench + 102 klatki squat/deadlift; oryginalne eksporty użytkownika zachowane.
- Nowe oznaczenia: `research/barbell/squat_deadlift_annotations.json`. Zgodnie z decyzją użytkownika pojedynczy odcinek oznacza widoczny gryf, wiele odcinków częściowo zasłonięty. Poprawiono i zatwierdzono 39 takich rekordów w osobnej kopii.
- Fazy: `research/barbell/phase_annotations.json`, 10 repów na 6 filmach: 6 bench, 2 squat, 2 deadlift. Wszystkie 4199 klatek filmów przeszły przez porównanie silników.
- Fine-tuning istniejącego modelu: 12 epok, batch 6, AdamW LR 0.0001, seed 42; najlepsza walidacja w epoce 8.
- Trening: 310 klatek (226 bench / 69 squat / 15 deadlift). Walidacja: 68 (50 / 9 / 9). Test: 24 bench.
- Podział całymi filmami; dla nowych ćwiczeń źródła IMG w treningu, pozostałe w walidacji. To wstępne grupowanie, nie potwierdzony wizualnie podział sesji. Brak niezależnego testu squat/deadlift.
- Manifest podziału, hashe danych, historia epok i wyniki: `artifacts/shaft_multiexercise_v2_run2/`.

Wyniki segmentacji gryfu, F1 maski (0–1, nie procent poprawnie wykrytych repów):

| Zbiór | Poprzedni model | Kandydat |
|---|---:|---:|
| Bench walidacja | 0.8435 | 0.8555 |
| Squat walidacja | 0.1405 | 0.3700 |
| Deadlift walidacja | 0.6061 | 0.7494 |
| Bench test | 0.7968 | 0.8014 |

Nie wszystkie metryki wzrosły: precyzja z tolerancją 3 px na teście bench spadła z 0.9916 do 0.9799, a recall wzrósł z 0.9339 do 0.9508. Squat wciąż ma słaby wynik maski.

## Pełne filmy i fazy

Porównanie używa oryginalnych timestampów dekodera. Dla kandydata ponownie wykonano detekcję i tracking gryfu, zachowując te same wykryte pozy. Ćwiczenie podano z ręcznej etykiety; ten eksperyment nie mierzy automatycznej klasyfikacji ćwiczenia ani poprawności przypisania gryfu do zawodnika. Pomiar zbiorczy obejmuje gryf bez filtra zawodnika.

| Film | Stary model + stare fazy | Stary model + nowe fazy | Kandydat + nowe fazy |
|---|---:|---:|---:|
| Bench 100kg x 5 | 5/5 | 5/5 | 5/5 |
| Bench VID_20260424_214030~2 | 1/1 | 1/1 | 1/1 |
| Squat IMG_0365 | 0/1 | 0/1 | 0/1 |
| Squat VID_20260420_175856~2 | 0/1 | 0/1 | 1/1 |
| Deadlift IJSK5035 | 0/1 | 0/1 | 0/1 |
| Deadlift VID_20260214_210811~2 (1) | 1/1 | 1/1 | 1/1 |

Dopasowanie repów: IoU przedziału podnoszenia >= 0.2, bez wykorzystania etykiet do detekcji. Żaden wariant nie zwrócił dodatkowego niedopasowanego repa w tych sześciu filmach. Dopasowany rep nie oznacza kompletu poprawnych faz: deadlift VID nadal nie ma zmierzonego odkładania. Z 40 oznaczonych granic faz uzyskano 26 w wariancie poprzednim i po zmianie samych faz, a 30 z nowym modelem. Brakujące granice nie wchodzą do średnich błędów.

Średni bezwzględny błąd na 6 repach **bench**, w sekundach:

| Granica | Przed | Po |
|---|---:|---:|
| Początek opuszczania | 0.0278 | 0.0278 |
| Koniec opuszczania | 0.0445 | 0.0167 |
| Początek podnoszenia | 0.0726 | 0.0111 |
| Koniec podnoszenia | 0.0667 | 0.0667 |

Na deadlift VID błąd początku podnoszenia zmalał z 2.041 s do 0.280 s (w obu przypadkach za wcześnie). Nowy model ma błąd końca podnoszenia 0.160 s wobec 0.200 s poprzedniego modelu. Odzyskany squat VID ma błędy odpowiednio +0.068 / -0.034 / 0.000 / -0.101 s dla czterech granic.

To mała partia rozwojowa wykorzystana również do strojenia reguł. Nie jest niezależnym testem końcowym. Nie zmierzono dokładności fizycznej prędkości ani przyspieszenia analizy.

## Zmiany w aplikacji i kontrakt danych

- Powolne rozpoczęcie podnoszenia nie jest doliczane do pauzy na dole.
- Dolne ekstremum obejmuje rzeczywisty koniec opuszczania.
- Deadlift ma osobny detektor: podnoszenie, pauza na górze, odkładanie. Ruch przygotowawczy przy podłodze może zostać odcięty przez późniejszy stabilny spoczynek; spoczynek wysoko w torze nie może przesunąć początku.
- Odkładanie należy do poprzedniego podniesienia, nie do następnego repa. `MovementRep.Lowering` może wystąpić po `Lifting`; `LoweringFollowsLifting` rozróżnia kolejność. `Start`, `End`, `Duration` i indeksy klatek obejmują chronologiczny rep, z odkładaniem, jeżeli udało się je zakończyć pomiarem. Niekompletna faza pozostaje pusta.
- Wykres czasu pokazuje tę kolejność i separatory, filtr pauzy ma podpis "Top pause" dla deadliftu. ROM obejmuje samo podnoszenie.
- CSV próbek dodaje wartość fazy `top_pause`. CSV repów zachowuje dotychczasowe kolumny i dopisuje `top_pause_s,lifting_end_s`. `bottom_pause_s` pozostaje puste dla pauzy na górze. `end_s` oznacza koniec całego repa, nowa kolumna `lifting_end_s` jednoznacznie koniec podnoszenia.
- Jednostki prędkości nadal px/s; nie zadeklarowano pomiaru m/s bez skali.

## Pozostałe problemy i następna partia

W kandydacie squat IMG_0365 traci ciągłość około 43.13–43.17 s, w trakcie podnoszenia. Deadlift IJSK5035 dzieli tor podczas podnoszenia 6.2–8.73 s na kilka fragmentów. Deadlift VID traci ciągłość około 10.17–10.25 s podczas odkładania. Nie łączymy tych fragmentów w pomiar na siłę.

Następna partia powinna objąć gęstsze oznaczenia widocznych odcinków gryfu w tych konkretnych fragmentach oraz inne filmy o podobnych zasłonięciach i kątach kamery. Potrzebne są też niezależne filmy testowe squat/deadlift. Obecne przypisanie gryfu do osoby zawiera regułę specyficzną dla bench i wymaga oddzielnej oceny dla pozostałych ćwiczeń. Sam trening faz na 10 repach nie rozwiąże braków trajektorii.

## Weryfikacja i odtwarzanie

- `dotnet test tests/MotionTrace.Tests/MotionTrace.Tests.csproj --nologo`: 93/93.
- Publish WinUI Release x64 self-contained do `artifacts/app-phase-quality-v2`: sukces.
- Testy obejmują powolny start wyciskania, przygotowanie do deadliftu, przypisanie odkładania, kolejność faz na wykresie, ROM i eksport CSV.
- Nie potwierdzono wyglądu w działającym oknie: narzędzie automatyzacji Windows nie uruchomiło sesji dostępności.
- SHA256 produkcyjnego modelu pozostał `cd930d56a2e2a63fcbed362d461a96a358200d6a3d9adafe247db982c3809e10`.

Skrypty w `research/barbell/`: `train_multiexercise.py`, `run_phase_engines.py`, `retrack_phase_candidate.py`, `compare_phase_batch.py`. Trening używa nowego katalogu wynikowego i nie nadpisuje istniejącego. Ścieżkę OUT trzeba zmienić dla następnego uruchomienia.

Wyniki faz: `artifacts/phase-comparison-full-before/comparison.json`, `artifacts/phase-comparison-final/comparison.json`, `artifacts/phase-comparison-model-candidate/comparison.json`. `benchmark_phase_versions.py` chwilowo podmienia plik detektora na zachowaną wersję bazową i odtwarza bieżący plik w `finally`; nie uruchamiać równocześnie z edycją tego pliku lub innym buildem.

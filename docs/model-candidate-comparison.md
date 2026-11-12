# Kandydat wieloćwiczeniowy — 22.09.2026

Sprawdzono istniejący `artifacts/shaft_multiexercise_v2_run2/candidate.pt`
(SHA-256 `b2f2b03b299293e6abe09903ef03c3841725620453bfe937fa8a6f5ca3f406e6`).
Nie trenowano nowych wag i nie zmieniono modelu domyślnego aplikacji.
Sześć filmów przeliczono sekwencyjnie na GPU, z tymi samymi pozami i timestampami
co w [poprzednim porównaniu](model-comparison.md). Zachowany analizator C# ma
identyczne hashe źródeł jak poprzedni benchmark. Poniższe liczby izolują zmianę
wag detektora przed późniejszymi poprawkami ciągłości i reguł faz.

## Odnalezione oznaczone powtórzenia

| Film | Referencja | Wdrożony v1 | Kandydat v2 | DINO/SAM2 |
|---|---:|---:|---:|---:|
| bench / 100kg x 5 | 5 | 3 | 3 | 3 |
| bench / VID_20260424 | 1 | 0 | 0 | 1 |
| squat / IMG_0365 | 1 | 0 | 0 | 1 |
| squat / VID_20260420 | 1 | 0 | 1 | 0 |
| deadlift / IJSK5035 | 1 | 0 | 0 | 0 |
| deadlift / VID_20260214 | 1 | 1 | 1 | 1 |
| **Razem** | **10** | **4** | **5** | **6** |

Kandydat odzyskał oznaczony przysiad VID_20260420: średni bezwzględny błąd
czterech granic wyniósł 0,042 s; opuszczanie skrócone o 0,068 s, podnoszenie
o 0,101 s. W bench 100kg nadal brak repów 4–5, a błąd znalezionych granic
wynosi 0,044 s. W deadlift VID_20260214 błąd granic wynosi 0,570 s i opuszczanie
jest wydłużone o 2,001 s. Sam detektor nie naprawił więc segmentacji faz.

IJSK5035 ma jeden niedopasowany fragment podnoszenia 7,933–8,433 s.
Nie zaliczono go jako oznaczonego repa. Ponieważ etykiety nie są pełnym spisem
wszystkich ruchów, nie nazywamy automatycznie każdego niedopasowanego fragmentu
fałszywym powtórzeniem; wymaga sprawdzenia.

## Geometria widocznego gryfu

Pokrycie ręcznych odcinków w odległości do 2 pikseli formularza, z brakami jako
zerami; porównywalna metryka tylko między dwoma detektorami odcinków:

| Film | Klatki z odcinkiem v2 / oznaczone | Pokrycie v1 | Pokrycie v2 |
|---|---:|---:|---:|
| bench / 100kg x 5 | 11/12 | 81,8% | 79,6% |
| bench / VID_20260424 | 11/12 | 79,6% | 80,8% |
| squat / IMG_0365 | 3/3 | 15,8% | 59,3% |
| squat / VID_20260420 | 3/3 | 12,4% | 20,7% |
| deadlift / IJSK5035 | 3/3 | 0,0% | 17,7% |
| deadlift / VID_20260214 | 3/3 | 21,1% | 34,4% |

Poprawa odcinków squat/deadlift nie daje jeszcze ciągłego, poprawnie przypisanego
pomiaru: IMG_0365 ma tylko 30 próbek pomiarowych w wyniku analizatora mimo
detekcji w trzech oznaczonych klatkach. To argument za diagnostyką przypisania
i przerw, a nie za automatyczną zamianą modelu na podstawie klatek.

## Czas i ograniczenia

Czas kandydata obejmuje inicjalizację, dekodowanie, detekcję, śledzenie i przypisanie;
nie obejmuje obliczenia pozy. Kolejno jak w tabeli: **18,0; 18,8; 65,5; 30,7;
12,0; 10,6 s**, razem **155,6 s**. Poprzednie v1: 131,8 s, DINO/SAM2/X-CLIP:
795,8 s. To pojedyncze pomiary z różnych dni, nie wielokrotny test wydajności;
obecny backend dodatkowo segmentuje maski i klasyfikuje ćwiczenie.

- Oba bench i squat IMG_0365 należą do treningu kandydata; pozostały squat i
  oba deadlifty do walidacji rozwojowej. Żaden z sześciu filmów nie jest tu
  niezależnym końcowym testem. Bench występował też w treningu bazowego v1.
- Kandydat wykrywa gryf, nie klasyfikuje ćwiczeń. Wszystkim wariantom ustawiono
  poprawne ćwiczenie ręcznie, aby porównywać tor i fazy na równych warunkach.
- Tylko trzy anotowane klatki na każdy squat/deadlift to mała próba geometrii.
  Pokrycie odcinka nie jest precyzją detekcji ani pomiarem błędu prędkości w m/s.
- MAE granic liczy tylko znalezione repy; brakujące pozostają w mianowniku
  liczby powtórzeń. Etykiety faz były wcześniej używane do strojenia reguł.

**Wniosek:** kandydat poprawia widoczny gryf poza bench i odzyskuje jeden
przysiad, lecz same nowe wagi nie usuwają głównych braków powtórzeń. Należy
kontynuować poprawę ciągłości/przypisania i porównać ją na tych samych zapisanych
wynikach. Nie ma podstaw do bezwarunkowej zamiany domyślnego backendu.

## Artefakty

`artifacts/model-candidate-comparison/report.json` zawiera komplet metryk,
proweniencję i hash poprzedniego raportu; `custom-runs.json` zapisuje komendy
i czas procesów. `baseline-probe` przechowuje analizator użyty w porównaniu.
Powtórne GPU uruchomienie wymaga nowego katalogu wyjściowego, ponieważ skrypt
celowo odmawia nadpisania istniejących wyników:

```powershell
& "$env:USERPROFILE/miniconda3/envs/motiontrace/python.exe" research/vision/run_custom_comparison.py `
  --output artifacts/model-candidate-comparison-rerun `
  --weights artifacts/shaft_multiexercise_v2_run2/candidate.pt
```

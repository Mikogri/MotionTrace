# Porównanie modeli z ręcznymi oznaczeniami

Badanie rozdziela **wykrycie gryfu, śledzenie, klasyfikację ćwiczenia i pomiary
faz**. Dobry wynik jednego etapu nie dowodzi poprawności pozostałych.

## Co jest porównywane

- Nowy backend: Grounding DINO Tiny + SAM2.1 Hiera Small + X-CLIP.
  Automatyczny punkt pomiaru pochodzi z maski i jest oznaczony jako proxy.
- Własny wdrożony model: `ai/models/shaft-v1.pt`, taki sam jak
  `artifacts/shaft_model/best.pt`; SHA-256
  `cd930d56a2e2a63fcbed362d461a96a358200d6a3d9adafe247db982c3809e10`.
  Uczył się widocznych odcinków gryfu na bench press. Śledzenie korzysta z
  aktualnych `FocusedShaftDetector`, `MultiShaftTracker` i `ShaftOwnership`.
  Sam ten model nie klasyfikuje ćwiczenia.
- Eksperymentalny `shaft_multiexercise_v2_run2/candidate.pt` ma inny hash
  (`b2f2b03b299293e6abe09903ef03c3841725620453bfe937fa8a6f5ca3f406e6`).
  Nie jest wdrożonym `shaft-v1.pt` i nie jest tu potajemnie podstawiany.

Nowe uruchomienia obu backendów wykorzystują te same istniejące wyniki pozy i
te same timestampy oryginalnego filmu. Nie porównujemy efektu różnych modeli
pozy. `replay_custom.py` sprawdza zgodność czasów każdej klatki i zapisuje hash
wag, filmu, wejścia pose i źródeł algorytmu. Wyniki uruchomień są zachowane
osobno; nie zmieniamy domyślnego modelu aplikacji.

## Referencje i ograniczenia

- `research/barbell/phase_annotations.json`: sześć ręcznie sprawdzonych nagrań,
  dziesięć oznaczonych powtórzeń; bench 6, squat 2, deadlift 2.
- `training_annotations.json` oraz `squat_deadlift_annotations.json`: widoczne
  odcinki gryfu. To nie są maski obiektu ani etykiety stałego punktu fizycznego.
- Oba filmy bench (`100kg x 5.mp4`, `VID_20260424_214030~2.mp4`) są częścią
  **treningu** wdrożonego detektora. Ich wyniki są testem regresji,
  a nie niezależnym potwierdzeniem generalizacji.
- Filmy squat/deadlift nie były w zbiorze treningowym, walidacyjnym ani testowym
  wdrożonego `shaft-v1.pt`. Część była użyta dopiero w odrębnym eksperymencie
  multiexercise. Status każdego filmu raportowany jest z oryginalnego splitu.
- Granice faz były wcześniej używane do strojenia reguł. Cały benchmark faz
  jest więc **zbiorem rozwojowym**, nie nowym, niezależnym testem.
- Adnotacje faz nie są pełnym spisem wszystkich ruchów w nagraniu. W szczególności
  `VID_20260420_175856~2.mp4` zawiera drugi przysiad bez etykiety. Dodatkowy rep
  poza etykietami wymaga inspekcji; nie nazywamy go automatycznie fałszywym.

## Metoda pomiaru

Oba wyniki przechodzą aktualny, wspólny analizator C# aplikacji przez
`AnalysisProbe`. Dla porównania trajektorii i faz **obu backendom ustawiamy
właściwe ćwiczenie ręcznie**. To warunkowy pomiar jakości faz, a nie dowód
działania automatycznej klasyfikacji. Predykcje nowego modelu przechowujemy
osobno w raporcie, włącznie z Unknown.

Powtórzenia dopasowujemy jeden do jednego, od największego nakładania przedziału
podnoszenia (IoU co najmniej 0,2). Raport zawiera liczbę znalezionych, brakujących
i niedopasowanych repów, błędy każdej dostępnej granicy oraz błędy czasu opuszczania
i podnoszenia. **MAE dotyczy tylko dopasowanych granic**; obok podawana jest liczba
dopasowanych repów, aby brak detekcji nie udawał wysokiej dokładności.

Dla sztangi:

- Własny detektor: odsetek punktów ręcznie narysowanej linii znajdujących się
  w odległości do dwóch pikseli obrazu anotacji od wykrytych odcinków.
- SAM2: ścisłe pokrycie ręcznie narysowanej linii maską oraz osobno pokrycie
  z tolerancją dwóch pikseli obrazu anotacji.
- Brak detekcji/maski liczy się jako zerowe pokrycie; raport podaje też liczbę
  klatek z dostępnym wynikiem. Anotacje są przeliczane z rozmiaru formularza do
  oryginalnego, obróconego obrazu i dopasowane czasowo.

To **różne metryki geometrii**, których nie wolno nazywać procentową dokładnością
modeli. Zbyt duża, błędna maska może nadal pokrywać całą linię. Nie ma referencji
prędkości w m/s, kalibracji ani stałego punktu osi, więc nie wyliczamy błędu m/s.

## Wyniki rzeczywistych uruchomień — 18.09.2026

Wykonano od nowa wszystkie sześć nagrań dla obu backendów, sekwencyjnie na tym
samym GPU. To wyniki aktualnego trackingu, nie starszych snapshotów.

| Film | Ręczne repy | Własny model: dopasowane / MAE granic | DINO/SAM2: dopasowane / MAE granic |
|---|---:|---:|---:|
| bench / 100kg x 5.mp4 | 5 | 3 / 0,033 s | 3 / 0,033 s |
| bench / VID_20260424_214030~2.mp4 | 1 | 0 / — | 1 / 0,076 s |
| squat / IMG_0365.MOV | 1 | 0 / — | 1 / 0,083 s |
| squat / VID_20260420_175856~2.mp4 | 1 | 0 / — | 0 / — |
| deadlift / IJSK5035.MP4 | 1 | 0 / — | 0 / — |
| deadlift / VID_20260214_210811~2 (1).mp4 | 1 | 1 / 0,600 s | 1 / 0,350 s |

Łącznie własny model dopasował **4/10** oznaczonych repów, a nowy **6/10**.
Nie było dodatkowych niedopasowanych detekcji w tych przebiegach. Nie oznacza to
zerowego odsetka fałszywych repów we wszystkich warunkach ani pełnego pokrycia
nieoznaczonych fragmentów. W bench oba backendy nadal pomijają repy 4–5.

Średni błąd dopasowanych granic wynosił 0,175 s dla własnego modelu
(16 z 40 granic) oraz 0,102 s dla nowego (24 z 40). **Nie porównujemy tych średnich
bez liczby braków**: powstały na różnych podzbiorach znalezionych powtórzeń.
Na wspólnym deadlifcie własny model wydłużył opuszczanie o 2,001 s, nowy o 0,881 s.
Nowy model w drugim bench wydłużył podnoszenie o 0,270 s, a w IMG_0365 skrócił
opuszczanie o 0,300 s. Raport JSON zawiera wszystkie różnice, także pauzę i czas
całego repa. Początek preparation nie jest wliczany do tych czterech granic.

Automatyczny X-CLIP wraz z weryfikacją właściciela podał oczekiwaną nazwę ćwiczenia
w obu filmach bench i obu squat. **Oba deadlifty pozostały Unknown.** To 4/6 filmów
z odpowiednią klasą i dwie abstencje, nie ocena identyfikacji wszystkich osób.
Powyższe fazy deadlift uzyskano dopiero z ręcznym wyborem ćwiczenia.

### Widoczność i geometria gryfu

| Film (kolejność jak wyżej) | Anotowane klatki | Własny: klatki z odcinkiem / pokrycie do 2 px formularza | SAM2: klatki z maską / ścisłe pokrycie linii |
|---|---:|---:|---:|
| 100kg x 5 | 12 | 12 / 81,8% | 7 / 45,1% |
| bench VID_20260424 | 12 | 12 / 79,6% | 9 / 72,5% |
| squat IMG_0365 | 3 | 2 / 15,8% | 0 / 0,0% |
| squat VID_20260420 | 3 | 2 / 12,4% | 0 / 0,0% |
| deadlift IJSK5035 | 3 | 1 / 0,0% | 0 / 0,0% |
| deadlift VID_20260214 | 3 | 3 / 21,1% | 2 / 39,9% |

Pokrycie liczone jest długością narysowanych odcinków, z brakami jako zerami.
Jedna maska ani odcinek nie gwarantują poprawnego właściciela. Obecność jednego
repa w IMG_0365 przy zerowym pokryciu trzech anotowanych klatek pokazuje, dlaczego
wynik faz nie wystarcza do uznania śledzenia gryfu za dobre. Trzy klatki na film
squat/deadlift to bardzo mała próba geometrii.

### Czas analizy przy gotowych, wspólnych pozach

| Film (kolejność jak wyżej) | Własny model + tracking | Etap DINO/SAM2/X-CLIP |
|---|---:|---:|
| 100kg x 5 | 15,7 s | 167,1 s |
| bench VID_20260424 | 17,3 s | 136,0 s |
| squat IMG_0365 | 60,4 s | 206,9 s |
| squat VID_20260420 | 18,3 s | 183,0 s |
| deadlift IJSK5035 | 10,6 s | 26,7 s |
| deadlift VID_20260214 | 9,5 s | 76,1 s |
| Razem | 131,8 s | 795,8 s |

To czas wewnętrzny etapów po uzyskaniu pose, **nie pełny czas analizy aplikacji**.
Własny etap mierzy inicjalizację modelu, dekodowanie, wykrywanie, śledzenie i
przypisanie; nowy dodatkowo segmentuje maski i klasyfikuje ćwiczenia. Własny jest
w tej próbie około sześciokrotnie szybszy, ale ma mniejsze pokrycie repów. Czasy
procesów, hashe i dokładne komendy zachowano w `custom-runs.json`, `runs.json`
i `runs-extra.json`. Nie porównujemy ich z wcześniejszymi uruchomieniami o innych
ustawieniach jako testu wydajności tego samego algorytmu.

**Wniosek:** aktualny ogólny backend odnalazł więcej oznaczonych powtórzeń, lecz
nie rozwiązał jakości pomiaru gryfu i jest znacznie droższy obliczeniowo. Własny
detektor ma dobre pokrycie widocznych odcinków w dwóch filmach bench, które znał
z treningu, ale nie daje wiarygodnego śledzenia squat/deadlift. Nie ma podstaw
do automatycznej zamiany modelu na starszy ani do deklarowania dokładnej prędkości.
Najbardziej uzasadniona dalsza praca to rozwój szybkiego detektora samego gryfu
na nowych, zróżnicowanych nagraniach squat/deadlift i odzyskiwanie ciągłości
pomiaru/przypisania; ocenę należy powtórzyć na nowych filmach z pełnymi etykietami.

## Powtarzalność

Skrypty nie trenują modeli i nie zmieniają konfiguracji aplikacji:

```powershell
# Uruchamiaj modele sekwencyjnie, żeby nie konkurowały o GPU.
& "$env:USERPROFILE/miniconda3/envs/motiontrace/python.exe" research/vision/replay_custom.py `
  --input "videos/bench/100kg x 5.mp4" `
  --pose-input artifacts/vision-validation/bench-final.json `
  --output artifacts/model-comparison/bench-custom.json

& "$env:USERPROFILE/miniconda3/envs/motiontrace-vision/python.exe" research/vision/compare_backends.py
```

`compare_backends.py` wyłącznie ocenia zapisane wyniki na CPU. Buduje wspólny
analizator C# i pracuje na kopiach wejść. Pełne wyniki: `artifacts/model-comparison/report.json`.
Starszy punkt odniesienia ma osobny plik `snapshots/snapshot-report.json` i nie
jest przedstawiany jako bieżące uruchomienie.

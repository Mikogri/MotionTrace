# TAPNext++ i BootsTAPIR — integracja PyTorch

## Wersje i instalacja

`scripts/setup-tap-trackers.ps1` instaluje osobne środowisko
`C:/Users/Mikolaj/miniconda3/envs/motiontrace-points/python.exe`.
Nie modyfikuje MMPose ani `motiontrace-vision`. Na tej maszynie środowisko
początkowo sklonowano z vision; nowe zależności dodano tylko do kopii.
Skrypt potrafi także utworzyć czyste środowisko Python 3.11.16.

- Kod: oficjalny `google-deepmind/tapnet`, rewizja
  `730cda1c730877cfedbe01bf87fb1cadb78a565d`.
- Wagi: oficjalne `google/tapnet`, rewizja
  `5d3fb48e76c5422841e38501514121e251beabb7`.
- TAPNext++: `tapnextpp_ckpt.pt`, 256×256, tryb online z zachowaną pamięcią
  rekurencyjną; SHA256
  `cb96a43444ccb4fbdb25d800b88c7ba196179a526e78f01b021a16b1c1eff6da`.
- BootsTAPIR: `bootstapir_checkpoint_v2.pt`, offline, 256×256,
  `TAPIR(pyramid_level=1, use_casual_conv=False)`; SHA256
  `8493c7a69e02c85b9382fbb3c7b8b539b36bc08ede744b9e99feb739a0129f4b`.
  Jest to ustawienie 256 z oficjalnego notebooka PyTorch, nie wariant causal
  ani automatyczne obniżanie rozdzielczości przy OOM.
- Torch 2.8.0+cu126, torchvision 0.23.0+cu126. Wszystkie zależności używanego
  podzbioru PyTorch są przypięte w `ai/comparison/requirements-points.txt`.
- Kod i wagi: Apache-2.0. LICENSE, przypięta karta modelu, kopie dostępnych
  licencji zależności oraz ich metadane pozostają w `.models/points`.
  PyAV ma zależności multimedialne opisane w licencjach dołączonych do wheel.

Źródła: <https://github.com/google-deepmind/tapnet>,
<https://huggingface.co/google/tapnet>,
`colabs/torch_tapir_demo.ipynb`, `tapnet/tapnextpp/votsp2026/model.py`
i `utils.py` z przypiętej rewizji. Nie instalujemy JAX ani wersji CUDA dla JAX.

Analiza nie pobiera żadnych plików. Weryfikuje sumy checkpointu i plików źródła.
Błąd integralności kończy zadanie; nie ma fallbacku do innego trackera.

## Kontrakt

```powershell
& C:/Users/Mikolaj/miniconda3/envs/motiontrace-points/python.exe `
  ai/comparison/tap_backends.py --provider tapnextpp `
  --input 'videos/bench/100kg x 5.mp4' `
  --pose-input artifacts/model-switch-repair/bench-production.json `
  --target artifacts/four-trackers/bench-target.json `
  --output artifacts/four-trackers/tapnextpp-bench.json `
  --models-root .models/points --device cuda:0
```

BootsTAPIR używa `--provider bootstapir`. Cel zawiera `targetId`,
`athleteTrackId`, `frameIndex`, `timestampSeconds`, `point{x,y}`, `box` i
kalibrację. Punkt jest fizyczną osią widocznego końca/piasty, nie środkiem
bboxa ani logo talerza. Współrzędne wejścia i wyniku są w pikselach oryginału.
Każdy adapter weryfikuje indeks klatki i timestamp względem wspólnego pose.

PyAV dekoduje wszystkie klatki prezentacyjne, z obsługą obrotu i MOV edit lists.
Każdy PTS jest porównywany z pose. Inny rozmiar, dodatkowe/brakujące klatki
lub rozbieżny PTS kończą zadanie błędem. Nie ma sztucznego dopisywania klatek.
Przed klatką zapytania zapisane są puste obserwacje, a nie punkt zero.

TAPNext++ używa oficjalnego preprocessingu BGR→RGB, resize 256, [-1,1],
query `[t,y,x]`. Wyjściowe `[y,x]` jest odwracane do `[x,y]` i skalowane do
oryginału. Kod wykonuje te same operacje co oficjalny wrapper, lecz zachowuje
także logity widoczności odrzucane przez jego wygodną metodę `track_frame`.

BootsTAPIR używa RGB/[-1,1], query `[t,y,x]`, tracks `[x,y]`. CNN jest
wykonywany po jednej klatce do prealokowanych tensorów cech. Następnie jeden
pełny offline refinement dostaje całą sekwencję — nie ma restartów na
granicach paczek. Nie trzymamy pełnego filmu 4K ani kopii obrazu wszystkich
klatek na GPU. Cechy offline nadal rosną liniowo z długością nagrania;
OOM pozostaje jawnym błędem bez zmiany FPS/modelu/rozdzielczości.

Wynik schema4 zachowuje wspólne pose/timestampy. `shafts=[]`, obiekty mają
`box=null`, `maskPath=null` i rzeczywisty punkt. Predykcje pod zasłonięciem
pozostają wyłącznie w `rawObservation`; `measurement=null`. Modelowe
prawdopodobieństwo widoczności nie jest porównywalną między modelami oceną
dokładności pomiaru. Pomiar obserwowany ma konserwatywną jakość `Reduced`.
Wynik zawiera tryb, preprocesing, rewizje, checkpoint, query frame,
czas i szczyt alokacji GPU. JSON jest zapisywany atomowo.

## Rzeczywisty test 22.09.2026

RTX 3070 Ti, 8 GB; modele uruchomione kolejno. `100kg x 5.mp4`, 565 klatek,
2160×3840, 30 FPS, pięć powtórzeń i spotter. Wspólny pose athlete2;
manualnie wskazana oś bliskiej piasty `(613,1576)` w klatce0/t0.

| Model | Czas adaptera z ładowaniem | Peak GPU allocated | Obserwacje |
|---|---:|---:|---:|
| TAPNext++ 256 | 60.656 s | 1,702,895,104 B | 565/565 |
| BootsTAPIR v2 offline 256 | 13.585 s | 2,216,826,880 B | 565/565 |

To pomiar `torch.cuda.max_memory_allocated`, nie całej pamięci procesu/Windows.
Nie obejmuje współdzielonego pose ani późniejszej analityki C#.
Próbki wizualne 0/5/10/15s w `artifacts/four-trackers/hub-point-review.jpg`
utrzymują oba punkty w okolicy piasty. Nie jest to ilościowa walidacja
dokładności na niezależnie oznaczonym zbiorze.

Wstępna próba z bardzo małym końcem tulei `(208,1513)` pokazała dryf TAPNext++
i pozostanie BootsTAPIR na tle. Zachowano te wyniki pod `*-sleeve-end.json`.
Nie ma automatycznej zamiany celu w produkcie. Jakość inicjalizacji ma znaczenie;
widoczny środek osi przy piaście jest na tym filmie stabilniejszy.

Sześć testów kontraktu: query o niezerowym czasie/VFR, błędny punkt/id,
brak fikcyjnego boxa/maski, zasłonięcie bez pomiaru, wyjście poza obraz,
brakujące klatki i błędne PTS. Wszystkie przeszły w `motiontrace-points`.
Testy prawdziwych modeli używały lokalnych wag, bez wywołań API/pobierania.

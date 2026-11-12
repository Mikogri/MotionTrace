# Integracja lokalnych modeli Vision — 2026-09-18

Nowe modele są zainstalowane, a aplikacja używa `ai/pipeline.py` i providera
`grounding_dino_sam2`. To integracja ogólnych modeli wideo, **nie potwierdzenie
lepszej dokładności pomiaru niż dotychczasowy model**. W trakcie rzeczywistych
testów znaleziono błędne przypisanie sztangi asekurantowi i niedokładne maski.
Przypisanie wzmocniono zgodnością ruchu; ograniczenia segmentacji pozostają.

## Instalacja i uruchomienie

- Zachowane środowisko: `C:/Users/Mikolaj/miniconda3/envs/motiontrace/python.exe`,
  Python 3.10.21, torch 2.1.0+cu121, torchvision 0.16.0+cu121, NumPy 1.26.4,
  OpenCV 4.11.0.86, MMCV 2.1.0, MMEngine 0.10.7, MMPose 1.3.2, MMDetection 3.2.0.
- Nowe środowisko: `C:/Users/Mikolaj/miniconda3/envs/motiontrace-vision/python.exe`,
  Python 3.11.16, torch 2.8.0+cu126, torchvision 0.23.0+cu126,
  Transformers 4.57.6, NumPy 1.26.4, OpenCV 4.11.0.86, PyAV 16.0.1.
  Pełny lock: `ai/requirements-vision-lock.txt`.
- Wagi: `C:/Work/Projects/MotionTrace/.models/vision`.
  Manifest zawiera pliki, rozmiary, SHA-256, rewizje i pochodzenie;
  `dependencies.json` oraz `dependency_notices/` dokumentują zależności.
- Nie zmieniano sterownika RTX 3070 Ti ani nie instalowano CUDA Toolkit, WSL czy Dockera.
- Gotowa aplikacja: `artifacts/app-vision-models/motion_trace_win.exe`.
  Należy zachować cały folder publikacji. Alternatywnie `./run.ps1` buduje aktualne źródła.

| Model | Rewizja checkpointu | Licencja modelu |
|---|---|---|
| microsoft/xclip-base-patch16 | d6184e3fd8780d04c85d0f1eabe5f94bf44d98f6 | MIT |
| IDEA-Research/grounding-dino-tiny | a2bb814dd30d776dcf7e30523b00659f4f141c71 | Apache-2.0 |
| facebook/sam2.1-hiera-small | ee5bba1d82bb8749febdf90f45e84b687142ba03 | Apache-2.0 |

Instalator i test importów: `scripts/setup-vision.ps1`.
Szczegóły licencji kodu, wag i zależności: `ThirdPartyNotices/vision.md`.
Nie przypisujemy jednej licencji całemu środowisku ani binarnym zależnościom CUDA/FFmpeg.

## Zachowanie własnego detektora

Zachowano `ai/models/shaft-v1.pt`, `ai/motiontrace_ai/shaft_model.py`, tracking,
geometrię, skrypty treningowe, ewaluację oraz dane i anotacje `research/barbell`.
SHA-256 wag przed i po integracji:
`cd930d56a2e2a63fcbed362d461a96a358200d6a3d9adafe247db982c3809e10`.

Nowy pipeline uruchamia stary interpreter z `--barbell-provider pose_only`.
Import, utworzenie modelu, hashowanie wag i inference własnego detektora są
wyłącznie wewnątrz jawnej gałęzi `custom_barbell`. Domyślny pipeline jej nie używa.
Brak nowego modelu kończy analizę błędem; nie ma automatycznego fallbacku.
W tym zadaniu nie uruchamiano starego detektora do benchmarku.

## Zmiany w kodzie i danych

- `ai/pipeline.py`: dwa jawne interpretery, sekwencyjne etapy, JSONL progress,
  osobny stderr, zachowanie przyczyny błędu. Istniejący `ai/analyze.py` zachowuje pose.
- `ai/vision/{models,pipeline,geometry,measurement,config,analyze}.py`:
  lokalne adaptery, kandydaci DINO, temporalny SAM2, przypisanie na podstawie
  geometrii i zgodności ruchu, osobny punkt LK lub oznaczony proxy, X-CLIP z oknami.
- `src/MotionTrace.Core/Analysis`, `Athletes`, `Exercise`, `Motion`:
  schemat 4, predykcja i wybór użytkownika osobno, obiekty i źródło punktu,
  istniejący wspólny analizator prędkości/repów. Przerwy i zmiany obiektu dzielą trajektorię.
- `src/MotionTrace.Infrastructure/AI/{AnalysisJson,PythonOptions,PythonPoseEngine,VideoCorrections}.cs`:
  odczyt historycznych wyników, zapis nowego kontraktu, konfiguracja, procesy i trwałe poprawki.
- WinUI `MainWindow.Corrections.cs`, `MainWindow.Export.cs`, `MainWindow.Movement.cs`,
  `MainWindow.xaml`, `MainWindow.xaml.cs`, `AnalysisViewModel`, `PoseOverlayRenderer`:
  wskazanie punktu/ramki na zatrzymanej klatce, źródło pomiaru, eksport wybranych osób,
  spinner obok przycisku, zachowanie minimum jednego wybranego zawodnika.
- `ai/motiontrace_ai/export_video.py`: obsługa nowego i historycznego JSON,
  overlay tylko wybranych osób/obiektów, bez ponownego inference.
- `scripts/`, `ThirdPartyNotices/`, testy Python/.NET, `research/vision/`: instalacja,
  licencje, powtarzalne testy i ewaluacja. Nie modyfikowano formularzy anotacji użytkownika.

Nowy wynik przechowuje wersję schematu, manifest/rewizje, konfigurację, hash źródeł,
wersje bibliotek, surowe logity X-CLIP, timestampy próbkowania, decyzję przed i po
sprawdzeniu właściciela, maski jako pliki oraz źródło/jakość każdego punktu.
Eksport kopiuje maski do paczki i używa względnych ścieżek.

## Jak używać korekt

Po analizie wybierz zawodnika w prawej kolumnie. Ćwiczenie można poprawić ręcznie;
wybór jest zapamiętany według SHA-256 filmu i ID zawodnika, osobno od predykcji.

W sekcji korekty wybierz obiekt oraz punkt albo ramkę. `Mark in video` zatrzymuje
film. Wskaż fizyczny punkt lub przeciągnij ramkę, a następnie kliknij `Analyze video`.
Poprawka jest przypisana do filmu, obiektu, zawodnika i czasu. Dane pose są ponownie
wykorzystywane; etap Vision przelicza film od początku. Częściowy replay nie jest
jeszcze zoptymalizowany. Poprawki pozostają w `%LOCALAPPDATA%/MotionTrace/corrections`.

Automatyczny punkt to środek zakresu maski, **nie gwarantowana oś gryfu**.
Ręczny punkt korzysta ze sprawdzanego w obie strony optical flow i zgodności z maską.
Po utracie daje brak pomiaru, zamiast potajemnego przejścia na środek maski.
Bez kalibracji jednostkami pozostają px i px/s. Snatch/CleanAndJerk mają propozycję
klasyfikacji, ale nie udają obsługiwanych faz, repów ani RPE.

## Rzeczywiście wykonane testy

Lista końcowych uruchomień i ich czasów znajduje się w
`artifacts/vision-validation/runs.json`; osobne logi i stderr są obok.
`research/vision/run_integration.py` odtwarza macierz testową sekwencyjnie.

Test bez sieci uruchamia rzeczywiste trzy checkpointy, blokując operacje socket
wyłącznie w swoim procesie. Potwierdza też temporalną pamięć SAM, inicjalizację po
pierwszej klatce i późniejszą korektę punktem. Punkt testowy jest wybierany z maski
automatycznie: to test API i propagacji, nie dokładności ręcznie wskazanej osi.

```powershell
& "$env:USERPROFILE/miniconda3/envs/motiontrace-vision/python.exe" scripts/test_vision_offline.py `
  --models-root "C:/Work/Projects/MotionTrace/.models/vision" `
  --video "videos/bench/100kg x 5.mp4" --output artifacts/offline-check.json

$env:PYTHONPATH = 'ai'
& "$env:USERPROFILE/miniconda3/envs/motiontrace/python.exe" -m unittest discover -s ai/tests
& "$env:USERPROFILE/miniconda3/envs/motiontrace-vision/python.exe" -m unittest vision.test_vision
dotnet test tests/MotionTrace.Tests/MotionTrace.Tests.csproj
dotnet run --project tests/MotionTrace.Smoke/MotionTrace.Smoke.csproj -- --parse-json artifacts/vision-validation/bench-final.json
```

Testy jednostkowe ze stubami są odrębne od rzeczywistych testów checkpointów.
Test C# uruchamia rzeczywiste procesy, powtarza analizę z cache pose, sprawdza JSON,
a osobny scenariusz anuluje przetwarzanie w trakcie etapu SAM.

Potwierdzone: **69 testów starego adaptera/Python, 16 testów Vision, 132 testy
.NET**. Build i publish WinUI Release x64 zakończyły się bez błędów.
Uruchomiony EXE utworzył okno `MotionTrace` i proces odpowiadał.
Odczyt historycznego schematu 2 oraz nowego schematu 4, selektywny eksport JSON,
metryki i CSV przeszły testy C#. Eksport krótkiego MP4 zachował 118 klatek,
1080×1920 i identyczne timestampy. Po anulowaniu nie pozostały procesy Python.

### Wyniki nagrań — końcowa wersja kodu

| Nagranie | Klatki | Decyzja dla zawodnika | Klatki ze śledzonym obiektem | Czas etapu Vision |
|---|---:|---|---:|---:|
| bench / 100kg x 5.mp4 | 565 | BenchPress, właściwy ID2 | 308 | 177,8 s |
| deadlift / VID_20260214_210811~2 (1).mp4 | 352 | Unknown, potrzebny ręczny wybór | 254 | 80,4 s |
| squat / VID_20260420_175856~2.mp4 | 710 | Squat, ID1; pomiary wymagają korekty | 38 | 82,4 s |
| 4 s przygotowania do przysiadu, bez powtórzenia | 118 | Unknown po odrzuceniu niepotwierdzonego powiązania | 0 | dwa wywołania z C# zakończone poprawnie |

Czasy dotyczą etapu Vision; nie są czasem odczytu pliku ani treningu.
Uruchomienia CLI bench/deadlift trwały odpowiednio 181,1 / 89,6 s. Bench używał
wcześniej zapisanego pose, a deadlift/squat przechodziły pełną orkiestrację
z cache pose. Wcześniejsze przebiegi deadlift/squat wykonały także świeże RTMPose.
Szczyt pamięci zaalokowanej przez PyTorch w Vision wyniósł **2 045 354 496 B**
(około 1,90 GiB); nie jest to całkowite zużycie GPU razem z pulpitem i sterownikiem.

Klip bez liftu pochodzi z pierwszych 4 s przysiadu: zawodnik przygotowuje się
i wyjmuje sztangę, lecz nie wykonuje pełnego powtórzenia. Surowy X-CLIP zwracał
Squat; końcowe Unknown pochodzi z jawnego sprawdzenia powiązania obiektu.
To dowód działania abstencji pipeline, nie poprawnego rozróżnienia faz przez X-CLIP.

Porównanie z lokalnymi anotacjami (`*-phases.json`):

- Bench: 3 dopasowane repy z 5; brak repów 4–5 po utracie ID. Średni bezwzględny
  błąd **tylko dopasowanych granic** wyniósł 0,033 s. Ten wynik pomija dwa brakujące
  repy i nie jest ogólną dokładnością całego nagrania.
- Deadlift: po **ręcznym ustawieniu Deadlift** istniejący analizator znalazł 1 rep
  pasujący do jednej anotacji. Błąd dopasowanych granic średnio 0,350 s,
  a koniec opuszczania był opóźniony o 0,761 s. Automatyczne Unknown nie generuje
  tych faz bez ręcznego wyboru ćwiczenia.
- Squat: tracking zaczął się dopiero około 16,21 s, więc ominął oznaczone pierwsze
  powtórzenie. Późniejsza sekwencja 18,24–21,45 s została uznana przez analizator
  za rep. Inspekcja klatek potwierdziła, że maska objęła tułów, a pozorny rep
  pochodził z odkładania sztangi i odchodzenia zawodnika. Dodano filtr maski
  obejmującej większość wnętrza tułowia. Po ponownym rzeczywistym przebiegu
  (`squat-guarded.json`) pozostaje 38 pomiarów i **0 repów**, a 193 obserwacje są
  Lost z powodem odrzucenia zapisanym w metadanych. Usuwa to fałszywy wynik,
  ale nie odzyskuje pominiętych liftów — potrzebna jest korekta punktu/obiektu.
  W filmie widać także drugi przysiad, którego nie obejmuje istniejąca anotacja.

Filtr tułowia wymaga czterech pewnych punktów barków/bioder i pokrycia co najmniej
75% wnętrza tułowia przez maskę; próg i geometria są zapisane w POLICY.
Po takim błędzie obiekt wymaga nowego promptu. Kontrola CPU wszystkich zapisanych
masek bench/deadlift nie odrzuciła żadnej: 0/308 i 0/254. Ich pełne przebiegi GPU
pochodzą sprzed dodania tego ostatniego filtra; nie powtarzano niezmienionych
przebiegów. Przysiad ponowiono na GPU i sprawdzono jego nowy JSON, CSV oraz repy w C#.

Ewaluacja maski przed filtrem tułowia (`final-evaluation.json`) wykorzystała 12 / 3 / 3 oznaczonych
klatek bench/deadlift/squat. Ścisłe pokrycie linii, licząc brak maski jako brak
pokrycia: 45,1% / 39,9% / 24,8%; maska była dostępna odpowiednio w 7 / 2 / 1
oznaczonych klatkach. **To pokrycie anotowanej linii, nie procent dokładności**.
Nie ma referencyjnej prędkości fizycznej ani anotacji tego samego punktu osi,
więc nie raportujemy błędu m/s ani dokładności lokalizacji fizycznego punktu.
Wyniki z końcowym odrzuceniem błędnej maski zapisano osobno jako
`guarded-evaluation.json`; nie nadpisano wcześniejszego raportu.

Anulowanie przez C# wykonano po przekroczeniu 70% postępu, podczas rzeczywistego
etapu SAM w deadlift. Proces nadrzędny i potomny zostały zatrzymane, a tymczasowy
katalog uruchomienia usunięty. Test z zablokowaną siecią zakończył się poprawnie;
nie wystąpiła próba pobrania plików.
Osobny test `offline-multi.json` potwierdził dodanie drugiego obiektu po rozpoczęciu
trackingu i zachowanie obu identyfikatorów. To test API na rzeczywistym SAM2,
nie walidacja rozpoznania dwóch aktywnych zawodników.

## Naprawa powiązania po długim przygotowaniu — IMG_0718.MOV

Wynik użytkownika dla `F:/Bench press/IMG_0718.MOV` zawierał 1485 klatek,
zero obiektów i Unknown. DINO znajdował sztangę, a X-CLIP proponował BenchPress,
lecz korelacja z całego filmu obejmowała długie ustawianie się i odrzucała właściciela.

Reguła `geometry-global-proof-local-fallback-4` zachowuje zaakceptowany dowód
z całego nagrania (również gdy właściciel chwilowo znika). Jeśli takiego dowodu
brakuje, sprawdza lokalne okno 8 s z co najmniej czterema detekcjami. Pozostają
progi ruchu i niejednoznaczności. Zaakceptowana grupa punktów ma pierwszeństwo
przed grupą o wyższej korelacji, która nie spełnia warunku amplitudy.

Rzeczywisty przebieg DINO/SAM2/X-CLIP z istniejącymi wynikami pose zapisał
`artifacts/vision-repair/bench-fixed.json`: Athlete 2, BenchPress, 368 śledzonych
klatek obiektu, 358 użytecznych pomiarów. Wspólny analizator C# znalazł 1 rep:
opuszczanie 1,533 s, podnoszenie 1,467 s, całość 3,067 s. Są to wyniki algorytmu,
nie pomiary dokładności względem ręcznej anotacji. Źródłem nadal jest proxy maski.

Przebieg GPU wykonano podczas pracy nad regułą lokalną; po końcowym dodaniu
ochrony wcześniej potwierdzonego właściciela odtworzono przypisania na wszystkich
detekcjach tego filmu i sprawdzono ich identyczność z wejściem przebiegu GPU.
Nie nadpisywano metadanych tego artefaktu. Odtworzenie wcześniejszych detekcji
bench/deadlift zachowało poprzednie przypisania; klip bez liftu nadal nie miał
przypisań. Dla squat pojawiły się wcześniejsze przypisania, lecz nie powtarzano
SAM i nie deklaruje się poprawy jakości przysiadów na podstawie samej tej kontroli.

Testy: 21 testów Vision, 134 .NET, parsowanie wyniku i selektywny eksport/CSV
w C# przeszły. Debug WinUI zbudowany bez błędów i ostrzeżeń. Przywrócono nakładkę
analizy na filmie, wyrównano odstęp wyboru ćwiczenia i dodano status analizy.
Strukturę XAML sprawdzono; nie wykonano interaktywnej inspekcji natywnego UI.

## Ograniczenia

- Modele ogólne nie zapewniają dokładnego gryfu. Maski potrafią obejmować talerze,
  rack albo inne elementy, więc proxy może mieć błędny ruch.
- Zgodność ruchu wymaga co najmniej trzech próbek DINO w odstępach około 2 s.
  Bardzo krótkie lub nieruchome klipy mogą wymagać ręcznego wskazania obiektu.
- RTMPose może rozdzielić jednego zawodnika na kilka ID przy zasłonięciu.
  Nowy adapter nie scala ich bez dowodów i nie przenosi automatycznie sztangi.
- Unknown jest poprawnym stanem braku pewności. Surowe X-CLIP może rozpoznać
  kontekst ćwiczenia także u asekuranta lub podczas przygotowania; brak potwierdzonego
  właściciela powoduje końcowe odrzucenie propozycji, z zachowaniem surowej decyzji.
- Końcowe wyniki Vision są ponownie używane po sprawdzeniu tożsamości wejść
  oraz hashy wyniku i masek. Zmiana modelu, kodu lub korekt unieważnia cache.
  Wyniki pomiaru przyspieszenia i zakres testu opisano w `analysis-performance.md`.
  Rozdzielczość i precyzja modeli pozostają bez zmian.
- Anotacje opisują widoczne odcinki gryfu, a nie pełne maski i fizyczny punkt osi.
  Pokrycie odcinka maską jest mierzalne, lecz nie jest dokładnością pomiaru pozycji
  ani prędkości; duża błędna maska też może przykryć całą linię.
- Build/testy nie zastępują wizualnej inspekcji WinUI. W tej sesji nie wykonano
  interaktywnego testu natywnego okna; nie deklarujemy weryfikacji jego wyglądu.

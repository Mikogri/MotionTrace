# MotionTrace

Lokalna aplikacja Windows (WinUI 3, C#/.NET) do analizy nagrań treningowych.
Aktualny analizator wykorzystuje **oficjalny Google DeepMind TAPNext++** do śledzenia
dwóch punktów wskazanych na sztandze. RTMPose dostarcza kontekst zawodnika,
a X-CLIP klasyfikację ćwiczenia. Czasy faz, powtórzenia i wykresy oblicza kod C#.
Starsze modele pozostają w źródłach jako wcześniejsze implementacje.

## Zawartość repozytorium

- `win_app/` — aplikacja Windows.
- `ai/` — analizator Python; główny punkt wejścia: `ai/comparison/analyze_session.py`.
- `src/` — modele danych, reguły pomiarów oraz integracja analizatora.
- `tests/` i `ai/tests/` — testy automatyczne.
- `scripts/` — instalacja środowisk i modeli.
- `research/` — narzędzia do oznaczania danych, treningu i ewaluacji.
- `docs/`, `ThirdPartyNotices/` — dokumentacja i informacje licencyjne.

Nagrania, wagi modeli, lokalne zbiory adnotacji, logi, środowiska Python i gotowe
kompilacje nie są publikowane. Pobieranie modeli opisują skrypty
`setup-tap-trackers.ps1`, `setup-vision.ps1` oraz dokumentacja w `docs/`.
Własne wytrenowane wagi trzeba dostarczyć osobno, aby korzystać z ich funkcji.

Uruchomienie ze źródeł: otwórz `MotionTrace.slnx` w Visual Studio (Windows, x64)
lub wykonaj `./run.ps1`. Testy .NET: `dotnet test tests/MotionTrace.Tests`.
Przed analizą przygotuj środowiska Python i modele zgodnie z dokumentacją instalacji.
Samo skopiowanie skryptu analizatora nie wystarcza do uruchomienia całego pipeline.

Dokumentacja aktualnego trackera: [pamięć i wymagania](docs/tapnext-memory.md),
[porównywanie nagrań](docs/video-comparison.md).

Poniższe sekcje zawierają także historyczne instrukcje wcześniejszych wersji silnika;
ścieżki do lokalnych artefaktów nie oznaczają plików dołączonych do repozytorium.

## Uruchomienie

Gotowa wersja z integracją Vision: `artifacts/app-vision-models/motion_trace_win.exe`. Uruchamiaj z całego folderu `app-vision-models`;
sam plik EXE wymaga bibliotek znajdujących się obok niego. Wersja opublikowana zawiera .NET i Windows App SDK.
Python i lokalne modele są osobnym wymaganiem.

Dla nowych modeli uruchom `scripts/setup-vision.ps1` zgodnie z dokumentacją
instalacji. Na tej maszynie środowisko `motiontrace-vision` oraz trzy lokalne
checkpointy są już przygotowane. Starsze sekcje poniżej opisują także historyczne
wersje; aktualną konfigurację Vision opisują dokumenty podane powyżej.

Wersja silnika 0.5 używa PyAV do dekodowania czasu prezentacji i obrotu MOV. W środowisku `motiontrace` wymagane jest `python -m pip install -r ai/requirements-decoder.txt` (zainstalowane na tej maszynie). Pod odtwarzaczem są suwak głośności 0–100% i wyciszenie. Szczegóły napraw dekodowania i pomiar przyspieszenia: [docs/analysis-decoder-v05.md](docs/analysis-decoder-v05.md).

Z PowerShell 7 w katalogu repozytorium:

```powershell
./run.ps1
./run.ps1 -Video ./bench_reel.mp4 -Analyze
```

W Visual Studio otwórz **MotionTrace.slnx** w katalogu głównym i uruchom projekt `motion_trace_win`, konfiguracja x64.
Projekt oryginalnego okna zachowuje dotychczasową ścieżkę. Stary szablon pakietu MSIX pozostaje poza rozwiązaniem;
MVP działa jako aplikacja unpackaged, bez instalacji i podpisywania pakietu.

1. Wybierz `Select video` albo przeciągnij jeden plik MP4/MOV/AVI.
2. Kliknij `Analyze video`. Pierwsze przygotowanie modeli może potrwać kilkanaście sekund.
3. Po zakończeniu wybierz zawodników na liście lub kliknij ich etykiety na filmie.
4. Odtwarzaj albo przewijaj suwakiem; overlay jest dopasowywany do czasu wideo i proporcji obrazu.
5. `Cancel analysis` zatrzymuje proces Pythona wraz z jego procesami potomnymi.
6. Domyślny tryb `Auto` rozpoznaje proporcje odtwarzanego nagrania. Film pionowy
   wykorzystuje pełną wysokość obszaru pracy: wykres prędkości znajduje się po lewej,
   film pośrodku, a zawodnicy i pozostałe wyniki po prawej. Dla filmu poziomego wykres
   pozostaje pod odtwarzaczem. Można też ręcznie wybrać `16:9` / `9:16`.
   Film pozostaje w całości, bez rozciągania i przycinania; overlay skaluje się razem z obrazem.

Interfejs korzysta z domyślnego motywu WinUI/Windows 11: tła Mica, systemowego akcentu,
standardowych kontrolek i zasobów jasnego/ciemnego motywu. Nie wymusza własnej palety kolorów.

## Środowisko

- .NET SDK 10 do budowania, WinUI 3 / Windows App SDK **2.4.0**, Windows x64.
- Lokalny Python 3.10 z działającym MMPose 1.3.2, MMDetection, MMCV, MMEngine,
  PyTorch 2.1 CUDA, OpenCV i SciPy. Istniejącego środowiska nie modyfikowano.
- Domyślny interpreter: `%USERPROFILE%/miniconda3/envs/motiontrace/python.exe`.
  Ścieżkę i urządzenie `cuda:0` lub `cpu` można zmienić w `%LOCALAPPDATA%/MotionTrace/settings.json`
  przy zamkniętej aplikacji. Ustawienia silnika nie są wyświetlane w interfejsie.
- Wagi muszą już znajdować się w katalogu `torch.hub.get_dir()/checkpoints`:
  `rtmpose-m_simcc-body7_pt-body7_420e-256x192-e48f03d0_20230504.pth`
  oraz `rtmdet_m_8xb32-100e_coco-obj365-person-235e8209.pth`.
- Konfiguracja MMPose: `rtmpose-m_8xb256-420e_body8-256x192` — konfiguracja przypisana
  przez MMPose 1.3.2 do aliasu `human`, zgodna z istniejącymi wagami body7.

Adapter używa jawnych lokalnych wag. Nie pobiera modeli ani nie wysyła nagrań do usług zewnętrznych.
Windows musi obsługiwać kodek filmu; samo rozszerzenie MP4/MOV/AVI nie gwarantuje obsługi.

## Struktura i odpowiedzialności

```text
MotionTrace.slnx
win_app/.../motion_trace_win/     # istniejący projekt WinUI, composition root DI
  Features/VideoImport/          # właściwości pliku przez Windows Storage
  Features/VideoAnalysis/        # stan ekranu, sterowanie analizą, renderer overlay
  Features/AthleteSelection/     # prezentacja wyboru zawodników
  Shared/                       # powiadomienia o zmianach właściwości
src/MotionTrace.Core/
  Athletes/                     # semantyczne stawy, klatki pozy, niezmiennik wyboru
  Analysis/                     # kontrakt silnika, wynik i synchronizacja klatek
  Exercise/                     # kontrakt klasyfikacji, maszyna stanów, rep i fazy
  Motion/                       # kontrakt sztangi, próbki XY i kalkulator prędkości
src/MotionTrace.Infrastructure/
  AI/                           # proces Python, DTO, walidacja JSON, ustawienia
  Logging/                      # lokalne logi
ai/
  analyze.py                    # CLI, inference, timestampy, cache, wersjonowanie
  motiontrace_ai/mapping.py      # MMPose COCO-17 → semantyczny format MotionTrace
  motiontrace_ai/tracking.py     # dopasowanie osób między klatkami
tests/MotionTrace.Tests/         # testy domeny i granicy JSON
tests/MotionTrace.Smoke/         # jawny test integracyjny na prawdziwym silniku
ai/tests/                       # testy trackingu i mapowania MMPose
```

Core nie zależy od WinUI, Pythona, MMPose ani biblioteki wykresów. `IPoseAnalysisEngine`
można zastąpić implementacją ONNX/TensorRT bez zmiany modeli domenowych i renderera.
Code-behind obsługuje picker/drag-drop, czas odtwarzacza i cykl życia zasobów UI.
Wybór co najmniej jednego zawodnika jest wymuszany przez agregat domenowy, niezależnie od checkboxów.

## Tracking i ograniczenia

Tracker używa dopasowania Hungarian 1:1, przewidywanej pozycji, IoU oraz odległości
pewnych keypointów. Potwierdzenie wymaga 3 obserwacji; krótkie zniknięcie do 0,6 s
nie usuwa od razu tożsamości. Wyniki nie zawierają losowych danych ani interpolowanych,
niewykrytych szkieletów. Rysowane są tylko stawy z confidence co najmniej 0,4.

**Track ID nie jest gwarantowaną tożsamością osoby przez cały zmontowany film.**
Nie ma jeszcze modelu appearance re-identification ani obsługi łączenia ścieżek po cięciach.
W `bench_reel.mp4` cięcie przy klatce 124 powoduje utworzenie nowej ścieżki: wynik ma
742 klatki i 3 ścieżki, chociaż w kadrze są dwie osoby. UI mówi o liczbie ścieżek.
Nakładanie się osób i długie zasłonięcia również mogą zmienić ID.

Analiza obejmuje obecnie cały film przed wyborem ścieżek. Wybór filtruje overlay;
nie ogranicza jeszcze kosztu inference. Wyniki klatek są trzymane w pamięci, więc MVP
jest przeznaczone do krótkich nagrań serii. Długie sesje wymagają strumieniowania wyników.

## Co działa, a co jest przygotowane

Działa: import i metadane, lokalna detekcja wielu osób, pose tracking, wybór ścieżek,
szkielety/keypointy/bounding boxy/ID, odtwarzanie i przewijanie, postęp, anulowanie,
walidacja wyników oraz cache analiz.

Przygotowane, ale **nie podłączone do automatycznej analizy ruchu**:

- `IExerciseClassifier` i jawny wynik `Unknown`, confidence 0. Nie ma zweryfikowanej
  heurystyki rozróżniającej squat/bench/deadlift dla dowolnego kąta kamery.
- `ExerciseStateMachine`: reaguje na sygnał ruchu w czasie, toleruje krótkie pauzy,
  nie uznaje brakujących obserwacji za ciągły bezruch. Brakuje generatora sygnału dla ćwiczeń.
- `Repetition`: numer, start/koniec, całkowity czas, uporządkowane fazy. Nie ma detektora repów.
- `IBarbellTracker`: brak modelu sztangi jest jawnym stanem niedostępności.
- `VelocityCalculator`: rzeczywiste obliczenia XY/time z kontrolą odstępów i confidence;
  `px/s` bez kalibracji, `m/s` wyłącznie po podaniu skali. Oś Y rośnie w dół obrazu.
  Panel wykresu pokazuje brak danych; nie rysuje fikcyjnej serii.

Następny etap: materiał walidacyjny w ciągłych ujęciach, tracking przy zasłonięciach
i opcjonalne łączenie ścieżek, następnie osobny detektor sztangi oraz zweryfikowany
temporalny klasyfikator ćwiczeń i repów. Dopiero na ich danych należy podłączyć wykres.

## Format danych i cache

Jeden JSON z `schemaVersion: 1`, `video`, `versions`, `athletes`, `frames`, `limitations`.
Timestampy w sekundach pochodzą z dekodera, współrzędne są w pikselach obrazu.
Keypoint ma nazwę stawu, `x`, `y`, `confidence`; pozycja w tablicy MMPose nie wycieka do domeny.
Wersje obejmują engine, pose model z hashem wag, detector z hashem, brak modelu sztangi i pakiety środowiska.
Parser odrzuca obcy schemat, nieprawidłowe ID, confidence i nieuporządkowane timestampy.

`%LOCALAPPDATA%/MotionTrace/` zawiera `settings.json`, `logs/`, `cache/` i tymczasowe `runs/`.
Klucz cache obejmuje SHA-256 filmu, obu zestawów wag, konfiguracji modeli, adaptera,
wersji pakietów oraz urządzenia. Modele są inicjalizowane przed sprawdzeniem cache,
więc cache pomija inference, ale nie cały czas przygotowania. Wynik zapisuje się atomowo;
anulowana lub niepełna analiza nie trafia do cache. MVP nie ma jeszcze automatycznej polityki usuwania cache.

## Weryfikacja

```powershell
dotnet build MotionTrace.slnx -p:Platform=x64
dotnet test tests/MotionTrace.Tests/MotionTrace.Tests.csproj
Push-Location ai
& "$env:USERPROFILE/miniconda3/envs/motiontrace/python.exe" -m unittest discover -s tests -v
Pop-Location
dotnet run --project tests/MotionTrace.Smoke -- bench_reel.mp4 ai/analyze.py artifacts/smoke
dotnet publish win_app/motion_trace_win/motion_trace_win/motion_trace_win/motion_trace_win.csproj -c Release -p:Platform=x64 --self-contained true -o artifacts/app
```

Test integracyjny wykonuje prawdziwą analizę, sprawdza ponowne użycie cache, parsuje wynik
w C# i przerywa kolejny proces Pythona, weryfikując sprzątanie katalogu roboczego.
Testy jednostkowe obejmują wybór zawodników, maszynę stanów, timing repów, prędkość,
mapowanie DTO i nieprawidłowy JSON; testy Pythona obejmują zmianę kolejności detekcji,
krótkie/długie zasłonięcia, potwierdzanie ścieżek i mapowanie COCO-17.

Wersję Windows App SDK potwierdzono w [kanale stabilnym Microsoft](https://learn.microsoft.com/en-us/windows/apps/windows-app-sdk/release-channels).

## Eksperymentalne rozpoznawanie wyciskania
Aplikacja pokazuje Bench press / Unknown dla zaznaczonych osób przy bieżącym czasie filmu. Detektor regułowy analizuje sześć sekund historii, a score nie jest prawdopodobieństwem. Obecny prototyp pomija część ujęć i nie mierzy czasu powtórzenia. Wyniki i ograniczenia: research/bench_press/README.md.


## Wykresy faz ruchu
Po analizie wybierz w Movement analysis zawodnika, widoczny nadgarstek i ręcznie ćwiczenie. Algorytm analizuje pionowy ruch tej jednej ręki. Wybierz wykryte powtórzenie i użyj Show rep start do porównania z filmem. Dolna oś wykresu pozycji to czas filmu; na wykresach faz to czas od początku danej fazy. Zacieniowanie zaznacza wybrane powtórzenie.

- Lowering: czas opuszczania, średnia pionowa prędkość i maksimum.
- Lifting: czas podnoszenia, średnia pionowa prędkość i maksimum.
- Total obejmuje obie fazy i pauzę na dole. Pauza jest pokazana osobno.
- Dodatnia prędkość oznacza ruch w kierunku danej fazy; wartości ujemne pokazują chwilowe cofnięcie albo szum pozy.
- Start wymaga przemieszczenia co najmniej 1,5% wysokości obrazu (próg regulowany) przez co najmniej 0,18 s. Po potwierdzeniu czas jest cofany do ostatniej próbki blisko szczytu. Tolerancja pozycji wynosi 12% progu ruchu.
- Koniec jest potwierdzany po około 0,35 s zatrzymania lub wyraźnym odwróceniu ruchu, ale znacznik końca wraca do ostatniego istotnego postępu w górę. Pauza w częściowym podniesieniu nie kończy powtórzenia; w ruchu z opuszczaniem wymagany jest powrót co najmniej 70% drogi.
- Deadlift pozwala rozpocząć podnoszeniem bez opuszczania. Po zakończeniu podniesienia kolejne opuszczenie może rozpocząć następne powtórzenie. To ręcznie wybrany tryb segmentacji, nie rozpoznanie deadliftu.
- Dane są wygładzane medianą w oknie ±75 ms; prędkość pochodzi z lokalnego dopasowania prostej w ±100 ms. Obliczenia korzystają ze znaczników czasu filmu, a nie zakładanego FPS.
- Braki dłuższe niż 0,25 s oraz duże skoki pozy rozdzielają serie. Niekompletne powtórzenia nie otrzymują czasu zakończenia.

**Ograniczenie:** są to kandydaci na powtórzenia oraz przybliżenie ruchu nadgarstka w px/s, nie pomiar sztangi w m/s. Nie ma kalibracji przestrzennej ani kompensacji ruchu kamery. Ruch przygotowawczy, chodzenie i pomoc spottera mogą dawać fałszywe kandydatury. Progu wyrażonego w procentach obrazu nie należy traktować jak uniwersalnego progu biomechanicznego. Sprawdzono działanie na trzech zapisanych analizach bench; wyników nie oceniono jako dokładności czasowej względem ręcznych etykiet. Scenariusze deadlift i squat sprawdzono na syntetycznych sygnałach — w zbiorze nie ma ich nagrań.

Odtworzenie pomiarów na lokalnych JSON-ach: `dotnet run --project research/bench_press/Evaluate -- --movement <analysis.json>`. Przykładowy wynik: research/bench_press/movement-results.txt.

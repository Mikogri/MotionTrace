# Cztery niezależne trackery MotionTrace

## Obsługa

1. Otwórz oryginalny film. Zatrzymaj klatkę, na której dobrze widać oś końca gryfu lub piasty talerza.
2. Po prawej wybierz `Measurement point (click)` i `Mark in video`, a następnie kliknij fizyczny punkt. Nie wskazuj logo obracającego się talerza.
3. Opcjonalnie na tej samej klatce zaznacz `Object box (drag)`. Bez ramki DINO proponuje obiekt zawierający punkt; nie zastępuje punktu środkiem ramki. Przy niejednoznacznym właścicielu wskaż ID zawodnika lub czytelniejszą klatkę.
4. `Analyze video` przygotowuje wszystkie cztery wyniki. RTMPose i X-CLIP wykonują wspólne przygotowanie tylko raz.
5. `Tracking model` wybiera gotowy wynik, bez inference i bez ponownego wyliczania repów. Niedostępny wynik pokazuje pusty stan i własny status. Podczas pracy można oglądać modele już gotowe.
6. `Cancel` zachowuje ukończone wyniki. `Analyze missing models` i `Retry selected` są jawnymi akcjami obliczeniowymi.

Zmiana punktu lub ramki unieważnia zależne wyniki. Zmiana progu ruchu wymaga jawnego Analyze, ale korzysta z surowego cache bez ponownego trackingu. Ręczny wybór BenchPress/Squat/Deadlift wykorzystuje wcześniej przygotowane warianty metryk. Nie ma nowego modelu RPE ani automatycznego wyboru najlepszego trackera.

## Architektura i pliki

- `ai/comparison/prepare.py`: walidacja prawdziwych PTS, punkt/ramka/właściciel i wspólny X-CLIP.
- `ai/comparison/analyze_session.py`: sesja, jawne interpretery, procesy, cache, integralność artefaktów, cztery zadania od początku.
- `ai/comparison/scheduler.py`: aktualna wolna VRAM/RAM, rezerwacje, kolejka i jedno ograniczone ponowienie OOM. Model/FPS/rozdzielczość pozostają bez zmian.
- `dino_backend.py`, `samurai_backend.py`, `tap_backends.py`: niezależne stany i trajektorie. SAMURAI nie zastępuje dotychczasowego DINO/SAM.
- `src/MotionTrace.Core/Analysis/AnalysisSession.cs`: statusy, przygotowane metryki/wykresy i wybór wyniku przez referencję. Rep dopasowywany po czasie, nie numerze.
- `src/MotionTrace.Infrastructure/AI/ComparisonAnalysisEngine.cs`, `ComparisonSnapshotStore.cs`: protokół, przygotowanie poza UI, atomowy zapis, cache i anulowanie drzewa procesów. Ready dopiero po metrykach.
- WinUI `AnalysisViewModel.Comparison.cs`, `MainWindow.Comparison.cs`: jeden ViewModel, atomowa podmiana prezentacji. Oryginalny plik odtwarzania nie jest przeładowywany.
- `MainWindow.xaml`, `MainWindow.Corrections.cs`, `PoseOverlayRenderer.cs`: selektor po prawej, wspólny punkt, spinner obok Analyze, overlay punktowy bez wymyślonej ramki.
- `MainWindow.Export.cs`, `ai/motiontrace_ai/export_video.py`: eksport aktywnego źródła, gotowych metryk i punktowych trackerów.
- `MainWindow.ComparisonSmoke.cs`, `research/comparison/SessionProbe`: jawne lokalne testy całej sesji i rzeczywistej warstwy WinUI.

Cache przechowuje surowy tracking, osobne maski/raw observations, poprawione dane, repy, metryki i statusy. Przy otwarciu odtwarza lekkie projekcje wykresów poza UI; przełączanie nie parsuje JSON. Sprawdza tożsamość filmu, inicjalizacji, konfiguracji, kodu, manifestów oraz integralność wyników/masek. Zmiana kalibracji nie zmienia klucza inference; aplikacja obecnie raportuje jednostki obrazu px i px/s, bez kalibracji metrycznej UI.

Stary DINO/SAM można odtworzyć jako jedyny gotowy provider wyłącznie po zgodności SHA256 filmu; pozostałe pozostają NotAnalyzed. Własny detektor użytkownika, jego kod, dane i wagi są zachowane, ale nie należą do nowej sesji i nie są ładowane ani używane jako fallback. SHA256 `ai/models/shaft-v1.pt`: `cd930d56a2e2a63fcbed362d461a96a358200d6a3d9adafe247db982c3809e10`.

## Instalacja i warianty

Uruchom istniejący `scripts/setup-vision.ps1` dla DINO/SAM/X-CLIP, `scripts/setup-samurai.ps1` oraz `scripts/setup-tap-trackers.ps1` dla nowych modeli. Działające środowisko MMPose pozostaje bez zmian.

| Provider | Implementacja | Środowisko |
|---|---|---|
| DINO/SAM | Dotychczasowy Grounding DINO + SAM2 | motiontrace-vision |
| SAMURAI | Oficjalny zmodyfikowany predictor, SAM2.1 small, forward temporal | motiontrace-samurai |
| TAPNext++ | Oficjalny `tapnextpp_ckpt.pt`, 256×256, online recurrent | motiontrace-points |
| BootsTAPIR | Oficjalny `bootstapir_checkpoint_v2.pt`, 256×256, offline full sequence | motiontrace-points |

Nowe środowiska: Python 3.11.16, torch 2.8.0+cu126, torchvision 0.23.0+cu126. Rewizje, pełne sumy wag, przypięte zależności i źródła/licencje opisują [SAMURAI](samurai-backend.md), [TAP](tap-point-trackers.md) oraz manifesty `.models/*/manifest.json`. Analiza ustawia tryb offline i korzysta wyłącznie z lokalnych plików; brak wag jest błędem bez pobierania/fallbacku.

## Jakość i ograniczenia

- To porównanie niezależnych trackerów, nie ensemble. Confidence modeli nie jest wspólną skalą dokładności.
- SAM/DINO i SAMURAI dostarczają maski. Pomiar wskazanego punktu wykorzystuje niezależny LK z kontrolą forward/backward i maski. Nie jest natywną głowicą punktową SAMURAI; po utracie nie przechodzi na centroid.
- Trackery punktowe zachowują surowe przewidywania, lecz zasłonięte punkty nie stają się obserwowanym pomiarem. Wszystkie nowe pomiary mają ostrożną ocenę jakości Reduced.
- Sprawdzony film bench ma spottera, pięć powtórzeń i częściowe zasłonięcia. Nie jest walidacją dokładności w pikselach ani testem wszystkich kątów, squat/deadlift i długich zasłonięć.
- Maleńki koniec tulei w tym filmie powodował dryf; widoczna oś piasty dawała lepszą stabilność. Zachowano obie próby. Żaden backend sam nie zmienia wskazanego punktu.
- BootsTAPIR offline wymaga pamięci rosnącej z długością filmu. Przekroczenie dostępnej pamięci daje jawny błąd. Nie ma cichego przejścia na causal, krótszy film ani mniejszy FPS.
- SAMURAI utrzymuje oryginalną pamięć ruchu; pomija opcjonalne CUDA hole filling. Wykonuje tracking od klatki inicjalizacji w przód.

## Pomiary

Szczegółowe wyniki pełnej sesji i testów UI znajdują się w `artifacts/four-trackers`. Czasy PyTorch peak allocated oznaczają pamięć tensorów danego procesu, nie całkowitą zajętość karty. Pomiar wyboru referencji w konsoli nie jest pomiarem renderowania UI.

### Wynik pełnej sesji — 22.09.2026

Film: `videos/bench/100kg x 5.mp4`, 565 klatek, 18,83 s. Punkt ręczny `(613,1576)` na osi bliskiej piasty, klatka 0, zawodnik 2. Wspólny X-CLIP: BenchPress dla zawodnika 2; spotter 1: Unknown.

| Tracker | Pomiarów punktu | Repy bench zawodnika 2 | Czas backendu | Peak tensorów GPU |
|---|---:|---:|---:|---:|
| DINO/SAM | 565 | 5 | 199,83 s | 1950,6 MiB |
| SAMURAI | 565 | 5 | 161,85 s | 702,3 MiB |
| TAPNext++ | 565 | 5 | 57,88 s | 1624,0 MiB |
| BootsTAPIR | 565 | 5 | 13,19 s | 2114,1 MiB |

Spotter ma zero repów sztangi we wszystkich wynikach. To nie jest wymuszona zgodność: granice repów TAPNext++ i BootsTAPIR różnią się od wyników segmentacji. DINO i SAMURAI korzystają z tej samej reguły LK, lecz niezależnych masek i stanów.

- Jedna pełna sesja: **499,145 s** (ciepły cache pose, ponownie wykonane cztery trackery i wspólny X-CLIP).
- Wszystkie cztery wyniki z metrykami: Ready. Ponowne otwarcie: **1,257 s**. Nowy proces: **1,870 s**, zero zdarzeń Analyze.
- Na RTX 3070 Ti i 16 GB RAM zadania rzeczywiście wykonały się **kolejno**, ze względu na bieżącą dostępność pamięci. Scheduler nie pominął żadnego modelu.
- Próbkowane całkowite użycie GPU: maks. **3482 MiB**, wraz z pulpitem. Maks. zaobserwowany peak working set procesu Python: **4123 MiB**. Próbkowanie zasobów rozpoczęto w etapie SAMURAI; nie jest pomiarem globalnego szczytu całej sesji.
- Test konsolowy 1000 wyborów gotowych referencji: mediana **0,0011 ms**, p95 **0,0016 ms**. To nie pomiar UI.

Weryfikacja: **175 test�w .NET**, **121 testów Python w ai/tests**, **52 testy vision**, **5 testów SAMURAI**. WinUI Release/x64: **0 błędów, 0 ostrzeżeń**. Rzeczywiste testy modeli działały z lokalnymi wagami i flagami offline; nie blokowano sieci systemowym firewallem.

Testy procesowe CPU pokrywają anulowanie drzewa procesów, awarię pojedynczego providera, niezależne wyniki i zapis/cache. OOM sprawdzono testem schedulera, nie celowym wyczerpaniem GPU użytkownika. RenderTargetBitmap w teście WinUI nie przechwytuje natywnego obrazu MediaPlayer ani Mica; diagnostyczny PNG zawiera warstwę XAML na jednolitym tle. Postęp odtwarzania i niezmienność jego źródła sprawdzono na działającym MediaPlayer.

### Rzeczywisty WinUI — gotowy aktywny rep

`artifacts/four-trackers/winui-active-rep.json`: 40 zmian selektora z przygotowanym wykresem, tabelą i overlayem. Aktualizacja na wątku UI: **mediana 5,73 ms, p95 9,37 ms, max 10,04 ms**. Osobne odrysowanie overlayu: mediana **0,46 ms**, p95 **0,83 ms**, max **16,44 ms**. W każdym sprawdzonym stanie analiza, ruch i overlay miały właściwego providera; zachowano źródło filmu, timestamp, pauzę i prędkość 1,25×. W teście 60 zmian podczas odtwarzania film przeszedł z 6,202 s do 9,144 s w 2,353 s czasu rzeczywistego, zachowując Playing i to samo źródło.

Dodatkowy test przy t=5 s (`winui-smoke-final.json`) potwierdził wyczyszczenie aktywnego repa przy braku jednoznacznego dopasowania. Przy t=6 s kolejne modele dopasowały rep 2. Obejrzano diagnostyczny obraz XAML: tabela, kolorowane fazy i separatory są widoczne. Czasy powyżej mierzą pracę UI i odtwarzacza, **nie opóźnienie prezentacji kompozytora ani subiektywną płynność obrazu wideo**.


Ko�cowy przegl�d wykry� i poprawi� przypadek podmiany pliku konfiguracji/wag pose pod t� sam� �cie�k�. Cache .NET uwzgl�dnia teraz r�wnie� ich SHA256 oraz jawne �cie�ki interpreter�w; test regresyjny najpierw odtworzy� b��d. Po poprawce wszystkie cztery snapshoty przygotowano ponownie z surowego cache w **3,12 s**, bez inference (`cache-reprepare.log`). Oryginalny pomiar pe�nego wykonania modeli zachowano w `full-session/gpu-session-report.json`, a aktualny cache w `full-session/probe-report.json`. Ostateczny build Release/x64: zero ostrze�e� i b��d�w.

Po końcowej poprawce cache uruchomiono ponownie **finalny WinUI w nowym procesie**, bez flagi Analyze: `artifacts/four-trackers/winui-verified.json`. Wszystkie 40 kontroli zgodności snapshot/ruch/provider/źródło/czas/prędkość przeszły. Mediana przełączenia **4,66 ms**, p95 **6,60 ms**, max **8,16 ms**; mediana odrysowania overlayu **0,39 ms**, p95 **1,30 ms**. Odtwarzanie zachowało Playing i to samo źródło; 60 przełączeń nie zresetowało pozycji. Te pomiary dotyczą pracy wątku UI, nie opóźnienia kompozytora.

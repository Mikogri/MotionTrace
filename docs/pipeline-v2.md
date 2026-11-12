# MotionTrace: pipeline 0.3 / schema 2

## Przepływ
RTMDet person → PersonTracker → stabilne ID / Lost → StableCrop → RTMPose-L 384×288 → schema 2 (surowe pozy i tracking) → CorrectingPoseEngine → TemporalPoseCorrector (C#) → poprawione pozy → WristTrajectoryProvider → MovementAnalyzer → MovementRepDetector / MovementStatusTimeline → PlaybackChart.

Python estymuje wszystkie śledzone osoby przy pierwszej analizie, ponieważ wybór zawodnika następuje po analizie. Opcjonalne `--athlete-ids` ogranicza estymację pozy do wybranych ID, zachowując detekcję i tracking pozostałych osób. Zaznaczenia w UI nie powodują ponownej inferencji. Minimum jednej zaznaczonej osoby nadal wymusza domenowy AthleteSelection. Źródło pomiaru jest oddzielnym, jawnym wyborem jednej osoby/ręki; nie przełącza się w trakcie zgubienia śladu. Jeśli klasyfikator nie wskazuje kandydata, użytkownik wybiera źródło pomiaru ręcznie.

## Tracking
`ai/motiontrace_ai/person_tracking.py`: detekcje bbox i lekki histogram HSV są dopasowywane jeden-do-jednego algorytmem Hungarian. Koszt uwzględnia przewidywany środek, IoU, zmianę rozmiaru i wygląd. Silne detekcje rozpoczynają ślad; słabsze mogą podtrzymać istniejący. Niejednoznaczne dopasowania oraz próba zastąpienia zaginionej osoby innym wyglądem pozostawiają Lost. Trzy trafienia potwierdzają ślad, utrata ponad 1 s kończy możliwość jego odzyskania. Nie jest to pełna implementacja ByteTrack ani wytrenowany ReID. Histogram może mylić podobne ubrania i tło. Brak gwarancji zachowania ID podczas trudnego przejścia/cięcia. Ślady mają własną tożsamość niezależną od kolejności wyników RTMPose. Interfejs update pozwala zastąpić tracker bez zmiany estymacji pozy.

StableCrop wygładza bbox w czasie (stała 0,12 s), dodaje domyślnie 20% paddingu na stronę, przycina do obrazu i zachowuje aktualną detekcję wewnątrz obszaru. Wyłączono dodatkowy padding GetBBoxCenterScale, aby go nie dublować. RTMPose nadal dopasowuje proporcje cropa do wejścia sieci.

## Konfiguracja modelu
`%LOCALAPPDATA%/MotionTrace/settings.json`: PoseModel, PoseWeights, CropPadding, Correction oraz istniejące PythonExecutable/Device. Domyślnie RTMPose-L body8 384×288. Pobrano lokalne wagi wskazane w metadanych zainstalowanego MMPose; analiza nigdy nie pobiera wag. Model M można wybrać jako `rtmpose-m_8xb256-420e_body8-256x192` (PoseWeights pusty wybiera odpowiadające znane wagi). Dla innych wariantów trzeba podać zgodne lokalne wagi; mapper wymaga COCO-17. Błąd modelu lub brak VRAM jest zgłaszany, bez cichego przełączenia na słabszy model.

Cache zawiera hash filmu, kodu, wag, konfiguracji modelu, padding, wariant i wersję trackera. Schema 2 dodaje trackingState, trackingConfidence, occlusionRisk i cropBox. C# nadal czyta schema 1. Korekcja jest wykonywana również po trafieniu cache; wynik domenowy przechowuje CorrectionVersion wraz z parametrami. JSON cache zachowuje surowe dane, nie duplikuje poprawionych klatek.

## Korekcja offline w Core
`TemporalPoseCorrector` operuje osobno na ciągłych fragmentach tej samej tożsamości. Lost/nieobecny ślad rozcina fragment. Składa się z:
- SideSwapCorrector: krótkie zamiany stron (do 3 klatek), wymagające potwierdzenia ciągłości zarówno przed, jak i po fragmencie.
- JointOutlierDetector: odchylenie od przewidywania z sąsiadów, prędkość i przyspieszenie z rzeczywistych timestampów, skala bbox.
- LimbConsistencyValidator: lokalna mediana proporcji kończyn z sąsiednich klatek i szeroka tolerancja perspektywy. Oznacza podejrzany dalszy staw, nie narzuca sztywnego szkieletu.
- ShortGapInterpolator: domyślnie maks. 3 brakujące klatki i maks. 0,15 s między poprawnymi końcami. Brak ekstrapolacji, obniżona confidence.
- IPoseSmoother / LightPoseSmoother: lekka korekta w stronę temporalnego przewidywania sąsiadów (20%). Punkt pozostaje dominującą obserwacją; filtr można zastąpić inną implementacją w DI.

Keypoint przechowuje RawPosition, Position, ModelConfidence, TrackingConfidence, IsCorrected, IsInterpolated i IsOutlier. OcclusionRisk redukuje confidence. Jakość całej pozy i jakość wybranego nadgarstka są rozdzielone: zasłonięta twarz nie musi unieważniać widocznej ręki. Wyniki nadal są heurystyczne, szczególnie przy silnej perspektywie, podobnych osobach, długich zamianach stron i brakach detekcji.

## Trajektorie, velocity i repy
IMotionTrajectoryProvider → WristTrajectoryProvider izoluje źródło pomiaru. MotionSample ma FrameIndex, TimestampSeconds, raw i corrected position, confidence i quality. Velocity powstaje z poprawionej trajektorii po dodatkowej krótkiej medianie czasowej i lokalnym dopasowaniu prostej, z faktycznych timestampów. Jednostki to px i px/s. PixelScaleCalibration jest przygotowany na późniejszą kalibrację; aktualny interfejs nie pokazuje jednostek fizycznych.

MovementRepDetector zachowuje regułę wyraźnego zejścia ze szczytu, pomija drobne drgania, rozdziela opuszczanie/pauzę/podnoszenie i nie zamyka niekompletnego ruchu. Deadlift może zaczynać się podnoszeniem. Modele MovementRep/MovementPhase przechowują czasy, indeksy klatek i jakość. Fazy używają widoków na próbki zamiast kopiować ich zawartość. Lista pokazuje numer, czas i jakość; wybór repa przewija film do jego początku. To nadal kandydaci: przygotowanie i ruch spottera mogą wyglądać jak powtórzenie. Brak oznaczonego zbioru nie pozwala podać wiarygodnej dokładności czasów ani repów.

MovementStatusTimeline korzysta z osobnego ExerciseStateMachine: 0,3 s ruchu do Performing, 3 s rzeczywistego bezruchu do Finished. Brak danych nie jest bezruchem. Klasyfikacja pozostaje temporalnym IExerciseClassifier; heurystyka Bench press/Unknown odrzuca Poor/Lost. Squat/deadlift są nadal ręcznymi trybami segmentacji, nie wytrenowanymi klasami.

## Playback i UI
Aktualny panel repów opisuje [rep-comparison-ui.md](rep-comparison-ui.md). Jeden PlaybackChart obsługuje wiele serii Height/Velocity z osią Time lub koncentrycznego ROM %. Osobne wykresy fazowe zastąpiono podsumowaniem czasów. PlaybackSampleLookup wyszukuje binarnie próbki wokół dokładnego czasu video i interpoluje tylko wewnątrz ciągłego fragmentu. Nie przenosi wartości przez lukę. Geometria zmienia się przy zmianie danych, wyboru, metryki, osi lub rozmiaru; timer przesuwa istniejące Line/Ellipse i aktualizuje wartość.

Analyze ma ProgressRing oraz disabled state. Brak procentów i progress bara, Cancel pozostaje. Debug pose domyślnie wyłączony: pomarańczowe surowe punkty z tooltipem raw/corrected/confidence/flag, skorygowany szkielet, bbox, ID, Lost, jakość i confidence śledzenia.

## Sprawdzenie i dalszy rozwój
Końcowa weryfikacja 2026-09-12: build rozwiązania bez błędów i ostrzeżeń, 60/60 testów .NET, 14/14 testów Python oraz publikacja self-contained x64 do `artifacts/app`. Testy Python uruchamia się z katalogu `ai`: `python -m unittest discover -s tests -v`.

Przeprowadzono testy jednostkowe trackingu, korekcji, selekcji, faz, velocity, timestampów i seek. Integracyjnie RTMPose-L działa na RTX 3070 Ti 8 GB: 413 klatek filmu bench, 3 potwierdzone ślady; schema 2, cache i rzeczywiste anulowanie procesu przeszły. Raport korekcji: artifacts/corrected-movement-report.txt. To test wykonania, nie dowód wzrostu accuracy. Na tym ujęciu wiarygodność pozy zawodnika nadal ogranicza wykrywanie powtórzeń.

Docelowo: wytrenowany ReID / mocniejszy tracker, detektor sztangi, kalibracja, wytrenowany temporalny classifier i zweryfikowany detektor faz. Potrzebne ręcznie oznaczone tożsamości, zasłonięcia i granice powtórzeń z całych oddzielnych sesji; aktualne heurystyki nie zastępują takiej walidacji.

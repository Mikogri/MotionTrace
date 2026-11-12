# Wybór modelu i poprawki analizy

## W aplikacji

Pod przyciskami analizy jest wybór **MotionTrace** (własny detektor gryfu v1)
lub **DINO + SAM2**. Wybór jest zapamiętywany, a podczas analizy zablokowany.
Nowe ustawienia domyślnie wybierają MotionTrace; wcześniejszy zapisany wybór
pozostaje zachowany. Kandydat wieloćwiczeniowy v2 nie jest automatycznie wdrażany.

Zmiana modelu nie zmienia istniejących wyników: status wskazuje model poprzedniej
analizy i potrzebę ponownego przeliczenia. Eksport nadal opisuje faktyczny model
wyniku. Korekty maski/punktu są dostępne wyłącznie dla ukończonej analizy DINO/SAM2.
Własny model nie wymaga środowiska Vision; brak jego wag daje jawny błąd zamiast
pustego wyniku udającego poprawną analizę.

## Gryf, powtórzenia i fazy

W filmie `100kg x 5.mp4` po ostatnich poprawkach nadal ginął piąty rep własnego
modelu. Ostatnia obserwacja gryfu była w 14,700 s, kolejna w 14,900 s. Pięć
brakujących klatek wystarczało do nadania nowego ID i utraty właściciela.

Tracker zachowuje teraz tożsamość przez maksymalnie 0,4 s, ale ważność pomiaru
nadal tylko przez 0,15 s. Odzyskanie wymaga nowej, jednoznacznie dopasowanej
detekcji. Podczas zasłonięcia nie są emitowane fikcyjne pozycje ani przepływ
optyczny przez przerwę. Analizator C# może połączyć obserwowane końce przerwy
do 0,25 s wyłącznie dla tego samego gryfu/właściciela, ze zgodnym kątem i dużym
pokryciem odcinków. Wynik ma obniżoną jakość; zmiana właściciela przerywa ciągłość.

Pełny produkcyjny przebieg własnego modelu na tym filmie daje **5/5 oznaczonych
repów**, wcześniej 4/5 po poprawce tożsamości sylwetki. Przy poprawnie ustawionym
BenchPress MAE 20 granic faz wynosi **0,035 s**, maksymalny błąd **0,133 s**.
Wynik zawiera tylko zawodnika ID2 jako potwierdzonego uczestnika.
Czas wewnętrzny etapu Python z nowym obliczeniem pozy: 55,86 s na tym komputerze.
To nie gwarancja czasu ani dokładności dla innych nagrań.

Dodatkowo przeliczono sześć filmów własnym detektorem przy identycznych starych
pozach z pierwotnego porównania, aby odseparować zmianę trackera gryfu. Dopasowanie
wzrosło z **4/10 do 5/10** (bench 4/5, pierwszy deadlift 1/1); pozostałe braki
utrzymują się. Ten przebieg celowo nie zawiera nowej identyfikacji sylwetki,
więc nie należy mieszać jego sumy z nowym pełnym wynikiem bench 5/5.
Etykiety są rozwojowe; nie jest to niezależny test na nowych filmach.

## Rozpoznawanie ćwiczeń

Dodano wspólne rozpoznawanie awaryjne na podstawie przypisanej ruchomej sztangi
i widocznej anatomii, gdy klasyfikator nie ma decyzji. Potwierdzone decyzje modelu
oraz ręczne ustawienia pozostają zachowane. Środek maski SAM nie jest traktowany
jako fizyczna oś gryfu przy ocenie wysokości rąk. Pochodzenie decyzji trafia do
podsumowania i eksportu. Szczegóły i wynik weryfikacji opisuje
[exercise-recovery.md](exercise-recovery.md).

Nie obniżano progów ukrytych stawów, nie zaliczano braku sztangi jako ruchu,
nie zastępowano Unknown arbitralnym ćwiczeniem. Trudne kąty, przerwy dłuższe niż
obsługiwane i brak przypisanej sztangi nadal mogą wymagać ręcznego wyboru ćwiczenia
lub zmiany modelu. Żaden z obecnych modeli nie gwarantuje pełnego wyniku.

### Niezależny wybór detektora gryfu i klasyfikatora ćwiczeń

Własny detektor korzysta teraz z zainstalowanego X-CLIP do rozpoznawania ćwiczeń,
bez uruchamiania DINO/SAM. Klasyfikacja używa wyłącznie kontekstu sztang przypisanych
do potwierdzonych zawodników. Nie zmienia klatek ani pomiarów własnego detektora.
Bez opcjonalnej instalacji X-CLIP analiza nadal działa, z informacją o konieczności
ręcznego wyboru ćwiczenia. Błąd zainstalowanego klasyfikatora jest zgłaszany.

Pełny przebieg aplikacji na `100kg x 5.mp4` automatycznie rozpoznał BenchPress
dla zawodnika 2 i zachował 5 powtórzeń. Wszystkie 565 klatek są identyczne z
wynikiem własnego detektora sprzed klasyfikacji. Sam dodatkowy etap trwał 13,40 s;
ponowne użycie sprawdzonego cache 1,10 s. Cache uwzględnia film, pozy, model,
kod, konfigurację i zależności oraz sprawdza integralność zapisanych predykcji.
Dowody: `bench-integrated.json`, `bench-integrated-probe.json`,
`bench-integrated-warm.json` w `artifacts/model-switch-repair`.

## Weryfikacja

- 158 testów .NET, 84 testy podstawowego Python i 47 testów Vision przeszły.
- Release publish zakończony powodzeniem; sprawdzono uruchomienie procesu aplikacji.
- Wykonano rzeczywisty przebieg `ai/pipeline.py --provider custom_barbell` z
  niedostępnym interpreterem Vision: własna analiza działa niezależnie od niego.
- Wyniki: `artifacts/model-switch-repair/bench-production-phase-report.json`,
  `batch-phase-report.json`, `exercise-recovery.json` i logi testów.
- Nowa aplikacja: `artifacts/app-model-switch/motion_trace_win.exe`.

W Visual Studio przebuduj projekt, wybierz model i ponownie przeanalizuj film.
Nie przeprowadzono automatycznej inspekcji natywnego UI.

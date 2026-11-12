# Gryf jako potwierdzenie powtórzenia — przegląd danych

**Aktualizacja 2026-09-13:** wytrenowano i wdrożono pierwszy model widocznych fragmentów gryfu, śledzenie oraz potwierdzanie powtórzeń bench press. Aktualne wyniki, ograniczenia i odtworzenie: [SHAFT_MODEL.md](SHAFT_MODEL.md). Poniżej pozostaje opis wcześniejszych etapów przygotowania danych.

Sprawdzony folder: `videos/bench`. 25 plików, 1262,6 s (21 min 2,6 s), około 4,60 GB. Wszystkie mają orientację pionową po zastosowaniu metadanych obrotu. Filmy źródłowe nie zostały zmienione. Inwentaryzacja nie jest pełną analizą AI wszystkich klatek.

## Przygotowane materiały
- `artifacts/barbell_dataset/manifest.json`: metadane, orientacja, rzeczywisty timestamp odczytanej klatki, oryginalne i przeskalowane wymiary, stan przeglądu.
- `frames/`: 200 klatek, po 8 z początku, środka i końca każdego nagrania; dłuższe filmy będą wymagały gęstszych próbek.
- `overview_1.jpg` … `overview_5.jpg`: przegląd wszystkich 25 nagrań. Obejrzano 100 klatek w zestawieniach oraz wybrane klatki w większym rozmiarze.
- `baseline/`: diagnostyczne propozycje prostych linii Hough, maks. 12 na klatkę. Nie są etykietami gryfu ani oceną prawdopodobieństwa.
- `research/barbell/seed_annotations.json`: 8 ręcznie przygotowanych przez asystenta propozycji po obejrzeniu obrazów. Status draft, nie approved. Współrzędne dotyczą widocznych odcinków części chwytowej, nie talerzy. Prostokąt zawodnika obejmuje widoczny obszar osoby, nie ukryte części ciała.
- `context/`: krótkie animowane podglądy ±1 s dla ośmiu propozycji, do oceny ruchu i przygotowania. Są próbkowane do 10 FPS, nie służą do pomiaru czasu. Pliki JSON obok zapisują timestampy źródłowe.
- `review.html`: lokalny panel poprawiania odcinków, wskazania zawodnika, stanu gryfu i kontekstu; autosave w przeglądarce, eksport/import JSON. Pierwsze 8 pozycji to propozycje do sprawdzenia. Bez uploadu i zewnętrznych zależności.

## Co wynika z obejrzanych klatek
1. IMG_0717 oraz IMG_0806–0811 zawierają gryf na stojakach przy pustej ławce, ustawianie zawodnika i późniejszą pozycję pod sztangą. To szczególnie przydatne do odróżnienia obecności gryfu od rzeczywistego repa.
2. IMG_0717 (33,47 s) pokazuje dłonie blisko siebie przy gryfie; samo zbliżenie dłoni do gryfu nie jest dowodem podnoszenia. Stan ruchu pozostawiono unknown do weryfikacji kontekstu.
3. IMG_E0821 (62,04 s) ma mocno zasłoniętą część chwytową i kilka osób wokół ławki. Oznaczono occluded; nie odtworzono domyślnie niewidocznej linii.
4. IMG_7845 zawiera ciemne ujęcie pod światło i dłonie spottera blisko gryfu. Trzeba łączyć detekcję obiektu z rolą osoby i przebiegiem czasowym.
5. 100kg x 5 ma nakładki tekstowe/graficzne; model nie może uczyć się liczby repów z napisu. Nazwy plików/folderu nie są etykietami faz.
6. Wiele filmów ma bardzo podobne tło i ustawienie kamery. Nie należy dzielić sąsiednich klatek losowo na trening i test. W manifeście zaproponowano rodziny wizualne, ale sesje nie zostały potwierdzone i split pozostaje unassigned. Wszystkie oglądane teraz filmy są materiałem rozwojowym; niezależny końcowy test najlepiej wykonać na późniejszych, nieoglądanych sesjach.

## Ocena prostego rozwiązania
Zaimplementowano wyłącznie diagnostyczny baseline: Canny + Hough, linie zbliżone do poziomu, ranking długości. Na obejrzanych wynikach zaznacza sufit, ławkę i stojaki; na IMG_0807 (23,87 s) najdłuższe linie omijają faktyczny gryf. To pokazuje, że ten konkretny prosty baseline jest niewystarczający, nie dowodzi niemożliwości każdej metody bez uczenia. Nie policzono precision/recall bez zatwierdzonych etykiet.

Następny eksperyment powinien używać detektora widocznych fragmentów gryfu z kontekstem dłoni i ciągłości czasowej. W pierwszej wersji lokalizacja gryfu ma potwierdzać kandydata z nadgarstków, a nie dostarczać m/s. Nie potrzeba wymiarów talerzy ani kalibracji użytkownika. Nie zintegrowano niezweryfikowanego baseline'u z licznikiem aplikacji.

## Schemat oznaczeń
- `shaft_segments`: lista [x1,y1,x2,y2] osi widocznych fragmentów części chwytowej. Osobne fragmenty po obu stronach zasłaniającej dłoni. To odcinki do detekcji obiektu, nie gwarantowane stałe punkty materiałowe do pomiaru jego prędkości.
- `athlete_box`: widoczny obszar właściwego ćwiczącego, albo null. Na razie nie przypisuje trwałego AthleteId ani tożsamości po powrocie.
- `bar_state`: unknown / visible_stationary / visible_moving / occluded / absent.
- `event`: przygotowanie pustymi rękami, ustawienie chwytu, unrack, rep, rerack, spotter_assist, between_sets lub unknown.
- `review_status`: unreviewed / draft / edited / approved. Puste odcinki w niezweryfikowanej klatce NIE oznaczają negatywnej próbki treningowej.

Gryf na stojakach jest dodatnią próbką wykrywania gryfu, ale ujemną próbką aktywnego powtórzenia. Pojedyncze zdjęcie nie wystarcza do oznaczenia ruchu. Dopiero po uzgodnieniu i weryfikacji przykładowych oznaczeń trzeba rozszerzyć zbiór, dodać granice zdarzeń w krótkich sekwencjach, ustalić sesje i uruchomić eksperyment treningowy. Osiem propozycji nie jest wystarczającym ani gotowym zbiorem treningowym. Nie wytrenowano jeszcze modelu.

## Odtworzenie
W środowisku motiontrace:

    python research/barbell/prepare_dataset.py
    python research/barbell/package_review.py

`prepare_dataset.py` regeneruje bazowy manifest (przed regeneracją wyeksportuj własne oznaczenia z przeglądarki). `package_review.py` dokłada wersjonowane propozycje i stronę. Otwórz `artifacts/barbell_dataset/review.html` w przeglądarce. W przypadku braku lokalnego odtwarzania MOV w przeglądarce osiem początkowych przykładów ma przenośny animowany podgląd; inne filmy można obejrzeć w MotionTrace.

## Co sprawdzić teraz
W pierwszych ośmiu pozycjach: czy zielone odcinki leżą na gryfie i nie na talerzach/stojakach, czy niebieski prostokąt obejmuje ćwiczącego, oraz — po obejrzeniu kontekstu — czy gryf faktycznie się rusza. Nie trzeba podawać długości ani średnic. Zatwierdź sprawdzone pozycje i wyeksportuj JSON. Reszta klatek pozostaje rezerwą do rozszerzenia zbioru.

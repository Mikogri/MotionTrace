# Import pierwszej weryfikacji — 2026-09-13

Zaimportowano `motiontrace-shaft-review.json`, zachowując plik źródłowy bez zmian. Sprawdzono ID, geometrię, wymiary i powiązanie z klatkami źródłowymi.

- 10 zatwierdzonych klatek, 1 edytowana bez zatwierdzenia, 189 niezweryfikowanych w eksporcie.
- W zatwierdzonych: 5 nieruchomy gryf, 2 poruszający się gryf, 1 zasłonięty, 2 stan nieustalony.
- `IMG_E0821.MOV / 62,035 s`: uwzględniono uwagę użytkownika „leg press”. Przykład wyłączony z dodatnich przykładów bench press. Nie zmieniono filmu ani nazwy folderu.
- `100kg x 5 / 9,4 s` oraz `IMG_0717 / 0,667 s`: nowe kreski nakładają się na stare propozycje. Zachowano wszystkie dane i oznaczono `geometry_review_required`; nie potraktowano ich jako niezależnych gryfów.
- `rep` wraz z `visible_stationary` nie jest automatycznie błędem: pojedyncza klatka może przedstawiać zatrzymanie w obrębie powtórzenia. Nie zmieniono etykiety użytkownika.
- `reviewed_annotations.json` zawiera przyjęte dane wraz z pochodzeniem i SHA-256 eksportu. Wszystkie mają `training_ready=false`: potrzebne są dalsze etykiety i podział sesji.
- `package_review.py` zachowuje zatwierdzone i edytowane oznaczenia zamiast nadpisywać je propozycjami asystenta; potrafi odtworzyć je z pliku reviewed_annotations po regeneracji bazowego manifestu.

Przygotowano cztery kolejne wizualne propozycje w osobnym panelu `artifacts/barbell_round2/review.html` (wyłącznie 4 pozycje, nie 200). Są to inne kąty kamery, gryf przy klatce, kontakt spottera oraz osoba przenosząca talerz obok gryfu na stojakach. Każda ma animowany kontekst ±1 s. Etykiety ruchu i zdarzenia pozostają unknown do weryfikacji. Osobny klucz localStorage chroni poprzednią pracę.

Po weryfikacji panel eksportuje `motiontrace-shaft-review-round2.json`. Import częściowej partii:

    python research/barbell/import_review.py research/barbell/motiontrace-shaft-review-round2.json

Te klatki rozszerzają próbki rozwojowe, nie stanowią niezależnego testu. Modelu jeszcze nie wytrenowano i nie zmieniono licznika w aplikacji.

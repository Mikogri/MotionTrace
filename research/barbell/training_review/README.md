# Pierwsza duża partia — lokalizacja gryfu

Otwórz `artifacts/barbell_training/review.html`. To osobna partia 300 klatek i osobny zapis przeglądarki. Wcześniejsze 14 zatwierdzonych przykładów oraz eksporty pozostają nietknięte.

## Oznaczanie
1. Zaznacz dwa końce widocznego odcinka części chwytowej gryfu. Dodaj osobne odcinki po obu stronach zasłaniającej dłoni. Nie łącz niewidocznych fragmentów.
2. Nie zaznaczaj talerzy, tulei ani zawodnika. Nie oceniaj ruchu z pojedynczego zdjęcia. Gryf na stojakach również należy oznaczyć.
3. Jeśli część chwytowa jest częściowo zasłonięta, zaznacz widoczne odcinki i wybierz odpowiednią widoczność. Całkowite zasłonięcie i brak gryfu to oddzielne etykiety; nie dopisuj wtedy odcinków. Jeśli nie umiesz rozstrzygnąć, przejdź dalej bez zatwierdzania.
4. „Zatwierdź i dalej” zapisuje klatkę i przechodzi do kolejnej. „Cofnij” usuwa ostatni punkt/odcinek; „Usuń wszystkie linie” pozwala narysować poprawkę od nowa. Powiększenie 150/200% nie zmienia układu współrzędnych zapisanych etykiet.
5. Na końcu kliknij raz „Eksport całej partii — jeden JSON”. Plik `motiontrace-shaft-training-300.json` zapisz w `C:\Work\Projects\MotionTrace\research\barbell\`.

Można przerwać: postęp zapisuje się w localStorage pod kluczem tej partii. Wróć w tej samej przeglądarce i pod tym samym adresem. Eksport przed dłuższą przerwą jest dodatkową kopią; przy zmianie przeglądarki wczytaj JSON. Eksport zawiera wszystkie 300 rekordów wraz ze statusami, nie tylko zatwierdzone.

## Dobór materiału
24 filmy bench; pominięto IMG_E0821.MOV wskazany przez użytkownika jako inne ćwiczenie. 12 klatek z każdego filmu, plus jedna dodatkowa w 12 najdłuższych filmach. Cały film dzielony jest na przedziały czasowe: w każdym wybierana jest jedna z dwóch klatek, preferując większą różnicę obrazu względem już wybranych. Porównanie obejmuje środkową/dolną część obrazu, ograniczając wpływ sufitu. To heurystyka różnorodności, nie gwarancja usunięcia każdej podobnej klatki. Rozłożenie próbek po całej długości obejmuje również przygotowanie i przerwy.

Nie powtarzamy dokładnych indeksów 200 klatek wcześniejszego przeglądu. Oryginalne pliki są tylko odczytywane. Próbki zapisano w orientacji zgodnej z metadanymi, maksymalnie 1280 px na dłuższym boku. Dla każdej zachowano timestamp, indeks klatki, oryginalne i robocze wymiary oraz ID źródłowego filmu.

Wszystkie podziały pozostają unassigned: nie dzielimy sąsiednich klatek między trening i walidację. Podział całych sesji i kontrola jakości nastąpią przed treningiem. Brak etykiet w niezatwierdzonej klatce nie oznacza negatywnej próbki. Całkowite zasłonięcie nie jest tym samym co brak obiektu.

## Format i walidacja
Schema 1 zachowuje wcześniejsze pola i dodaje dataset_id, annotation_target oraz shaft_visibility. bar_state i event pozostają unknown — ta partia uczy lokalizacji, nie ruchu. Import:

    python research/barbell/import_training_review.py research/barbell/motiontrace-shaft-training-300.json

Importer sprawdza całą partię przed zapisem, współrzędne, tożsamość klatek i zgodność zatwierdzenia z widocznością. Nie nadpisuje pliku eksportu ani wcześniejszych oznaczeń.

Przygotowanie partii: `python research/barbell/prepare_training_batch.py`. Nie regenerować rozpoczętej partii bez uprzedniego eksportu kopii. Testy logiki panelu: `node research/barbell/training_review/state_tests.cjs` (prawidłowy runtime Node, nie systemowy plik o nazwie node).

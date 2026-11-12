# Squat / deadlift: pierwszy przegląd jakości

Znaleziono 26 nagrań squat i 8 deadlift. Sprawdzono obecny shaft-v1 na 3 klatkach każdego filmu (25%, 50%, 75% czasu): squat 59/78 klatek z co najmniej jedną detekcją, deadlift 19/24. To częstość wykrycia kandydata, nie precision/recall. Nie zakładamy obecności widocznego gryfu na każdej klatce. Podgląd pierwszych arkuszy wykazał błędne linie na stojakach oraz brak detekcji na części ujęć. Nie wyznaczono dokładności całego zestawu.

Wyniki i arkusze: artifacts/new-exercises-baseline. Reprodukcja: python research/barbell/probe_new_exercises.py w środowisku motiontrace. Skrypt wykonuje inference istniejącego modelu; nie zmienia wag ani filmów.

Osobny formularz artifacts/shaft-squat-deadlift-review/review.html zawiera 102 klatki. Zaznaczać widoczne odcinki części chwytowej gryfu, nie talerze/tuleje ani domyślne przebiegi pod zasłonięciem. Wybrać widoczność. Eksport całej partii zapisuje jeden motiontrace-shaft-squat-deadlift.json. Timestamp jest z PTS; frame_index jest przybliżeniem timestamp*FPS i nie jest przeznaczony do oceny granic faz. Nie regenerować rozpoczętej partii.

Plan oceny/treningu:
1. Zweryfikować nowe oznaczenia, pogrupować filmy z tej samej sesji/kamery. Całe grupy wydzielić do walidacji/testu, nie losować sąsiednich klatek do różnych zbiorów.
2. Dotrenować detektor na mieszance bench/squat/deadlift, zachowując bench jako test regresji. Dodać negatywne przykłady stojaków, przygotowania i zasłonięć.
3. Porównać lokalizację linii z ręcznymi oznaczeniami i ciągłość na pełnych filmach. Nie zastępować dotychczasowych wag, dopóki wynik nie przejdzie porównania.
4. Oddzielnie naprawić przypisywanie gryfu: obecny shaft_tracking.py odrzuca nadgarstki poniżej barków jako spottera bench. Ta reguła nie nadaje się dla deadliftu, a bywa błędna dla squat.
5. Rozpoznawanie ćwiczenia obecnie ma tylko BenchPressClassifier / Unknown. Folder oznacza etykietę materiału, nie powinien być sygnałem runtime. Nowy klasyfikator wymaga sekwencji, relacji gryf–barki–biodra i walidacji dla innych ćwiczeń.
6. Oznaczyć PTS początku/końca faz na pełnych powtórzeniach. Mierzyć błąd granic, pominięcia i fałszywe repy. Deadlift powinien mieć osobną kolejność lift–lockout–lowering i rozróżnienie dead-stop/touch-and-go; obecna obsługa pierwszego podnoszenia nie wystarcza.

Dokładność prędkości: stabilne śledzenie tego samego gryfu, korekta ruchu kamery, filtrowanie z kontrolą opóźnienia oraz odrzucanie niepewnych pików. Jednostki pozostają px/s; bez skali i odniesienia nie można potwierdzić dokładności m/s.

Nie uruchomiono treningu i nie zmieniono klasyfikatora ani reguł faz na podstawie nieoznaczonych próbek. UI: tytuł rozszerzony na Mica, spinner/procent na przyciemnionym video wyłącznie podczas IsAnalyzing. Narzędzie automatyzacji pulpitu dwukrotnie zgłosiło „accessibility window-opened handler did not become ready”; wizualna kontrola aplikacji pozostała niewykonana.

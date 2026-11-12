# Wybór zawodników i ćwiczenia

Build: `artifacts/app-exercise-notice/motion_trace_win.exe`.

- Select all / Clear all zmieniają całą listę; pozostaje indywidualny wybór. `AthleteSelection` dopuszcza teraz pusty zestaw zaznaczonych osób, ale nadal wymaga niepustego zestawu dostępnych ID przy tworzeniu.
- Przy pustym zaznaczeniu aplikacja czyści pomiary i wyłącza eksport. Przy odznaczeniu aktualnej osoby wybiera pierwszą pozostałą zaznaczoną osobę, jeżeli taka istnieje.
- Athlete for movement jest aktywne zawsze, gdy lista ma elementy, również dla źródła Barbell. Dostawca trajektorii otrzymuje wybrane ID zamiast 0 (wszystkie tory). Tory przypisane do innych osób są odrzucane; tory bez ustalonego właściciela zachowują dotychczasowe traktowanie i mogą pozostać niejednoznaczne.
- Po analizie i przy zmianie zawodnika Exercise wybiera najczęściej rozpoznane obsługiwane ćwiczenie z jego osi klasyfikacji. Unknown pozostawia pusty wybór i prosi o ręczne wskazanie ćwiczenia. Zmiana czasu odtwarzania ani źródła pomiaru nie nadpisuje ręcznego wyboru.
- Obecny klasyfikator rozpoznaje BenchPress / Unknown. Obsługa wartości Squat i Deadlift w domyślnym wyborze nie oznacza dodania nowego klasyfikatora.
- Overlay nie rysuje gryfu przypisanego do odznaczonej osoby; przy odznaczeniu wszystkich nie rysuje też nieprzypisanego gryfu. Odznaczone osoby nie mają tagu, ramki ani szkieletu na nagraniu; można je ponownie zaznaczyć na liście Athletes.
- Jeżeli wybrany zawodnik nie ma rozpoznanego lub ręcznie wybranego ćwiczenia, nad listą Exercise pojawia się ostrzeżenie InfoBar z prośbą o ręczny wybór. Znika po wybraniu ćwiczenia, odznaczeniu zawodnika lub usunięciu wyników przy imporcie nowego filmu.

Weryfikacja: 93/93 testy .NET, publish WinUI Release x64 zakończony powodzeniem. Interakcje w działającym oknie nie zostały zweryfikowane narzędziem UI.

# Powiązanie zawodnika z gryfem — silnik 0.8.0

Nowa analiza zapisuje schemaVersion 3 i tablicę `shafts` w każdej klatce.
Aplikacja nadal odczytuje wcześniejsze formaty 1 i 2. Starsze aplikacje odrzucą
nowy format zamiast pominąć wiele sztang i pokazać niepełne pomiary.

## Działanie

Detektor gryfu jest wspólny dla wszystkich sztang. Każdy gryf otrzymuje własne ID,
śledzenie LK oraz ruch skompensowany o ruch kamery. Dopasowanie detekcji jest
wzajemnie jednoznaczne; odległe współliniowe gryfy nie są automatycznie sklejane.
Przed utratą ID tracker próbuje odzyskać detekcję; nie emituje starych obserwacji
po przekroczeniu limitu 150 ms bez potwierdzenia.

Powiązanie z osobą wymaga anatomii zgodnej z chwytem/położeniem gryfu i zgodnego
ruchu w oknie do 1,5 s. Samo stanie obok lub ruch kamery nie wystarcza. W bench
pozycja leżącego zawodnika pomaga wykluczyć stojącego spottera. Niejednoznaczne
osoby lub dwie równie prawdopodobne sztangi pozostają nieprzypisane.

Potwierdzona para ma pierwszeństwo. Zasłonięte dłonie nie odbierają przypisania,
jeżeli ten sam zaobserwowany gryf pozostaje przy tej samej śledzonej osobie.
Po analizie można odzyskać wcześniejsze klatki tego samego ciągłego śladu, gdy
zawodnik pozostawał przy gryfie. Uzupełnianie nie tworzy pozycji ani ruchu,
nie łączy sprzecznych właścicieli i respektuje niejednoznaczne przypisania.

Każda osoba może mieć najwyżej jeden przypisany gryf w klatce. Wykres, potwierdzanie
repów i eksport używają gryfu tej osoby. Obce i nieprzypisane sztangi nie wpływają
na punkt odniesienia jej pomiaru.

Flaga `isExerciseParticipant` steruje domyślnym zaznaczeniem. Pozostałe osoby są
dostępne do ręcznego wyboru, lecz domyślnie nie mają overlayu ani pomiarów w widoku.
Ręczne zaznaczenie osoby nie wymusza przypisania niepewnego gryfu. Gdy nie ma
potwierdzonej pary, aplikacja pokazuje odpowiedni komunikat.

## Weryfikacja i ograniczenia

Sprawdzono pełne 1627 klatek trzech dostępnych nagrań. Osobne scenariusze testowe
obejmują dwie równoczesne pary, przechodnia, spottera, różny ruch osoby i gryfu,
ruch samej kamery, niejednoznaczność, krótkie utraty detekcji, filtrowanie eksportu
i izolację pomiaru od obcych gryfów. Nie mamy tu oznaczonego rzeczywistego nagrania
dwóch jednocześnie ćwiczących osób; ten przypadek sprawdzono na danych syntetycznych.

| Nagranie | Automatycznie wybrane ID | Repy z gryfu przed / po |
|---|---|---|
| bench/100kg x 5.mp4 | 2, 3; spotter 1 odznaczony | 4 / 3 |
| squat/VID_20260420_175856~2.mp4 | 1; pozostałe odznaczone | 0 / 0 |
| deadlift/VID_20260214_210811~2 (1).mp4 | 1; pozostałe odznaczone | 1 / 1 |

To wyniki obecnego algorytmu faz z trajektorii gryfu, nie ręcznie oznaczona liczba
rzeczywistych powtórzeń. Na trudnym bench tracker osoby nadal rozdziela zawodnika
na ID 2 i 3; ostrzejsze przypisanie odrzuca jedno wcześniej akceptowane powtórzenie.
Nie scalono tych tożsamości bez dowodów. Squat nadal wymaga poprawy detekcji gryfu
i ciągłości trajektorii. Mechanizm parowania nie naprawia niewidocznego/źle wykrytego
gryfu i nie jest pełnym ReID po długiej nieobecności zawodnika.

Surowe pomiary: `artifacts/motion-pairs-validated/`. Modele i ich wagi pozostały
bez zmian; nie było ponownego treningu. Cache pozy nadal jest wykorzystywany.

Weryfikacja końcowa: 58 testów Python, 119 testów .NET, pełny przebieg schema3
bench z odczytem przez C# i sprawdzeniem relacji jeden-do-jednego; publish WinUI
Release x64 zakończony powodzeniem. Nie wykonano ręcznej kontroli GUI.

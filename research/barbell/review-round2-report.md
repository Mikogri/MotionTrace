# Druga weryfikacja i eksperyment ruchu — 2026-09-13

Zaimportowano `motiontrace-shaft-review-round2.json`: 4/4 zatwierdzone klatki. Sprawdzono, że wszystkie pola użytkownika zostały zachowane dokładnie, a 10 wcześniejszych zatwierdzeń pozostaje w zbiorze. Oryginalnych eksportów nie zmieniono.

Łącznie: 14 approved i 1 edited. Zatwierdzone stany: 7 stationary, 4 moving, 1 occluded, 2 unknown. Dwa wcześniej wykryte konflikty nakładających się odcinków nadal są oznaczone do przeglądu; przykład innego ćwiczenia nadal wyłączono z dodatnich przykładów bench press.

## Eksperyment pomocniczy
`motion_probe.py` bada lokalny optical flow w pobliżu odcinków zaznaczonych przez użytkownika. To lokalizacja podana z góry, NIE automatyczny detektor gryfu. Nie używa talerzy, jednostek fizycznych ani kalibracji wymiarów. Śledzi narożniki w pasie 9 px wokół odcinków, sprawdza spójność śledzenia w przód i wstecz oraz odejmuje medianę ruchu punktów w górnych 35% obrazu jako przybliżenie ruchu kamery. Sprawdza cztery przesunięcia czasu: −0,4, −0,2, +0,2, +0,4 s od klatki oznaczonej. Brak wystarczających punktów daje unknown. Próg ruchu pionowego: max(3 px, 2,5% poziomego rozpięcia oznaczonych fragmentów).

Wzięto 9 zatwierdzonych przykładów moving/stationary bez konfliktów geometrii i innego ćwiczenia:

| Etykieta użytkownika | Wynik moving | Wynik stationary | Unknown |
|---|---:|---:|---:|
| moving (4) | 2 | 2 | 0 |
| stationary (5) | 0 | 5 | 0 |

Dwa pominięcia: IMG_7845 / 21,307 s oraz VID_20251014_204427~2 / 10,340 s. Przykład IMG_0432 przekracza próg tylko nieznacznie. Nie stroiliśmy progu na tych przykładach po odczytaniu wyników.

To mały test rozwojowy z lokalizacją podaną przez człowieka, nie niezależny benchmark i nie dokładność detekcji repów. Okno testowe 0,8 s jest węższe niż 2-sekundowy kontekst dostępny podczas oznaczania. Rozbieżności mogą wynikać ze śledzenia nieodpowiednich cech, gładkiego/zasłoniętego gryfu, progu lub różnego zakresu czasowego etykiety. Nie wolno automatycznie uznać, że etykiety użytkownika są błędne ani że brak optycznego ruchu dowodzi bezruchu sztangi.

## Decyzja
Nie włączać tej metody jako twardej bramki zaliczającej repy: pomija połowę czterech dodatnich przykładów mimo znanej lokalizacji. Potrzebny detektor gryfu oraz testy sekwencji z redetekcją i oceną niepewności. Obecny mały zbiór pozwala testować założenia, nie uzasadnia jeszcze wdrożenia wytrenowanego modelu. Potwierdzenie gryfem ma wspierać kandydatów z nadgarstków, z rozróżnieniem stationary / moving / unknown; nie zastępować braku obserwacji etykietą stationary.

Wyniki zapisano w `motion_probe_results.json` i `.csv`. Aplikacji ani dotychczasowego licznika nie zmieniono. Nie przygotowano kolejnej prośby o ręczne etykietowanie w tej partii.

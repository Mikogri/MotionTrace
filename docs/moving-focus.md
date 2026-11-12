# Ruchomy obszar analizy — silnik 0.9.0

Po potwierdzeniu pary zawodnik–gryf detektor otrzymuje dodatkowe zbliżenie.
Obszar obejmuje aktualną sylwetkę, widoczne fragmenty gryfu i margines. Podąża
za zmianą pozycji osoby, w tym cofaniem i ruchem w bok. Rozszerza się natychmiast,
a kurczy stopniowo. Każdy potwierdzony zawodnik ma niezależny obszar.

Po krótkiej utracie przypisania margines rośnie; po 750 ms bez odnowienia para
traci lokalny obszar. Brak śledzonej osoby wyłącza lokalne wycięcie. Pełny kadr
jest nadal analizowany z dotychczasową częstotliwością, aby zachować wykrywanie
nowych osób i kolejnych sztang. Nie zmieniono wyświetlania filmu w aplikacji.

Wszystkie lokalne detekcje wracają do współrzędnych oryginalnego filmu. LK i
kompensacja ruchu kamery pracują nadal w stałym układzie pełnego kadru. Ruch
samego obszaru nie jest pomiarem ruchu sztangi.

Ta wersja zachowuje ostrożne zabezpieczenie: lokalny gryf musi pasować do
wcześniejszego śladu i mieć zgodne potwierdzenie w pełnym kadrze. Niejednoznaczne
lokalne detekcje oraz znaczne skrócenie widocznego gryfu nie zastępują wyniku
globalnego. Chroni to przed przejęciem sztangi w tle. Nie oznacza to jeszcze
odzyskiwania gryfu całkowicie niewykrywalnego na pełnym obrazie.

## Weryfikacja

65 testów Pythona przechodzi, w tym siedem testów ruchomych obszarów: podążanie
za osobą, dwa osobne obszary, powiększanie po utracie, mapowanie współrzędnych,
nieruchoma sztanga podczas przesuwania obszaru, obcy gryf oraz pełne wyszukiwanie.

Pełne 1627 klatek trzech filmów przeliczono z cache pozy. Odczyt przez C# i
obliczenie trajektorii/repów zakończyły się powodzeniem.

| Film | Lokalne wywołania / zaakceptowane | Repy z gryfu przed / po |
|---|---:|---:|
| Bench 100kg x 5 | 78 / 22 | 3 / 3 |
| Squat VID_20260420_175856~2 | 87 / 0 | 0 / 0 |
| Deadlift VID_20260214_210811~2 (1) | 58 / 7 | 1 / 1 |

Zaakceptowana detekcja oznacza zgodność kontroli, nie ręcznie potwierdzoną poprawę
dokładności. Dotychczasowe ograniczenia faz, wykrywania gryfu w squat i podziału
tożsamości zawodnika na trudnym bench nadal występują. Dodatkowa inferencja lokalna
może wydłużyć analizę; zmiana służy dokładniejszemu odczytowi, nie gwarancji szybkości.
Nie zmieniono modeli ani nie wykonano treningu.

Profile, wyniki i pomiary: `artifacts/focused-shaft-evaluation/`.

# Dwa punkty — TAPNext++

Od 23.09.2026 po pierwszym wczytaniu nagrania lokalny `shaft-v1.pt`
wykrywa gryf na pierwszej klatce i proponuje końce najdłuższego wiarygodnego
odcinka (ranking długość × confidence). To jednorazowe zaznaczenie;
dalsze śledzenie wykonuje TAPNext++. `Undo point` i `Clear points` pozwalają
poprawić propozycję ręcznie. Istniejące zaznaczenia i zapisane wyczyszczenie
nie są zastępowane. Brak detekcji lub niedostępny model pozostawia ręczny tryb.

## Poprawka śledzenia i drgań (22.09.2026)

Dla dwóch punktów adapter analizuje stały obszar wokół obu zaznaczeń,
z szerokim zapasem na ruch: bok co najmniej 60% krótszego wymiaru filmu
lub trzykrotność odległości między punktami. Obszar mieści się w obrazie.
Nie zmieniamy układu współrzędnych pod pamięcią rekurencyjną modelu.
Predykcje są przeliczane z powrotem na piksele całego nagrania; wyjście poza
obszar analizy nie jest poprawnym pomiarem. Metadane `sourceRegionXYWH`
pozwalają odtworzyć użyty obszar. Oficjalne współrzędne modelu pozostają
256×256 również przy wejściu 512×512.

Po analizie nakładka pokazuje pozycje z aktualnej klatki zamiast znaczników
inicjalizacji. Przełącznik `Pose` ukrywa sylwetkę, ale nie punkty sztangi.
Filtr pomiarów środka pary tłumi drgania do 0,1% wysokości obrazu przed
różniczkowaniem, zachowuje surowe dane i powolny ruch narastający w czasie.
Nie łączy przerw widoczności. Pole `Clear movement` usunięto z widoku.

Punkty mają wypełnienie o kryciu 35% i obramowanie 70%; powiadomienie
ma pomarańczowe tło Acrylic o kryciu 30% i obramowanie 60%.

Weryfikacja na pełnym `IMG_0809.MOV` (1560 klatek), z punktami użytkownika
z klatki 0: poprzedni wynik był niemal nieruchomy i miał 0 repów. Analiza
obszaru dała 1408 wspólnych pomiarów i po poprawce zakończenia wyciskania
2 repy: 40,168–41,035 s oraz 41,102–42,035 s. Detektor potwierdza też
zakończenie przy małym, utrzymanym ruchu odkładania dopiero po powrocie do
górnej pozycji; nie dopisuje faz w przerwach widoczności. To wynik jednego
trudnego filmu, nie ogólna walidacja dokładności. Śledzenie nadal może tracić
punkt przy zasłonięciu lub wyjściu poza analizowany obszar.

Testy: 189 .NET, 130 Python, 14 kontroli diagnostycznych WinUI. Diagnostyka
sprawdza transformacje, zmianę pozycji nakładki oraz utrzymanie fokusu;
nie symuluje fizycznych kliknięć myszą. Materiał porównawczy i logi znajdują
się w `artifacts/tap-motion-repair`. Po aktualizacji trzeba ponowić analizę,
ponieważ stare wyniki nie zawierają poprawionych trajektorii.

Aktualny interfejs udostępnia tylko oficjalny TAPNext++ PyTorch. Poprzednie
adaptery i modele pozostają w repozytorium do badań; nie są uruchamiane dla
nowego celu z dwoma punktami i nie można ich wybrać w aplikacji.

## Obsługa

1. Wczytaj film i zatrzymaj go na klatce, na której widać dwa stabilne,
   fizyczne punkty sztangi, np. osie końców tulei. Analiza punktów zaczyna
   się od tej klatki; nie śledzi wstecz.
2. Przybliż kółkiem myszy lub przyciskiem `+`. Przesuwaj powiększony obraz
   prawym albo środkowym przyciskiem. `Fit` przywraca cały obraz.
3. Kliknij dwa punkty na tej samej klatce. Żółty komunikat znika po zapisaniu
   obu punktów. `Undo point` usuwa ostatni, `Clear points` usuwa oba.
4. Kliknij `Analyze video`. Postęp pojawia się na środku przyciemnionego filmu.

Zaznaczenia są zapisywane w `tapnext-targets` w katalogu danych aplikacji.
Stare `comparison-targets` nie są nadpisywane. Zmiana punktów unieważnia
poprzedni wynik dla tego celu. Zapis punktów musi zakończyć się przed analizą.

## Pomiar i eksport

Jedno wywołanie modelu śledzi dwa niezależne zapytania. Wynik zachowuje
współrzędne x/y w pikselach oryginalnego obrazu, indeks punktu, wspólną grupę,
widoczność i jej surowe logity/prawdopodobieństwo. Przy braku pewnego zawodnika
powstaje właściciel `Marked barbell`; można ręcznie wskazać ćwiczenie.

Obecna krzywa ruchu używa środka pary, wyłącznie gdy oba punkty są widoczne
i poprawne. Utrata jednego punktu przerywa ciągłość pomiaru. Nie zastępujemy
środka drugim punktem ani pozycją nadgarstka. Istniejący filtr, prędkość i
detektor faz pracują na tej trajektorii. Bez fizycznej kalibracji prędkość
jest w px/s, nie m/s. Widoczność nie gwarantuje poprawnego śledzenia.

Eksport ZIP zawiera dodatkowo `points.csv`: oba punkty, również surowe x/y
punktu niewidocznego, z pustymi kolumnami poprawnego pomiaru w takim przypadku.
Eksport obejmuje tylko zaznaczonych zawodników. `analysis.json` zachowuje
metadane pary i surowe obserwacje; dotychczasowe `samples.csv` i `reps.csv`
dotyczą przetworzonego ruchu.

## Oficjalna implementacja i rozdzielczość

Źródła: [Google DeepMind TAPNext++](https://github.com/google-deepmind/tapnet/blob/main/tapnet/tapnextpp/README.md)
i [oficjalne checkpointy](https://huggingface.co/google/tapnet).
Szczegóły przypiętych rewizji i środowiska: [tap-point-trackers.md](tap-point-trackers.md).

Domyślnie używany jest `tapnextpp_ckpt.pt`, 256×256. Ustawienia backendu
`TapNextResolution` (256 albo 512) i `TapNextCheckpoint` (opcjonalna ścieżka)
pozwalają później przetestować oficjalny `tapnextpp_512.ckpt`. Ścieżka względna
jest rozwiązywana względem katalogu modeli punktowych. Wariant musi pasować
do oficjalnej sumy SHA256. Rozdzielczość i checkpoint należą do klucza cache.
Brak pliku lub niezgodność kończy się błędem, bez podmiany trackera.

W tej zmianie rzeczywiście uruchomiono wariant 256; 512 sprawdzono testami
konfiguracji i metadanych, bez pobierania oraz benchmarku GPU.

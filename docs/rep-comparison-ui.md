# Panel repów i wspólny wykres

## Wybór i playback
Lewa kolumna zawiera selector numer + czas, podsumowanie oraz jeden wykres. Kliknięcie numeru aktywuje rep, wybiera wyłącznie jego serię, ustawia Time i przewija wstrzymany film do początku. Checkbox Compare dodaje/usuwa serię bez seekowania. Select all i Clear także nie przesuwają filmu. Przy przejściu do porównania co najmniej dwóch repów domyślna oś zmienia się na ROM %. Powrót do jednego ustawia Time; użytkownik może zmienić oś ręcznie.

RepSelectionState rozdziela ActiveRep (ostatni jawnie aktywowany numer) i Selected. Checkboxy mogą pozostawić ActiveRep poza zestawem porównania: przycisk „Play from rep N” jednoznacznie wskazuje, który rep będzie odtwarzany. Clear oraz zmiana źródła analizy resetują aktywny rep i wybór. Początkowe zaznaczenie pierwszego wyniku po analizie nie przewija filmu.

## Dane i metryki
RepChartData tworzy kolekcję MotionChartSeries wskazującą istniejące MovementPoint: bez utrzymywania kopii całej trajektorii. Time używa zakresu całego repa, ROM istniejącego widoku punktów Lifting. RepMetricsPresenter pokazuje całkowity czas, opuszczanie, pauzę, czas koncentryczny oraz średnią i szczytową prędkość fazy koncentrycznej. Jednostki pozostają px/s; brak kalibracji i detekcji sztangi. Nie dodano pozornej metryki velocity loss ani minimalnej prędkości, której interpretacja przy zatrzymaniu na końcu byłaby myląca. Porównanie pokazuje najkrótsze/najdłuższe podnoszenie w sekundach, nie ranking siły.

## ROM
ROM dotyczy wyłącznie fazy koncentrycznej nadgarstka, nie czasu ani prawdziwej sztangi:

`ROM% = 100 * (Y_bottom - Y_sample) / (Y_bottom - Y_top)`

Współrzędna Y obrazu rośnie w dół. Początek podnoszenia ma 0%, koniec 100%; wynik jest ograniczony do tego zakresu. Każdy rep ma własne punkty odniesienia. Zakres nieprzekraczający 1 px jest oznaczany jako niedostępny. Cofnięcie nadgarstka cofa również X — dane nie są sortowane według ROM ani sztucznie wymuszane jako monotoniczne. Dlatego niepewne detekcje mogą dać pętle. Time pokazuje cały rep, od 0 s własnego początku, z ujemną prędkością opuszczania i dodatnią podnoszenia. Height to wysokość względem dolnej pozycji danego repa.

## Wykres i synchronizacja
PlaybackChart przyjmuje wiele neutralnych serii, rysuje wspólne osie i legendę. Id serii składa się z SourceVideoId i RepId; DisplayName jest oddzielną etykietą. SourceVideoId to obecnie pełna lokalna ścieżka pliku. W przyszłym Compare Video można przekazać serie innych nagrań i wskazać aktualnie odtwarzany SourceVideoId bez zmiany modelu wykresu. Nie dodano drugiego odtwarzacza ani nieaktywnego przycisku Compare Video — w zastanym kodzie nie było tej akcji.

Podczas playbacku i scrubbingu aktualizowane są tylko istniejące Line/Ellipse i tekst odczytu. Geometry jest budowana przy zmianie danych, wybranych repów, metryki, osi lub rozmiaru. Timestamp wyszukuje próbkę binarnie przez PlaybackSampleLookup; interpolacja nie przechodzi przez luki. W ROM marker używa położenia tej próbki, a w Time czasu od początku repa. Poza wybraną fazą/repem marker znika. Tolerancja granic 1 µs uwzględnia zaokrąglenie Position przez MediaPlayer, nie uzupełnia brakujących klatek. Przełączniki wykresu nie dotykają silnika AI ani źródła video.

## Uproszczenia UI
Usunięto dwa stale widoczne wykresy fazowe, prawy dropdown repów i powielone metryki. Exercise, athlete selection, status i parametry pomiaru pozostają po prawej. Film pozostaje pośrodku; boczne kolumny mają ograniczoną szerokość, a panel analizy przewija się przy braku wysokości. Dla poziomego filmu zachowano wykres pod filmem. Spinner przy Analyze i Cancel pozostają. Bar Path nie został dodany: zastany wykres nie miał trajektorii X/Y, a wynik MovementPoint przechowuje jedynie pionową trajektorię. Nie przedstawiono ruchu nadgarstka jako pomiaru toru sztangi.

## Weryfikacja
67 testów .NET przeszło, w tym nowe testy wyboru, ROM opartego na przemieszczeniu, różnej długości repów, braku kopiowania źródła, luk, seekowania i tożsamości serii z dwóch źródeł. Build bez błędów i ostrzeżeń. W UI sprawdzono brak seeka po dodaniu drugiej serii, dwie linie/legendę/ROM oraz seek do początku po kliknięciu numeru. Testowy klip zawiera fałszywych kandydatów ruchu spottera; weryfikacja UI nie dowodzi poprawności detekcji powtórzeń.

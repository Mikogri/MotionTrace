# IMG_0809: ciągłość gryfu i kompletność analizy

## Przyczyna

Film `F:/Bench press/Speed bench press 60kg (50%)/IMG_0809.MOV` ma 1560
poprawnie dekodowanych klatek, koniec prezentacji 52,001667 s. Nie wystąpił brak
klatek źródłowych. Własny detektor widział gryf w dolnej pozycji jako kilka
fragmentów. Niejednoznaczność dopasowania przerywała trajektorię na 0,4 i 0,3 s
właśnie w dolnych fazach dwóch powtórzeń. Po odłożeniu sztangi ruch samych dłoni
nie jest kolejnymi powtórzeniami; wcześniejsza hipoteza o śledzeniu tła w tej
części filmu nie potwierdziła się podczas inspekcji obrazu.

## Zmiany

- Dopasowanie fragmentów uwzględnia dominujące pokrycie poprzednio widzianego
  odcinka: minimum 50%, ponad dwukrotnie większe niż drugiego kandydata.
  Kandydaci muszą leżeć na wspólnej osi, a dopasowanie pozostaje wzajemnie
  jednoznaczne. Osobne równoległe sztangi nadal nie są łączone.
- Nie zwiększono dopuszczalnych przerw w pomiarze ani nie interpolowano dołów.
  Obecna segmentacja obsługuje szybkie serie bez pauzy; dodano testy regresji.
- DINO przy braku potwierdzonego właściciela wykonuje dodatkowe wykrywanie
  w obszarach poruszających się zawodników, maksymalnie 2 razy/s/osobę.
  Obowiązują wcześniejsze wymagania zgodności ruchu i pewności przypisania.
- Uszkodzony lub niepełny pełny cache jest odrzucany, aby wykonać analizę ponownie.
  Sprawdzane są uporządkowanie i poprawność czasu oraz pokrycie zapisanej długości.
  Zapis wyników Vision wymaga dokładnie jednej listy obiektów na każdą klatkę.
- Naprawiono kontrolę końca strumienia z niezerowym czasem startowym i odrzucanie
  strumieni bez prezentowanych klatek. Zmienna liczba klatek/s i edycje MOV nie
  są uznawane automatycznie za uszkodzenie.
- Brak potwierdzonego zawodnika jest sygnalizowany ostrzeżeniem w aplikacji;
  nie jest przedstawiany zielonym statusem udanego pomiaru.

## Weryfikacja

Replay własnego modelu z identycznymi zapisanymi pozami:
- wcześniej 1541 klatek z gryfem, 3 odcinki trajektorii i 0 repów;
- po poprawce 1560 klatek z gryfem, 1 odcinek trajektorii i 2 repy;
- rep 1: opuszczanie 0,600 s, podnoszenie 0,467 s;
- rep 2: opuszczanie 0,367 s, podnoszenie 0,533 s.

To pomiary algorytmu, nie niezależna walidacja dokładności czasów. Replay
obejmował rzeczywisty detektor na GPU i wszystkie klatki filmu, przy zachowanych
wcześniejszych pozach. Pliki: `artifacts/0809-repair/custom-fixed.json` oraz
`custom-fixed-metrics.json`.

DINO: rzeczywisty etap wykrywania zwiększył liczbę klatek z przypisanym kandydatem
z 0 do 43. Sam ten etap nie potwierdza jeszcze jakości śledzenia SAM ani repów.

Nie można zagwarantować pomiaru z każdego uszkodzonego lub nieczytelnego filmu.
Błąd dekodowania ma być jawny; brak dowodu ruchu nie może tworzyć fikcyjnych repów.

Weryfikacja kodu: 161 testów .NET, 101 testów podstawowego Python i 52 testy Vision przeszły. Release publish i uruchomienie procesu aplikacji zakończyły się powodzeniem. Wersja: artifacts/app-0809-repair/motion_trace_win.exe. Nie przeprowadzono automatycznej inspekcji natywnego UI.

Pełny diagnostyczny przebieg SAM/X-CLIP na odzyskanych kandydatach:
1560 zachowanych klatek, 1410 klatek ze śledzonym obiektem, automatyczny BenchPress.
Proxy obiektu pozostaje jednak rozbite na 42 odcinki (1345 próbek pomiarowych)
i nie daje kompletnych repów z maski. Nie poluzowano walidacji, aby ukryć ten problem.
Sama część SAM/X-CLIP trwała 471,12 s; DINO 95,86 s. Na tym filmie zalecany
jest własny detektor MotionTrace. To ograniczenie DINO/SAM pozostaje jawne.
Pliki: artifacts/speed-bench-repair/dino-recovered.json oraz
artifacts/0809-repair/dino-fixed-metrics.json, dino-fixed-exercise.json.

Pełny produkcyjny przebieg ai/pipeline.py --provider custom_barbell, świeży cache:
1560 klatek, 1560 obserwacji gryfu, ciągła przypisana trajektoria, 2 repy,
automatyczny BenchPress z X-CLIP i zgodne awaryjne rozpoznanie z anatomii/ruchu.
Czasy faz są identyczne z replayem. Metadane: 142,22 s etap pozy/gryfu,
46,64 s klasyfikacja (nie jest to całkowity czas procesu ze startem interpreterów).
Dokładny koniec52,001667s, ostatnia klatka0,033333s. Wyniki: production.json,
production-metrics.json, production-exercise.json w artifacts/0809-repair.

Regresja rzeczywistego detektora na 100kg x 5.mp4: nadal 5/5 repów (bench-regression-metrics.json). Ponowne pełne uruchomienie IMG_0809 z cache zachowało identyczne klatki i predykcje klasyfikatora.

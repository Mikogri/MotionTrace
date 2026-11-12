# Odzyskiwanie ciągłości zawodnika i gryfu — 22.09.2026

## Diagnoza

W `videos/bench/100kg x 5.mp4` ostatnia obserwacja zawodnika ID2 była w
11,733 s. Ta sama osoba wracała w 12,767 s, ale otrzymywała ID3. Przerwa
1,033 s przekraczała dotychczasowe okno jednej sekundy. Dodatkowo zapamiętana
prędkość ramki sylwetki wynosiła około (-950, -231) px/s: po zasłonięciu jej
ekstrapolacja przesuwała przewidywaną ramkę o (-380, -92) px. To szum ramki
detektora, a nie dowód rzeczywistego przemieszczenia zawodnika.

Rzeczywista ramka powracającej osoby miała IoU 0,645 z ostatnią obserwacją,
a odległość zapisanych histogramów wyglądu wynosiła 0,103. Przewidywana ramka
miała natomiast IoU tylko 0,276. Zapisano wszystkie 565 rzeczywistych detekcji
do deterministycznego odtwarzania trackera, bez ponownego uruchamiania modeli.

SAM przerywał pomiar w 12,233 s, dokładnie 0,5 s od ostatniej widoczności
właściciela. Czwarty rep nie miał wystarczającej obserwacji zatrzymania,
a piąty nie miał już przypisanej trajektorii. Sam próg wykrywania faz nie był
przyczyną tego błędu. Pozostałe zdiagnozowane braki opisuje
`artifacts/rep-diagnosis/diagnosis.md`.

## Zmiany

- Potwierdzona tożsamość może zostać odzyskana do dwóch sekund. Po zwykłym
  oknie jednej sekundy porównujemy ostatnią obserwowaną ramkę, bez starej
  prędkości. Wymagane są silny overlap, zgodny wygląd i brak niejednoznaczności.
  Dłuższe nieobecności i inne osoby nie otrzymują automatycznie starego ID.
- Vision zachowuje pomiar obserwowanej sztangi podczas krótkiej utraty sylwetki
  tylko przy potwierdzonym późniejszym powrocie tego samego ID w dwóch sekundach.
  Nadal obowiązują pewność maski, geometria i bliskość obu obserwacji właściciela;
  dodatkowo IoU kolejnych ramek >=0,6 i kontrola maski względem tułowia przed/po
  przerwie. Maska odrzucona jako tułów nadal wymaga nowego promptu.
- Własny tracker może uzupełnić samo przypisanie obserwowanej sztangi między
  potwierdzonymi obserwacjami tego samego właściciela. Brak gryfu, przerwa >0,15 s
  między jego obserwacjami, niejednoznaczność lub różni właściciele blokują naprawę.
- Nie generujemy brakujących pozycji ani nie zmieniamy progów faz w C#.
  Nowe źródła i wersja trackera unieważniają stare wyniki cache.

## Świeża weryfikacja bench

Przeliczono ponownie rzeczywisty film: RTMDet/RTMPose i wszystkie trzy warianty
wykrywania gryfu. Wspólny analizator C# jest identyczny z wcześniejszym benchmarkiem.
Dla porównania faz ustawiono ręcznie BenchPress; obecny X-CLIP również sam
rozpoznał BenchPress u ID2, a ID1 (spotter) pozostał Unknown i nie jest uczestnikiem.

| Wariant | Dopasowane repy przed | Dopasowane repy po | MAE granic po |
|---|---:|---:|---:|
| DINO/SAM2 | 3/5 | **5/5** | **0,035 s** |
| Własny wdrożony v1 | 3/5 | 4/5 | 0,0354 s |
| Kandydat wieloćwiczeniowy v2 | 3/5 | 4/5 | 0,0438 s |

MAE dotyczy znalezionych granic, więc warianty z brakującym repem nie mają
porównywalnego mianownika. Maksymalny błąd granicy obecnego wariantu wyniósł
0,167 s. Liczba jego próbek wzrosła z 308 do 500. Nie było niedopasowanych repów
w tym przebiegu. Ręcznie obejrzano nakładki maski w pięciu klatkach obejmujących
utratę sylwetki i powrót; zapis: `artifacts/continuity-repair/bench-mask-review.jpg`.

To regresja jednego filmu rozwojowego, a nie dowód skuteczności na nowych nagraniach.
Nie przeliczano po poprawce całego sześciofilmowego zestawu z nową pozycją;
nie należy przedstawiać sumy starych i nowych wyników jako nowego pełnego testu.
Modele odcinków nadal pomijają piąty rep. W squat pozostają błędne maski tułowia,
a w trudnym deadlift brak przypisanej sztangi. Nie usuwano chroniących przed tym filtrów.

## Model wieloćwiczeniowy

Porównanie samych wag na tych samych zapisanych pozach znajduje
się w [raporcie kandydata](model-candidate-comparison.md): v2 uzyskał 5/10 repów,
v1 4/10, DINO/SAM2 6/10 przed poprawką ciągłości. Wszystkie sześć nagrań należy do
treningu lub walidacji rozwojowej kandydata. Domyślnego backendu ani wag nie zmieniono.

## Sprawdzenie i artefakty

- 80 testów podstawowego modułu Python i 41 testów Vision zakończone powodzeniem.
- Testy regresji najpierw odtworzyły błąd, potem przeszły po poprawkach.
- Release publish zakończony powodzeniem; proces uruchomiony, reagujący,
  okno MotionTrace. Nie wykonywano automatycznej inspekcji natywnego UI.
- Pliki AI w `artifacts/app-continuity-repair` porównano bajtowo ze źródłami.
- `artifacts/continuity-repair/report.json`: komplet dopasowań i błędów faz.
- `bench-person-replay.json`, `bench-detections.json`: dowody zmiany tożsamości.
- `bench-pose-fixed.json`, `bench-current.json`, `bench-custom.json`,
  `bench-candidate.json`: rzeczywiste nowe wyniki, bez nadpisania benchmarku.
- `research/vision/evaluate_continuity.py`: powtarzalne porównanie CPU na kopiach.

Nowa aplikacja: `artifacts/app-continuity-repair/motion_trace_win.exe`.
W Visual Studio należy ponownie zbudować projekt i ponownie przeanalizować film.

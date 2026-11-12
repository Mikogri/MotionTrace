# Bench press / Unknown — prototyp 0.1

## Co zostało wykonane
Zinwentaryzowano 25 filmów (1262,6 s). Kontaktowe podglądy znajdują się lokalnie w artifacts/bench_dataset. Wykonano pełną analizę pozy trzech nagrań wymienionych w analyze_samples.py. Pozostałe nagrania nie przeszły jeszcze pełnej analizy pozy ani etykietowania.

To detektor regułowy, nie wytrenowany model. Nie przypisuje etykiety na podstawie nazwy folderu ani pliku. Dla każdej osoby osobno ocenia ostatnie 6 sekund: widoczność barku/łokcia/nadgarstka/biodra, pochylenie tułowia, uniesienie nadgarstka, zakres zmiany kąta łokcia i zmianę kierunku. Przerwy w pozy, brak ruchu i niepewne ujęcia dają Unknown. Wynik liczbowy jest siłą spełnienia reguł, nie prawdopodobieństwem.

## Obserwacje z prawdziwych filmów
- VID_20251014_204427~2.mp4: kandydat Bench press dla track 3 od 5,5 do 15 s, pozostałe ślady Unknown. Podgląd wskazuje wyciskającego zawodnika; koniec detekcji obejmuje także przejście po serii. To nie jest dokładny czas powtórzenia.
- 100kg x 5.mp4: wszystkie ślady Unknown mimo obecnego wyciskania; ujęcie od nóg / zasłonięcie.
- VID_20260424_214030~2.mp4: wszystkie ślady Unknown mimo obecnego wyciskania; niestabilne / zasłonięte pozy.

To eksploracyjne sprawdzenie i dobór reguł na trzech filmach, a nie niezależny test. Nie obliczano accuracy, precision ani recall. Nie ma etykiet każdej osoby i każdego przedziału. Nie ma modelu rozróżniającego squat/deadlift ani dowodu odporności na inne ćwiczenia leżąc, przygotowanie lub pomoc spottera. Czułość aktualnego prototypu jest ograniczona. Unknown nie oznacza, że osoba nie wykonuje wyciskania.

## Orientacja
OpenCV 4.11 domyślnie zwracał w tym środowisku CAP_PROP_ORIENTATION_AUTO=0. Włączono automatyczny obrót przed odczytem wymiarów i klatek. Przykładowy materiał zapisany jako 1920x1080 daje po korekcji 1080x1920, zgodnie z orientacją odtwarzania. Wersja silnika 0.2.0 unieważnia wcześniejszy cache. Pliki źródłowe pozostają bez zmian.

## Odtworzenie
Uruchom research/bench_press/analyze_samples.py Pythonem środowiska motiontrace z jego Library/bin w PATH. Wymaga lokalnych wag RTMPose/RTMDet i CUDA; nie pobiera wag. Następnie:

    dotnet run --project research/bench_press/Evaluate -- "artifacts/bench_dataset/VID_20251014_204427~2.mp4.json" "artifacts/bench_dataset/100kg x 5.mp4.json" "artifacts/bench_dataset/VID_20260424_214030~2.mp4.json"

Dokładne próbki dodatnich wyników zapisano w results.txt. Kolejny etap walidacji wymaga etykietowania przedziałów i zawodnika, oraz podziału całych sesji/kamer na zbiór rozwojowy i testowy. Sąsiednich IMG_0806–0818 nie należy losować klatkami do obu zbiorów. Filmy przeglądane podczas doboru reguł nie mogą później udawać niezależnego testu.

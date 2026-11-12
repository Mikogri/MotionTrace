# Czas analizy i zachowanie jakości

Pomiar na `F:/Bench press/IMG_0718.MOV`, 1485 klatek, 2160 × 3840,
wykonany sekwencyjnie na tym samym komputerze i tych samych wagach.
Porównanie dotyczy **etapu Vision z gotowymi wynikami pozy**, nie całkowitego
czasu pierwszej analizy w aplikacji. Pierwsze obliczenie RTMPose trzeba doliczyć.

| Etap | Przed | Po |
|---|---:|---:|
| Wykrywanie kandydatów DINO | 70,67 s | 40,92 s |
| Śledzenie SAM2 | 170,82 s | 132,98 s |
| Klasyfikacja X-CLIP | 58,75 s | 29,06 s |
| Vision łącznie, bez startu procesu | 305,26 s | 207,86 s |
| Ponowne Vision, zweryfikowany cache | brak odczytu cache | 5,32 s |

Pierwszy przebieg Vision skrócono o **31,9%**. Czas nowego procesu od uruchomienia
do zakończenia wyniósł 213,06 s dla świeżego przebiegu i 8,17 s dla cache.
Zużycie szczytowe zaalokowanej pamięci CUDA pozostało 2 045 354 496 bajtów.

## Zmiany

- Każda klatka nadal jest dekodowana i sprawdzana: PTS, kompletność nagrania,
  błędy, wymiary i obrót. Pełny obraz BGR tworzony jest tylko tam, gdzie dany
  etap go wykorzystuje. Nie zmienia to harmonogramu próbek DINO ani X-CLIP.
- Odczyt obrazu nakłada się na obliczenia przez ograniczoną kolejkę dwóch klatek.
  SAM dostaje wszystkie kolejne klatki od pierwszego promptu i zachowuje pamięć.
- Pomiar proxy wykorzystuje już policzoną ramkę maski. Nie powtarza wyszukiwania
  wszystkich pikseli ani konwersji obrazu do szarości niepotrzebnej dla proxy.
  Ręcznie wskazany punkt nadal używa LK z kolejnymi obrazami w skali szarości.
- X-CLIP liczy sekwencje potwierdzonych właścicieli obiektów. Pozostali i tak
  otrzymywali końcowe Unknown przez bramkę przypisania; teraz zapisują jawny
  powód pominięcia, bez surowych propozycji ćwiczenia dla osób z tła.
- Pełny wynik może być ponownie użyty. Sprawdzane są modele, źródła algorytmu,
  zależności, urządzenie, film, pose, konfiguracja i korekty oraz hashe wyniku
  i wszystkich masek. Brakujący/uszkodzony plik wymusza nowe obliczenie.
  Wynik niekompletnego/anulowanego przebiegu nie jest trafieniem cache.

## Kontrola wyniku

Na powyższym filmie porównano wszystkie klatki i obiekty: PTS, identyfikatory,
stan śledzenia, ramki i pomiary były identyczne. Pliki masek miały identyczne
SHA-256. Klasyfikacja ćwiczącego, wszystkie jego okna, wyniki i marginesy były
identyczne. Odczyt cache zachował dokładnie klatki i predykcje świeżego przebiegu.
To kontrola braku regresji na tym filmie, nie uniwersalny dowód dokładności AI.

Dowody: `artifacts/model-comparison/performance-comparison.json`, `runs.json`,
`img-current.json`, `img-warm.json`. Punkt odniesienia pozostaje w
`artifacts/vision-repair/bench-fixed.json`; nie nadpisywano jego metadanych.

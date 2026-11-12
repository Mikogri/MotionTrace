# Porównanie nadgarstka i gryfu

Test wykonano na zapisanych wynikach reported-mp4.json (606 klatek) i reported-0809.json (1560 klatek), z tą samą korekcją pozy, progiem ruchu 1,5% wysokości obrazu i detektorem faz bench press. Nie uruchamiano ponownie modeli AI. Nadgarstki mają dodatkową bramkę potwierdzenia ruchu gryfu, jak w aplikacji; gryf jest analizowany niezależnie od ID zawodnika. Wyników nie należy interpretować jako niezależnego porównania dwóch detektorów powtórzeń.

| Nagranie / źródło | Próbki trajektorii | Segmenty ciągłości | Potwierdzone repy | Podnoszenie (s) |
|---|---:|---:|---:|---|
| MP4 / gryf | 606/606 | 1 | 1 | 1,723 |
| MP4 / track 2 lewy nadgarstek | 477/606 | 3 | 1 | 2,094 |
| MP4 / track 2 prawy nadgarstek | 418/606 | 10 | 0 | — |
| 0809 / gryf | 1560/1560 | 1 | 2 | 0,400; 0,500 |
| 0809 / track 1 lewy nadgarstek | 1409/1560 | 3 | 2 | 0,400; 0,467 |
| 0809 / track 1 prawy nadgarstek | 1389/1560 | 4 | 1 | 0,733 |

Liczba próbek nadgarstka dotyczy konkretnego ID i obejmuje naprawę krótkich luk; nieobecność osoby i zmiana ID również zmniejszają pokrycie. Gryf może łączyć obserwacje niezależnie od ID osoby, więc pokrycie całego filmu nie jest samodzielnym miernikiem dokładności.

Maksymalna prędkość: MP4 gryf 83,58 px/s, lewy nadgarstek track 2 103,92 px/s. 0809 gryf 774,81 i 829,31 px/s, lewy nadgarstek 844,32 i 946,62 px/s. Różne wartości pokazują rozbieżność, nie dowodzą który szczyt jest poprawny. Nie porównywać wartości px/s między nagraniami jako fizycznej prędkości.

W tych dwóch przykładach pomiar z gryfu jest bardziej ciągły i mniej zależny od wyboru ręki lub ID zawodnika. Nie dowiedziono przewagi dokładności czasów ani prędkości: brak oznaczeń referencyjnych klatek granicznych, skali i niezależnego pomiaru prędkości. Nie wykonano nowej oceny wizualnej klatka po klatce w tym teście. Wynik dotyczy bench press, nie squatu ani deadliftu.

Następny test: ręczne oznaczenie początku/końca faz na tych samych powtórzeniach, błędy czasów względem oznaczeń oraz odsetek brakujących próbek w obrębie liftu. Część filmów musi pozostać poza strojeniem progów.

Surowe wyniki: artifacts/shaft_model/comparison-mp4.json i comparison-0809.json. Odtwarzalny program: research/barbell/AnalysisProbe.

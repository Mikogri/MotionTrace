# TAPNext++ — przyspieszenie bez zmiany trajektorii

22.09.2026: adapter `tap-points-4`, oficjalny checkpoint 256×256 bez zmiany wag.

- Istniejący `PrefetchedVideoDecoder` dekoduje następną klatkę podczas pracy
  GPU. Kolejka ma pojemność 2, nie pomija klatek ani walidacji timestampów.
  Błędy dekodowania i zamknięcie producenta zachowują dotychczasowy kontrakt.
- Jedna sesja autocast obejmuje sekwencję; konwersje wag mogą pozostać w cache.
  Nadal używamy tych samych wag float32 i CUDA autocast float16.
- Współrzędne, logity i prawdopodobieństwa obu punktów trafiają do CPU jednym
  transferem na klatkę zamiast osobnych synchronizacji dla każdej wartości.
- `performance.trackingTimings` rozdziela ładowanie modelu, oczekiwanie na
  dekoder i preprocessing/inferencję/transfer wyników.

## Rzeczywiste porównanie

`IMG_0809.MOV`, 1560 klatek, te same dwa zaznaczenia i obszar, RTX 3070 Ti,
ten sam plik z udziału sieciowego. Dwa pełne przebiegi, kolejno przed i po
zmianie; to pojedyncza para pomiarów, nie gwarancja dla każdego nagrania.

| Etap śledzenia | Przed | Po |
|---|---:|---:|
| Czas całkowity adaptera | 142,621 s | 82,400 s |
| Maksymalna pamięć GPU alokowana przez Torch | 1703628288 B | 1730625024 B |
| Liczba obserwacji dwóch punktów | 3120 | 3120 |

Skrócenie czasu o 42,2% (1,73× szybciej). Wszystkie obiekty wynikowe są
identyczne, w tym x/y, widoczność i confidence. Maksymalna różnica x/y: 0.
Zachowane 2 repy i ich czasy. Pomiar nie obejmuje RTMPose, klasyfikacji
ćwiczenia ani operacji UI. Etap modelu nadal stanowi większość kosztu:
około 71,8 s; oczekiwanie na dekoder około 3,2 s, ładowanie modelu około 3,0 s.

## Widoczne opóźnienie

Nakładka jest teraz odświeżana przez `CompositionTarget.Rendering`, zamiast
polegać wyłącznie na timerze kontrolek 33 ms. Nadal wybiera rzeczywistą klatkę
według timestampu; nie przewiduje przyszłego położenia i nie przesuwa czasów.
To usuwa dodatkowe oczekiwanie na timer, ale nie jest poprawą dokładności
predykcji modelu. Nie zmierzono latencji fizycznego ekranu.

Materiały: `artifacts/tap-speed-accuracy/baseline.json`, `optimized.json`,
`measurements.json` oraz logi testów i kompilacji w tym samym katalogu.

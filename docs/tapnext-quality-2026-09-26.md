# Śledzenie punktów i ponowna analiza — 26.09.2026

Wprowadzono małe zmiany w istniejącym przebiegu:

- Automatyczna propozycja szuka wyraźnego detalu w wąskim pasie gryfu,
  najwyżej 8% długości od wykrytych końców. Bez wyraźnego detalu zachowuje
  punkt detektora. To heurystyka tekstury, nie nowy model rozpoznający oś
  talerza ani dłonie. Zapisane punkty i ręczne poprawki nie są nadpisywane.
- Stały obszar TAP może korzystać z zakresu ruchu nadgarstków wskazanego
  zawodnika. Wymaga obu pewnych nadgarstków na pierwszej klatce i w co
  najmniej 80% klatek (minimum 20). Obszar zachowuje zapas, może się
  powiększyć przy większym ruchu. Bez tych danych używa poprzedniej reguły.
  Obszar nie przesuwa się pod stanem rekurencyjnym modelu; nadgarstki
  nigdy nie zastępują współrzędnych punktów w pomiarach.
- Pojedynczy skok względnego położenia punktów, po którym wracają do
  poprzedniej geometrii, jest oznaczany `pair-discontinuity`. Obie miary
  z tej klatki są nieważne. Surowe x/y, widoczność i logity pozostają.
  Wspólny szybki ruch pary pozostaje poprawny; filtr nie łączy luk.
  Nie wykrywa wszystkich rodzajów trwałego dryfu.
- Klasyfikacja X-CLIP ma osobny cache: zmiana punktów przy tym samym
  zawodniku nie wymusza jej ponownego liczenia. Wideo, pozy, model,
  kod, środowisko i zawodnik są częścią tożsamości cache. Walidacja wag
  działa również przy odczycie cache. Pozy już miały własny cache.

## Sprawdzenie na GPU

Rzeczywista klasyfikacja X-CLIP tego samego filmu: 23,76 s pierwszy przebieg,
3,60 s po przesunięciu punktu przy tym samym zawodniku; zapisane predykcje
identyczne. Pomiar zawiera start procesu i sprawdzanie modeli. To czas
etapu klasyfikacji, nie całej analizy. Skrypt: `cache_benchmark.py`.

Pełne 565 klatek filmu `100kg x 5.mp4`, oficjalny TAPNext++, dwie propozycje
punktów. Wersja 256: 48,94 s, 249 klatek z dwoma poprawnymi pomiarami.
Wersja 512: 97,11 s, 130 takich klatek. Poprzedni przebieg 256 z 24.09:
49,84 s, 246 klatek. To pojedyncze przebiegi; brak dowodu przyspieszenia
pierwszej analizy. Na tym filmie nadal występują znaczne przerwy śledzenia,
a próba wyznaczania powtórzeń z pary nie zwróciła powtórzeń.

Na 8 wspólnych widocznych obserwacjach z ręcznie opisanych klatek średnia
odległość od osi gryfu wyniosła 13,53 px przed zmianą, 9,73 px po zmianie
w 256 i 21,13 px w 512 (piksele źródłowego 4K). To odległość od osi,
nie błąd śledzenia tego samego punktu fizycznego; próba jest bardzo mała.
Nie stanowi gwarancji poprawy w innych filmach ani walidacji czasów faz.
Na badanym filmie nie spełniono warunków dopasowania obszaru z pozy —
zadziałała reguła zapasowa. Dopasowanie z pozy pokryto testami syntetycznymi.

512 pobrano z oficjalnego repozytorium modeli Google i sprawdzono SHA-256.
Pozostaje opcją istniejącej konfiguracji; domyślne 256 nie zostało zmienione.
Kod DeepMind i jego manifest integralności pozostają bez zmian.

Próba `torch.compile` na CUDA zakończyła się `TritonMissing` w obecnym
PyTorch 2.8.0+cu126. Kompilacja pozostaje wyłączona. Nie instalowano
zamiennych backendów i nie dodano procesu stale zajmującego pamięć.

Wyniki, logi i powtarzalne skrypty: `artifacts/tracking-quality/`.

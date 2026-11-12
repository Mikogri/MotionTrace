# Weryfikacja Tritona na Windows — 26.09.2026

Środowisko `motiontrace-points`: Python 3.11.16, PyTorch 2.8.0+cu126,
triton-windows 3.4.0.post21, RTX 3070 Ti. Prosty test `torch.compile`
z tensorem CUDA przeszedł. Oficjalny TAPNext++ również ukończył pełne
565 klatek `100kg x 5.mp4` przy `compile_model=True`.

Próba znajduje się w `artifacts/tap-compile/probe.py`. Włącza istniejący
oficjalny parametr wyłącznie w procesie testowym. Nie modyfikuje kodu
DeepMind, checkpointu, precyzji, rozdzielczości 256 ani produkcyjnej konfiguracji.
`TORCHINDUCTOR_COMPILE_THREADS=1` ogranicza równoległe zużycie pamięci
podczas kompilacji. Dane wejściowe i punkty są takie same jak w poprzednim
teście `artifacts/tracking-quality/analysis.json`.

Pierwszy przebieg skompilowany trwał 250,73 s (bez kompilacji 48,94 s).
Drugi przebieg w nowym procesie, z zachowanym cache kompilatora, trwał
210,91 s. Odpowiada to sposobowi uruchamiania backendu przez aplikację;
nie mierzono kolejnych filmów w jednym stale działającym procesie.
Oba przebiegi skompilowane zwróciły takie same różnice względem baseline.
Porównano wszystkie 1130 obserwacji na identycznych timestampach:
widoczność i dostępność pomiarów pozostały takie same. Średnia różnica
współrzędnych widocznych punktów wyniosła 0,099 px, maksymalna 22,98 px.
Maksimum dla wszystkich surowych predykcji, również niewidocznych, to
65,02 px. Nie są to błędy względem prawdy referencyjnej — to różnice
między dwoma sposobami obliczania modelu. Nie wykazano równoważności pomiarów.

Kompilacja pozostaje wyłączona w aplikacji. Triton zostaje zainstalowany,
ale sama obecność pakietu nie zmienia przebiegu analizy.

Wyniki: `cold-result.json`, `cold-comparison.json`, logi oraz raport
porównawczy `comparison.json` w `artifacts/tap-compile/`.

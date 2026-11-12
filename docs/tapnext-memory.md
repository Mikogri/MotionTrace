# Pamięć TAPNext++

Pomiar 2026-09-24: oficjalny TAPNext++ 256, dwa punkty, lokalny film
`100kg x 5.mp4`, 2160×3840, wszystkie 565 klatek. Zakończono śledzenie
obu punktów na całej osi czasu. Bez zmian modelu, FPS i precyzji obliczeń.

- Szczyt working set procesu: 4134 MiB; podczas śledzenia zaobserwowano 1708 MiB.
- Maksymalny próbkowany private commit: 7814 MiB (próbkowanie co 100 ms).
- Szczyt alokacji PyTorch na GPU: 1649 MiB; nie obejmuje całej pamięci sterownika.
- Backend: 49,84 s; pomiar obejmował tylko etap śledzenia, bez pozy i klasyfikacji.

Przy pojedynczym TAPNext++ scheduler dopuszcza start przy 2560 MiB wolnego RAM
i 10240 MiB dostępnego Windows commit (RAM + plik stronicowania). Zachowano
dotychczasową ścieżkę dla co najmniej 4524 MiB wolnego RAM oraz warunki GPU
i równoległego uruchamiania starszych modeli. To budżety orientacyjne na
podstawie jednego nagrania, nie gwarancja zużycia dla wszystkich filmów.
Stronicowanie może spowolnić start przy dużym obciążeniu systemu.

Wyniki: `artifacts/ram-profile/memory.json`, `result.json`, `stdout.log`.
Skrypt pomiarowy nie przechwycił kodu zakończenia procesu (null); sukces
potwierdzono końcowym komunikatem i walidacją zapisanego JSON: 565 klatek,
po dwa obiekty na każdej, bez błędów w stderr.

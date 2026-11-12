# Oznaczenia faz — pilotaż

Otwórz artifacts/phase-review-v1/review.html. Formularz obejmuje sześć całych nagrań: po dwa bench, squat i deadlift, pierwsze/ostatnie w kolejności nazw. To mała partia pilotażowa, nie reprezentatywny test jakości.

1. Wybierz film i dodaj powtórzenie. Przesuwaj podgląd strzałkami klatka po klatce; spowolnienie i pasek filmu pomagają znaleźć właściwe miejsce.
2. Dla bench/squatu zaznacz ostatnią górną klatkę przed właściwym opuszczaniem, koniec opuszczania, początek podnoszenia i jego koniec. Przygotowanie obejmuje wyjęcie/ustawianie przed repem; nie wliczamy go do czasu opuszczania. Między repami przygotowanie zaczyna się po końcu poprzedniego podnoszenia.
3. Dla deadliftu rep opisujemy jako podnoszenie → lockout/pauza na górze → odkładanie. Odkładanie nie poprzedza pierwszego podnoszenia. Nowy rep dodaj dla każdego kolejnego podnoszenia. Początkowa przerwa na podłodze może być przygotowaniem.
4. Gdy nie ma pauzy, koniec opuszczania i początek podnoszenia mogą być równe. Ucięte/nieczytelne granice zostaw puste i opisz. Nie zgaduj. Oznaczaj wykonującego ćwiczenie, nie spottera.
5. Zaznacz „Całe nagranie sprawdzone” po obejrzeniu całości. Nie jest to automatyczne zatwierdzenie wszystkich granic; eksport zachowuje także niepełne repy.
6. Wyeksportuj motiontrace-phases-v1.json do research/barbell. Zapis lokalny ma osobny klucz; stare oznaczenia gryfu są niezależne.

Podglądy są bez dźwięku i mają zmniejszoną rozdzielczość, lecz zachowane źródłowe PTS i orientację. Indeksy klatek są zerowe. Znaczniki eksportowane są z tablicy rzeczywistych czasów źródłowych, nie z frame/FPS. Kompresja podglądu nie zmienia danych oryginału.

Po imporcie: ocenić błąd początku/końca faz oraz pominięte/fałszywe repy. Oddzielić walidację od filmów używanych do strojenia. Te etykiety służą algorytmowi faz, nie segmentacji gryfu. Nie zmieniono jeszcze automatycznego detektora faz; najpierw potrzebne są poprawne oznaczenia referencyjne.

Testy: właściwym runtime Node uruchomić research/barbell/phase_review/review_tests.cjs. Generator prepare_phase_review.py odmawia nadpisania istniejącej partii.

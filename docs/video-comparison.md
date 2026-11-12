# Porównanie wielu nagrań

1. Przeanalizuj pierwszy film i wybierz zawodnika, ćwiczenie oraz źródło pomiaru.
2. Kliknij **Compare videos…**. Możesz zaznaczyć kilka plików jednocześnie.
   **Add videos…** dodaje następne bez zastępowania wcześniejszych.
3. **Displayed video** wybiera film w odtwarzaczu. Nagrania bez zapisanej
   analizy należy wybrać i przeanalizować zwykłym przyciskiem Analyze video.
4. Każdy film ma osobny wybór powtórzenia i stały kolor na wspólnym wykresie.
   Przełączenie odtwarzacza zachowuje wyniki pozostałych nagrań.

Time wyrównuje początek ruchu do zera. Przygotowanie jest przed zerem;
czas nie jest rozciągany. ROM pokazuje tylko podnoszenie. Przerywane linie
mają kolor filmu i oznaczają granice faz. Filtry faz nie zmieniają pomiarów.
Przeciąganie kursora oraz Play sterują wyłącznie wyświetlanym nagraniem.

Tabela zawiera 16 metryk i jakość dla każdego wybranego powtórzenia.
Pod wartościami kolejnych filmów widnieją różnice bezwzględne i procentowe
względem pierwszego filmu. Brak danych lub zerowy mianownik daje kreskę.
Przy porównaniu różnych ćwiczeń pojawia się informacja o różnym znaczeniu faz.

Normalizacja Y pokazuje % ROM i % ROM/s, a nie prędkość fizyczną w m/s.
Bez normalizacji jednostki to px i px/s, zależne od kamery i rozdzielczości.
Niepoprawny ROM nie jest zastępowany sztuczną wartością.

Lista porównania istnieje w bieżącym oknie. End comparison przywraca zwykły
widok aktualnego filmu. Eksport nadal dotyczy aktualnego filmu.
Nie zmieniono modeli AI ani algorytmów pomiaru.

Diagnostyka --video-compare-ui-report używa trzech syntetycznych przebiegów
oraz rzeczywistych plików w odtwarzaczu. Sprawdza kolory, fazy, tabelę,
niezależny wybór powtórzeń, zmianę odtwarzanego pliku i przewijanie.

# Odczyt filmów z dysku sieciowego

24.09.2026: błąd `av.error.ValueError: [Errno 22] Invalid argument` wystąpił
podczas ponownego odczytu `F:\Bench press\IMG_0788.MOV` przez klasyfikator
ćwiczenia. W czasie diagnostyki mapowanie F: do `\\10.10.10.50\Filmy`
przeszło ze stanu Reconnecting do Disconnected. Bez dostępu do oryginału
nie można wykluczyć także uszkodzenia samego filmu.

Orkiestrator kopiuje teraz wejścia UNC i dyski sieciowe Windows do lokalnego
`comparison-cache/inputs/<SHA256>/<nazwa filmu>`. Kopia trafia do właściwej
nazwy dopiero po potwierdzeniu sumy kontrolnej. Wszystkie etapy backendu
otrzymują lokalną ścieżkę. Oryginał oraz ścieżka odtwarzania pozostają bez zmian.
Niepełna kopia jest usuwana; zmiana zawartości podczas kopiowania kończy
analizę błędem. Istniejąca poprawna kopia może być ponownie wykorzystana.
Import i odtwarzanie oryginału nadal wymagają dostępu do dysku źródłowego.

Baner pokazuje końcową przyczynę błędu procesu, a pełny traceback pozostaje
w logach. Nie wyłączono walidacji klatek ani obsługi błędów dekodowania.

Weryfikacja: testy kopiowania, utraty źródła po skopiowaniu, integralności,
czyszczenia niepełnej kopii i komunikatu błędu. Rzeczywisty lokalny film
`100kg x 5.mp4` skopiowano i w całości zdekodowano. IMG_0788.MOV pozostaje
do ponownego sprawdzenia po odzyskaniu połączenia z serwerem.

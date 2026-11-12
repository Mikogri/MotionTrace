# Lokalny backend Vision — Windows

Backend `grounding_dino_sam2` korzysta z osobnego środowiska Conda
`motiontrace-vision`. Istniejące środowisko `motiontrace` nadal obsługuje
detektor osób, tracking i RTMPose/MMPose. Instalator nie zmienia tego środowiska,
sterownika GPU ani CUDA Toolkit. Wagi własnego detektora sztangi pozostają w
projekcie; nie są składnikiem instalacji Vision.

## Instalacja

Z katalogu projektu, w PowerShell:

```powershell
.\scripts\setup-vision.ps1
```

Skrypt używa jawnego interpretera
`$env:USERPROFILE\miniconda3\envs\motiontrace-vision\python.exe`, a nie `python`
z PATH. Dla innej instalacji Conda należy podać `-CondaExe` i `-EnvironmentPath`.
Opcjonalny `-ModelRoot` zmienia lokalizację modeli. `-SkipDownload` pomija
pobieranie modeli, lecz nadal instaluje zależności i sprawdza istniejący manifest;
nie jest trybem instalacji całkowicie offline.

Przypięte wersje: Python 3.11.16, pip 25.3, PyTorch 2.8.0+cu126,
torchvision 0.23.0+cu126, Transformers 4.57.6, NumPy 1.26.4,
OpenCV 4.11.0.86, PyAV 16.0.1, Pillow 11.3.0, SciPy 1.15.3.
Bezpośrednie zależności są przypięte w `ai/requirements-vision.txt`;
`dependencies.json` zapisuje rzeczywiste wersje wszystkich zainstalowanych
zależności pośrednich. Instalator preferuje `ai/requirements-vision-lock.txt`,
jeżeli istnieje; ten plik utrwala także zależności pośrednie z potwierdzonej
instalacji. Sam manifest wersji nie jest kompletnym archiwum pakietów do
instalacji offline.

Domyślna lokalizacja wag jest wspólna dla Visual Studio, terminala i EXE.
AppData procesu instalującego może być przekierowane przez Windows, dlatego
używamy katalogu projektu wyłączonego z Git. Nie wymaga praw administratora:

```text
<katalog-projektu>/.models/vision/
  manifest.json
  dependencies.json
  dependency_notices/
  xclip/
  grounding_dino/
  sam2/
```

| Klucz | Repozytorium wag | Przypięta rewizja | Licencja karty modelu |
|---|---|---|---|
| xclip | microsoft/xclip-base-patch16 | d6184e3fd8780d04c85d0f1eabe5f94bf44d98f6 | MIT |
| grounding_dino | IDEA-Research/grounding-dino-tiny | a2bb814dd30d776dcf7e30523b00659f4f141c71 | Apache-2.0 |
| sam2 | facebook/sam2.1-hiera-small | ee5bba1d82bb8749febdf90f45e84b687142ba03 | Apache-2.0 |

Instalator pobiera rzeczywiste wagi Safetensors, konfiguracje i komplet plików
processorów/tokenizerów z tych rewizji. Nie pobiera drugiej kopii wag `.bin`/`.pt`,
jeżeli dostępne jest Safetensors. Zachowuje karty modeli i przypięte licencje
upstream. Manifest zawiera źródło, lokalną ścieżkę, rozmiar i SHA-256 każdego
zainstalowanego pliku. Pobieranie jest osobnym krokiem instalacji.

## Sprawdzenie bez internetu

Weryfikacja plików nie importuje klienta Hugging Face i nie wykonuje żądań sieciowych:

```powershell
$VisionPython = "$env:USERPROFILE\miniconda3\envs\motiontrace-vision\python.exe"
$ModelRoot = Join-Path $PWD '.models\vision'
$env:HF_HUB_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
& $VisionPython .\scripts\vision_models.py --root $ModelRoot --verify
```

Osobny test rzeczywistego inference, na lokalnym nagraniu:

```powershell
& $VisionPython .\ai\vision\smoke.py --models-root $ModelRoot `
    --video '.\videos\bench\100kg x 5.mp4' `
    --output '.\artifacts\vision-smoke.json'
```

Test wymaga przygotowanych modeli, CUDA oraz wskazanego lokalnego pliku.
Weryfikacja importów lub samych hashy nie dowodzi, że inference działa;
wynik testu modeli zapisuje oddzielny raport. Analiza ma ładować modele wyłącznie
z lokalnych katalogów z `local_files_only=True` oraz `HF_HUB_OFFLINE=1`.
Brak lub zmiana pliku oznacza błąd wymagający ponownej instalacji, a nie ukryty
download ani przełączenie na własny detektor.

## Licencje i pochodzenie

Zobacz `ThirdPartyNotices/vision.md`. Licencje wag, implementacji i bibliotek są
odrębne. Skrypt `--audit-environment` zapisuje metadane licencji oraz dołączone
LICENSE/NOTICE z zainstalowanych dystrybucji. Nie przypisuje Apache-2.0 całemu
środowisku. Przy dystrybucji środowiska należy zachować również licencje
składników binarnych, m.in. CUDA i FFmpeg, dołączone do konkretnych pakietów.

Źródła interfejsów:

- [X-CLIP](https://huggingface.co/docs/transformers/v4.57.1/en/model_doc/xclip)
- [Grounding DINO](https://huggingface.co/docs/transformers/v4.57.1/en/model_doc/grounding-dino)
- [SAM2 Video](https://huggingface.co/docs/transformers/v4.57.1/en/model_doc/sam2_video)

Dokumentacja stabilnej serii 4.57 zawiera `Sam2VideoModel` i
`Sam2VideoProcessor`. Setup sprawdza dostępność tych klas w faktycznie
zainstalowanej wersji 4.57.6; nie wymaga WSL, Dockera ani instalacji repozytorium
SAM2 z własnymi rozszerzeniami CUDA.

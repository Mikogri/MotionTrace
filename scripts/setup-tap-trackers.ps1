param(
    [string]$Conda = "$env:USERPROFILE/miniconda3/Scripts/conda.exe",
    [string]$Python = "$env:USERPROFILE/miniconda3/envs/motiontrace-points/python.exe",
    [string]$ModelsRoot = "$PSScriptRoot/../.models/points"
)
$ErrorActionPreference = 'Stop'
$revision = '730cda1c730877cfedbe01bf87fb1cadb78a565d'
$weightsRevision = '5d3fb48e76c5422841e38501514121e251beabb7'
if (-not (Test-Path -LiteralPath $Python)) {
    & $Conda create --name motiontrace-points python=3.11.16 -y
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create isolated point tracker environment' }
}
& $Python -m pip install -r "$PSScriptRoot/../ai/comparison/requirements-points.txt"
if ($LASTEXITCODE -ne 0) { throw 'Point tracker dependencies failed' }
New-Item -ItemType Directory -Force -Path $ModelsRoot | Out-Null
$ModelsRoot = (Resolve-Path -LiteralPath $ModelsRoot).Path
$source = Join-Path $ModelsRoot 'tapnet'
if (-not (Test-Path -LiteralPath $source)) {
    & git clone --no-checkout https://github.com/google-deepmind/tapnet.git $source
    if ($LASTEXITCODE -ne 0) { throw 'Official tapnet clone failed' }
}
& git -C $source checkout --detach $revision
if ($LASTEXITCODE -ne 0) { throw 'Pinned tapnet revision unavailable' }
$weights = @{
    tapnextpp = @{ path='tapnextpp_ckpt.pt'; sha256='cb96a43444ccb4fbdb25d800b88c7ba196179a526e78f01b021a16b1c1eff6da'; size=2532282370; mode='online-recurrent' }
    bootstapir = @{ path='bootstapir_checkpoint_v2.pt'; sha256='8493c7a69e02c85b9382fbb3c7b8b539b36bc08ede744b9e99feb739a0129f4b'; size=218886140; mode='offline-full-sequence' }
}
$models = @{}
foreach ($name in $weights.Keys) {
    $weight = $weights[$name]
    $path = Join-Path $ModelsRoot $weight.path
    if (-not (Test-Path -LiteralPath $path)) {
        $url = "https://huggingface.co/google/tapnet/resolve/$weightsRevision/$($weight.path)"
        & $Python -c 'import sys,urllib.request,os; urllib.request.urlretrieve(sys.argv[1],sys.argv[2]+".download"); os.replace(sys.argv[2]+".download",sys.argv[2])' $url $path
        if ($LASTEXITCODE -ne 0) { throw "Download failed: $name" }
    }
    if ((Get-Item -LiteralPath $path).Length -ne $weight.size -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $weight.sha256) { throw "Checkpoint integrity failed: $path" }
    $models[$name] = @{ revision=$weightsRevision; checkpoint=$weight.path; files=@(@{path=$weight.path;sha256=$weight.sha256;size=$weight.size}); mode=$weight.mode; resolution=@(256,256); license='Apache-2.0'; source='https://huggingface.co/google/tapnet' }
}
$sources = @(Get-ChildItem -LiteralPath (Join-Path $source 'tapnet') -Recurse -File -Filter '*.py' | ForEach-Object { @{path=[IO.Path]::GetRelativePath($ModelsRoot,$_.FullName).Replace('\','/');sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant();size=$_.Length} })
Invoke-WebRequest -Uri "https://huggingface.co/google/tapnet/raw/$weightsRevision/README.md" -OutFile (Join-Path $ModelsRoot 'MODEL_CARD.md')
Copy-Item -LiteralPath (Join-Path $source 'LICENSE') -Destination (Join-Path $ModelsRoot 'LICENSE')
& $Python -m pip freeze | Set-Content -LiteralPath (Join-Path $ModelsRoot 'environment-lock.txt') -Encoding utf8
& $Python -c 'import importlib.metadata as m,json,pathlib,sys; names=["torch","torchvision","numpy","opencv-python","av","einops","einshape","dm-tree","absl-py","attrs","wrapt"]; d={}; [d.update({n:{"version":m.version(n),"license":m.metadata(n).get("License"),"classifiers":[c for c in m.metadata(n).get_all("Classifier",[]) if "License" in c]}}) for n in names]; pathlib.Path(sys.argv[1]).write_text(json.dumps(d,indent=2),encoding="utf-8")' (Join-Path $ModelsRoot 'DEPENDENCY-LICENSES.json')
& $Python -c 'import importlib.metadata as m,pathlib,shutil,sys; root=pathlib.Path(sys.argv[1]); names=[line.split("==")[0] for line in pathlib.Path(sys.argv[2]).read_text().splitlines() if "==" in line]; [( (root/n/pathlib.Path(str(f))).parent.mkdir(parents=True,exist_ok=True),shutil.copyfile(m.distribution(n).locate_file(f),root/n/pathlib.Path(str(f)))) for n in names for f in (m.distribution(n).files or []) if "dist-info" in str(f) and any(x in pathlib.Path(str(f)).name.upper() for x in ["LICENSE","NOTICE","COPYING"])]' (Join-Path $ModelsRoot 'dependency-licenses') "$PSScriptRoot/../ai/comparison/requirements-points.txt"
@{schemaVersion=1;repository='https://github.com/google-deepmind/tapnet';repositoryRevision=$revision;python=$Python;models=$models;sourceFiles=$sources} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $ModelsRoot 'manifest.json') -Encoding utf8NoBOM
Write-Output "Installed TAPNext++ 256 recurrent and BootsTAPIR v2 offline 256 in $ModelsRoot"

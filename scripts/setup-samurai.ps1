param(
    [string]$Conda = "$env:USERPROFILE/miniconda3/Scripts/conda.exe",
    [string]$Python = "$env:USERPROFILE/miniconda3/envs/motiontrace-samurai/python.exe",
    [string]$ModelsRoot = (Join-Path $PSScriptRoot '../.models/samurai')
)
$ErrorActionPreference = 'Stop'
$revision = '76ba195984892b0d1e3db5d9c9f90bb62175680a'
$checkpointHash = '6d1aa6f30de5c92224f8172114de081d104bbd23dd9dc5c58996f0cad5dc4d38'
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Installation command failed: $LASTEXITCODE" } }
if (-not (Test-Path -LiteralPath $Python)) {
    & $Conda create -y -n motiontrace-samurai python=3.11.16 pip
    Check-Exit
}
New-Item -ItemType Directory -Force -Path $ModelsRoot | Out-Null
$ModelsRoot = (Resolve-Path -LiteralPath $ModelsRoot).Path
$source = Join-Path $ModelsRoot 'source'
if (-not (Test-Path -LiteralPath $source)) {
    & git clone --filter=blob:none --no-checkout https://github.com/yangchris11/samurai.git $source
    Check-Exit
    & git -C $source sparse-checkout set sam2/sam2 scripts
    Check-Exit
    & git -C $source checkout $revision
    Check-Exit
}
$actualRevision = & git -C $source rev-parse HEAD
Check-Exit
if ($actualRevision.Trim() -ne $revision) { throw 'SAMURAI source has a different revision. Existing source was preserved.' }
$dirty = & git -C $source status --porcelain
Check-Exit
if ($dirty) { throw 'SAMURAI source has local changes. Existing source was preserved.' }
& $Python -m pip install --extra-index-url https://download.pytorch.org/whl/cu126 -r (Join-Path $PSScriptRoot 'requirements-samurai.lock.txt')
Check-Exit
$previousCudaBuild = $env:SAM2_BUILD_CUDA
try {
    $env:SAM2_BUILD_CUDA = '0'
    & $Python -m pip install --no-build-isolation --no-deps -e (Join-Path $source 'sam2')
    Check-Exit
} finally { $env:SAM2_BUILD_CUDA = $previousCudaBuild }
$checkpoint = Join-Path $ModelsRoot 'sam2.1_hiera_small.pt'
if (-not (Test-Path -LiteralPath $checkpoint)) {
    Invoke-WebRequest 'https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt' -OutFile "$checkpoint.partial"
    if ((Get-FileHash -LiteralPath "$checkpoint.partial" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $checkpointHash) { throw 'Checkpoint checksum mismatch' }
    Move-Item -LiteralPath "$checkpoint.partial" -Destination $checkpoint
}
if ((Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256).Hash.ToLowerInvariant() -ne $checkpointHash) { throw 'Installed checkpoint checksum mismatch' }
$files = @(Get-ChildItem -LiteralPath (Join-Path $source 'sam2/sam2') -Recurse -File | Where-Object { $_.Extension -in '.py','.yaml' } | ForEach-Object {
    @{ path = [IO.Path]::GetRelativePath($ModelsRoot, $_.FullName).Replace('\','/'); sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
})
@{
    schemaVersion=1; provider='samurai'; revision=$revision; checkpoint='sam2.1_hiera_small.pt';
    checkpointSha256=$checkpointHash; config='configs/samurai/sam2.1_hiera_s.yaml';
    python=$Python; source='https://github.com/yangchris11/samurai'; files=$files;
    license='Apache-2.0'; checkpointLicense='Apache-2.0';
    licensePaths=@('source/LICENSE','source/sam2/LICENSE','source/sam2/LICENSE_cctorch');
    optionalCudaExtension=$false; holeFilling=$false
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $ModelsRoot 'manifest.json') -Encoding utf8
& $Python -c "import torch, sam2; print('SAMURAI installed:', sam2.__file__, 'CUDA:', torch.cuda.is_available())"
Check-Exit

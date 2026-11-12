param([string]$Video, [switch]$Analyze)
$ErrorActionPreference = 'Stop'
$project = Join-Path $PSScriptRoot 'win_app\motion_trace_win\motion_trace_win\motion_trace_win\motion_trace_win.csproj'
dotnet build $project -p:Platform=x64 --nologo
if ($LASTEXITCODE -ne 0) { throw 'MotionTrace build failed.' }
$executable = Join-Path $PSScriptRoot 'win_app\motion_trace_win\motion_trace_win\motion_trace_win\bin\x64\Debug\net10.0-windows10.0.19041.0\win-x64\motion_trace_win.exe'
$launch = [System.Diagnostics.ProcessStartInfo]::new($executable)
$launch.UseShellExecute = $false
if ($Video) {
    $launch.ArgumentList.Add('--video')
    $launch.ArgumentList.Add((Resolve-Path -LiteralPath $Video).Path)
}
if ($Analyze) { $launch.ArgumentList.Add('--analyze') }
[System.Diagnostics.Process]::Start($launch) | Out-Null

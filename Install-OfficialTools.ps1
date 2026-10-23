param([string]$ArchivePath = '')
$ErrorActionPreference = 'Stop'
$expected = 'e97e203ce77b6b1a3a37d01beccf069dc6c4632b579ffbb82ae739cdda229f38'
$vendor = Join-Path $PSScriptRoot 'vendor'
$target = Join-Path $vendor 'testdisk-7.2'
if (Test-Path -LiteralPath $target) { throw 'vendor/testdisk-7.2 already exists; existing installation will not be overwritten.' }
$stage = Join-Path $PSScriptRoot ('tool-install-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage | Out-Null
if (!$ArchivePath) {
    $ArchivePath = Join-Path $stage 'testdisk-7.2.win64.zip'
    Invoke-WebRequest -Uri 'https://www.cgsecurity.org/testdisk-7.2.win64.zip' -OutFile $ArchivePath -UseBasicParsing
}
if ((Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Official archive hash mismatch; nothing installed.' }
Expand-Archive -LiteralPath $ArchivePath -DestinationPath $stage
$unpacked = Join-Path $stage 'testdisk-7.2'
$checks = @{
    'photorec_win.exe' = 'd75b9a6ff60f91479085a578aca518abb1cd7405f24506a61afa2f7e222147bf'
    'testdisk_win.exe' = '025ea8936765169966fe497b8c46bd5ad16b98b189ee90d6854f063200c95f0c'
}
foreach ($name in $checks.Keys) {
    if ((Get-FileHash -LiteralPath (Join-Path $unpacked $name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $checks[$name]) { throw 'Executable hash mismatch; nothing installed.' }
}
if (!(Test-Path -LiteralPath (Join-Path $unpacked '63/cygwin'))) { throw 'Terminal runtime missing.' }
New-Item -ItemType Directory -Path $vendor -Force | Out-Null
# Both paths are fixed children of this package, never source/recovery disks.
if (!( [IO.Path]::GetFullPath($unpacked).StartsWith([IO.Path]::GetFullPath($PSScriptRoot) + [IO.Path]::DirectorySeparatorChar)) -or
    !( [IO.Path]::GetFullPath($target).StartsWith([IO.Path]::GetFullPath($PSScriptRoot) + [IO.Path]::DirectorySeparatorChar))) { throw 'Unsafe destination' }
Move-Item -LiteralPath $unpacked -Destination $target
Write-Output 'Official PhotoRec/TestDisk 7.2 installed and hash verified. No recovery process was started.'

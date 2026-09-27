# SPDX-License-Identifier: GPL-3.0-only
param(
    [string]$Sdk = "$env:LOCALAPPDATA\Android\Sdk",
    [string]$NdkVersion = '25.2.9519653'
)
$ErrorActionPreference = 'Stop'
$revision = 'f2448a8797c85814aa892efc1ab8707900fbcc78'
$headers = @{
    'openxr.h' = '17e8e334a7ad0c6933b31143330d4771010e393df5d5d9d08566eb15bb171a15'
    'openxr_platform_defines.h' = 'a458ba5777415f2de518fdcdcc87fcf8651ba0468c9f69a101378672aad80946'
}
$include = Join-Path $PSScriptRoot 'native\include'
New-Item -ItemType Directory -Force (Join-Path $include 'openxr') | Out-Null
foreach ($name in $headers.Keys) {
    $path = Join-Path $include "openxr\$name"
    if (-not (Test-Path -LiteralPath $path)) {
        Invoke-WebRequest -UseBasicParsing "https://raw.githubusercontent.com/KhronosGroup/OpenXR-SDK/$revision/include/openxr/$name" -OutFile $path
    }
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $headers[$name]) {
        throw "Header hash mismatch: $path. No compilation performed."
    }
}
# Header copyright notices are preserved; we use the MIT alternative of their
# Apache-2.0 OR MIT grant. See LICENSES/OpenXR-MIT.txt.
$toolchain = Join-Path $Sdk "ndk\$NdkVersion\toolchains\llvm\prebuilt\windows-x86_64"
$clang = Join-Path $toolchain 'bin\clang.exe'
if (-not (Test-Path -LiteralPath $clang)) { throw "Install Android NDK $NdkVersion or pass -Sdk / -NdkVersion." }
$output = Join-Path $PSScriptRoot 'native\libopenxr_loader_generic.so'
& $clang --target=aarch64-linux-android29 "--sysroot=$toolchain/sysroot" -shared -fPIC -O2 -Wall -Wextra -Werror '-Wl,-Bsymbolic' '-Wl,-soname,libopenxr_loader_generic.so' -I $include (Join-Path $PSScriptRoot 'native\frame_bridge.c') -ldl -llog -o $output
if ($LASTEXITCODE -ne 0) { throw 'Adapter compilation failed' }
Get-FileHash -LiteralPath $output -Algorithm SHA256

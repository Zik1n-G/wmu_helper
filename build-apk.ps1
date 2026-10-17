$ErrorActionPreference = "Stop"

# Zik1nG 课表 APK 手动构建（参照外刊工作站的工具链：aapt2 -> javac -> d8 -> jar -> zipalign -> apksigner）
$scriptRoot = "D:\Vibecoding Project\projects\WMU\curriculum_table_get"
$androidRoot = Join-Path $scriptRoot "android"
$sdkRoot = if ($env:ANDROID_SDK_ROOT) { $env:ANDROID_SDK_ROOT } elseif ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { Join-Path $env:LOCALAPPDATA "Android\Sdk" }
$buildToolsRoot = Join-Path $sdkRoot "build-tools"
$platformRoot = Join-Path $sdkRoot "platforms"

$buildTools = Get-ChildItem -LiteralPath $buildToolsRoot -Directory | Sort-Object Name -Descending | Select-Object -First 1
$platform = Get-ChildItem -LiteralPath $platformRoot -Directory | Where-Object { $_.Name -eq "android-36.1" } | Select-Object -First 1
if (-not $buildTools -or -not $platform) {
    throw "Android Build Tools 36.1.0 and platform android-36.1 are required."
}

$aapt2 = Join-Path $buildTools.FullName "aapt2.exe"
$d8 = Join-Path $buildTools.FullName "d8.bat"
$zipalign = Join-Path $buildTools.FullName "zipalign.exe"
$apksigner = Join-Path $buildTools.FullName "apksigner.bat"
$aapt = Join-Path $buildTools.FullName "aapt.exe"
$androidJar = Join-Path $platform.FullName "android.jar"

# JDK 工具
$prevPref = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$javaSettings = & java -XshowSettings:properties -version 2>&1
$ErrorActionPreference = $prevPref
$javaHomeLine = ($javaSettings | Select-String 'java.home' | Select-Object -First 1).ToString()
$javaHome = ($javaHomeLine -replace '.*java.home\s*=\s*', '').Trim()
$javac = Join-Path $javaHome "bin\javac.exe"
$jar = Join-Path $javaHome "bin\jar.exe"
$keytool = Join-Path $javaHome "bin\keytool.exe"
foreach ($tool in @($javac, $jar, $keytool, $aapt2, $d8, $zipalign, $apksigner, $aapt)) {
    if (-not (Test-Path -LiteralPath $tool)) { throw "Required tool is missing: $tool" }
}

$buildRoot = Join-Path $androidRoot "build\manual"
$outputRoot = Join-Path $androidRoot "build\outputs\apk\debug"
New-Item -ItemType Directory -Force -Path $buildRoot, $outputRoot | Out-Null

$manifest = Join-Path $androidRoot "app\src\main\AndroidManifest.xml"
$resources = Join-Path $androidRoot "app\src\main\res"
$assets = Join-Path $androidRoot "app\src\main\assets"
$javaRoot = Join-Path $androidRoot "app\src\main\java"

$compiledResources = Join-Path $buildRoot "compiled-res.zip"
$generated = Join-Path $buildRoot "gen"
$classes = Join-Path $buildRoot "classes"
$dex = Join-Path $buildRoot "dex"
$baseApk = Join-Path $buildRoot "base.apk"
$alignedApk = Join-Path $buildRoot "aligned.apk"
$signedApk = Join-Path $outputRoot "Zik1nG-Schedule-debug.apk"
$keystore = Join-Path $androidRoot "debug.keystore"

Write-Output "==> aapt2 compile"
& $aapt2 compile --dir $resources -o $compiledResources
if ($LASTEXITCODE -ne 0) { throw "aapt2 compile failed" }

Write-Output "==> aapt2 link"
& $aapt2 link -I $androidJar --manifest $manifest --java $generated --auto-add-overlay `
    --min-sdk-version 23 --target-sdk-version 36 --version-code 1 --version-name 1.0.0 `
    -A $assets -o $baseApk $compiledResources
if ($LASTEXITCODE -ne 0) { throw "aapt2 link failed" }

Write-Output "==> javac"
New-Item -ItemType Directory -Force -Path $classes, $dex | Out-Null
$javaSources = @(Get-ChildItem -LiteralPath $generated -Recurse -Filter '*.java' | Select-Object -ExpandProperty FullName) + `
               @(Get-ChildItem -LiteralPath $javaRoot -Recurse -Filter '*.java' | Select-Object -ExpandProperty FullName)
if ($javaSources.Count -lt 2) { throw "Java sources not found ($($javaSources.Count))" }
# JDK 25 下 -source 8 + -bootclasspath 会报「在平台类中找不到程序包 java.lang」
# （android.jar 的 java.lang 不完整）。改用 -source 17（平台类来自 JDK）+
# -classpath 提供 android.jar 作为 API stub；再用 d8 把字节码降到 min-api 23。
& $javac -source 17 -target 17 -classpath $androidJar -nowarn -d $classes @javaSources
if ($LASTEXITCODE -ne 0) { throw "javac failed" }

$classFiles = Get-ChildItem -LiteralPath $classes -Recurse -Filter '*.class' | Select-Object -ExpandProperty FullName
if (-not $classFiles) { throw "javac produced no class files" }
if (-not (Test-Path -LiteralPath (Join-Path $classes "com\zik1ng\schedule\MainActivity.class"))) {
    throw "MainActivity.class was not compiled"
}

Write-Output "==> d8 (dex)"
& $d8 --lib $androidJar --min-api 23 --output $dex @classFiles
if ($LASTEXITCODE -ne 0) { throw "d8 failed" }
if (-not (Test-Path -LiteralPath (Join-Path $dex "classes.dex"))) { throw "d8 produced no classes.dex" }

Write-Output "==> jar (insert dex + assets)"
& $jar uf $baseApk -C $dex classes.dex
if ($LASTEXITCODE -ne 0) { throw "jar dex insert failed" }

# aapt2 -A 在 Windows 上可能存错分隔符/重复条目，统一 dedupe 一遍
$dedupedApk = Join-Path $buildRoot "deduped.apk"
$dedupeTool = "D:\Vibecoding Project\projects\Project_Foreign Journal Reading Workstation\module_android-app\tools\dedupe-apk-entries.py"
if (Test-Path -LiteralPath $dedupeTool) {
    & python $dedupeTool $baseApk $dedupedApk
    if ($LASTEXITCODE -ne 0) { throw "dedupe-apk-entries failed" }
    Move-Item -Force $dedupedApk $baseApk
} else {
    Write-Output "    (dedupe tool not found, skipping)"
}

Write-Output "==> keystore"
if (-not (Test-Path -LiteralPath $keystore)) {
    & $keytool -genkeypair -keystore $keystore -storepass android -keypass android `
        -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 `
        -dname "CN=Android Debug,O=Android,C=US"
    if ($LASTEXITCODE -ne 0) { throw "keytool failed" }
}

Write-Output "==> zipalign"
& $zipalign -f 4 $baseApk $alignedApk
if ($LASTEXITCODE -ne 0) { throw "zipalign failed" }

Write-Output "==> apksigner sign"
& $apksigner sign --ks $keystore --ks-pass pass:android --key-pass pass:android `
    --ks-key-alias androiddebugkey --out $signedApk $alignedApk
if ($LASTEXITCODE -ne 0) { throw "apksigner sign failed" }

Write-Output "==> verify"
& $apksigner verify --verbose $signedApk
if ($LASTEXITCODE -ne 0) { throw "apksigner verify failed" }

Write-Output ""
Write-Output "APK built: $signedApk"
& $aapt dump badging $signedApk | Select-Object -First 3

# AURA OS — запуск (режим web: дашборд + ядро + аватар + трей)
# • Защита от дублей: если Аура уже жива — второй раз не стартуем
# • Чистка: старые/зависшие процессы Ауры убираются перед запуском

$ErrorActionPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false) } catch {}

$root = 'C:\aura_os'
$py = 'C:\Users\User\AppData\Local\Programs\Python\Python311\pythonw.exe'

# Все процессы Ауры: ядро (main.py) и окна аватаров (aura_live2d.py)
$all = @(Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and
    $_.CommandLine -and
    ($_.CommandLine -match 'main\.py|aura_live2d\.py') -and
    ($_.CommandLine -notmatch 'mcp-servers|opencode')
})
$core = @($all | Where-Object { $_.CommandLine -match 'main\.py' })

function Test-AuraAlive {
    try {
        $r = Invoke-WebRequest 'http://localhost:8000/api/health' -UseBasicParsing -TimeoutSec 4
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

$alive = Test-AuraAlive

# Процесс есть, а порт ещё не отвечает — возможно, она ещё поднимается: даём шанс
if (-not $alive -and $core.Count -ge 1) {
    Start-Sleep -Seconds 10
    $alive = Test-AuraAlive
}

# Дубль-защита: жива и ровно один экземпляр — не трогаем
if ($alive -and $core.Count -le 1) {
    Write-Host '[aura] Аура уже запущена — второй экземпляр не нужен.'
    exit 0
}

# Чистим всё старое (в т.ч. дубли, если их несколько)
if ($all.Count -gt 0) {
    $ids = ($all | ForEach-Object { $_.ProcessId }) -join ', '
    Write-Host "[aura] Убираю старые процессы: $ids"
    foreach ($p in $all) { Stop-Process -Id $p.ProcessId -Force }
    Start-Sleep -Seconds 3
}

Start-Process -FilePath $py -ArgumentList 'main.py', '--web' -WorkingDirectory $root -WindowStyle Hidden
Write-Host '[aura] Запущено. Ядро поднимется за ~30-60 сек, окна аватара — следом.'

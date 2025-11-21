# PowerShell script для установки переменных окружения для production
# Использование: .\setup-prod-env.ps1

Write-Host "Generating unique passwords for production environment..." -ForegroundColor Green

# Функция для генерации случайных паролей
function Generate-RandomPassword {
    param([int]$Length = 32)
    $chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*'
    $random = 1..$Length | ForEach-Object { Get-Random -Maximum $chars.length }
    return -join ($chars[$random])
}

# PostgreSQL Database
$env:POSTGRES_PASSWORD = Generate-RandomPassword -Length 32
$env:POSTGRES_USER = "hydro"
$env:POSTGRES_DB = "hydro"

# Laravel Reverb (WebSocket)
$env:REVERB_APP_ID = "app"
$env:REVERB_APP_KEY = Generate-RandomPassword -Length 32
$env:REVERB_APP_SECRET = Generate-RandomPassword -Length 48
$env:REVERB_AUTO_START = "true"
$env:REVERB_HOST = "0.0.0.0"

# Grafana
$env:GRAFANA_ADMIN_USER = "admin"
$env:GRAFANA_ADMIN_PASSWORD = Generate-RandomPassword -Length 24

# MQTT Passwords (for different services)
$env:MQTT_MQTT_BRIDGE_PASS = Generate-RandomPassword -Length 24
$env:MQTT_AUTOMATION_ENGINE_PASS = Generate-RandomPassword -Length 24
$env:MQTT_HISTORY_LOGGER_PASS = Generate-RandomPassword -Length 24
$env:MQTT_SCHEDULER_PASS = Generate-RandomPassword -Length 24

# Laravel API Token (optional - можно сгенерировать позже)
# $env:LARAVEL_API_TOKEN = "your_laravel_api_token_here"

Write-Host "Environment variables set successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Unique passwords generated for production environment." -ForegroundColor Green
Write-Host ""
Write-Host "IMPORTANT: Save these passwords securely! They are unique and will be different on next run." -ForegroundColor Yellow
Write-Host ""
Write-Host "To validate docker-compose config, run:" -ForegroundColor Cyan
Write-Host "  docker-compose -f docker-compose.prod.yml config" -ForegroundColor Cyan
Write-Host ""
Write-Host "To start production environment, run:" -ForegroundColor Cyan
Write-Host "  docker-compose -f docker-compose.prod.yml up -d" -ForegroundColor Cyan


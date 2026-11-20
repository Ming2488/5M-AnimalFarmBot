$ErrorActionPreference = "Stop"

Write-Host "==============================" -ForegroundColor Cyan
Write-Host " FIVE M ANIMAL FARM BOT" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Host "Python is not installed." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit
}

$work = Join-Path $env:TEMP "AnimalFarmBot"
New-Item -ItemType Directory -Force -Path $work | Out-Null

$base = "https://raw.githubusercontent.com/Ming2488/5M-AnimalFarmBot/main"

Write-Host "Downloading bot and images..."

$files = @(
    "animal_farm.py",
    "animal_buy_button.png",
    "animal_feed_button.png",
    "animal_collect_button.png"
)

foreach ($file in $files) {
    Invoke-WebRequest "$base/$file" -OutFile "$work/$file"
}

Write-Host "Installing libraries..."

py -m pip install pyautogui keyboard

Write-Host "Starting bot..." -ForegroundColor Green

py "$work/animal_farm.py"

Read-Host "Press Enter to exit"

$ErrorActionPreference = "Stop"

Write-Host "==============================" -ForegroundColor Cyan
Write-Host " FIVE M ANIMAL FARM BOT" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan

# ตรวจสอบ Python
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Host "Python is not installed." -ForegroundColor Red
    Write-Host "Download Python from https://www.python.org/downloads/"
    Read-Host "Press Enter to exit"
    exit
}

# สร้างโฟลเดอร์ชั่วคราว
$work = Join-Path $env:TEMP "AnimalFarmBot"
New-Item -ItemType Directory -Force -Path $work | Out-Null

# GitHub
$base = "https://raw.githubusercontent.com/Ming2488/FiveM-AnimalFarmBot/main"

Write-Host "Downloading bot..."

# ดาวน์โหลดบอท
Invoke-WebRequest "$base/animal_farm.py" -OutFile "$work/animal_farm.py"

# ติดตั้งไลบรารี
py -m pip install pyautogui keyboard

Write-Host "Starting bot..." -ForegroundColor Green

# เปิดบอท
py "$work/animal_farm.py"

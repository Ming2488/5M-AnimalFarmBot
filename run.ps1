$ErrorActionPreference = "Stop"

Clear-Host

Write-Host "==============================" -ForegroundColor Cyan
Write-Host " FIVE M ANIMAL FARM BOT" -ForegroundColor Cyan
Write-Host " AUTO INSTALLER" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan

# CHECK PYTHON
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Python is not installed." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit
}

# WORK DIRECTORY
$work = Join-Path $env:TEMP "AnimalFarmBot"
New-Item -ItemType Directory -Force -Path $work | Out-Null

# GITHUB SOURCE
$base = "https://raw.githubusercontent.com/Ming2488/5M-AnimalFarmBot/main"

# DOWNLOAD FILES
$files = @(
    "animal_farm.py",
    "animal_buy_button.png",
    "animal_feed_button.png",
    "animal_collect_button.png"
)

Write-Host ""
Write-Host "[1/4] Downloading bot and images..." -ForegroundColor Yellow

foreach ($file in $files) {
    try {
        Invoke-WebRequest "$base/$file" -OutFile (Join-Path $work $file)
        Write-Host "[OK] $file" -ForegroundColor Green
    }
    catch {
        Write-Host "[ERROR] Failed to download $file" -ForegroundColor Red
        Write-Host $_
        Read-Host "Press Enter to exit"
        exit
    }
}

# INSTALL LIBRARIES
Write-Host ""
Write-Host "[2/4] Installing required libraries..." -ForegroundColor Yellow

py -m pip install --upgrade pyautogui keyboard opencv-python pillow

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Library installation failed." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit
}

# CHECK LIBRARIES
Write-Host ""
Write-Host "[3/4] Checking libraries..." -ForegroundColor Yellow

py -c "import pyautogui, keyboard, cv2, numpy, PIL"

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Library verification failed." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit
}

Write-Host "[OK] All libraries installed." -ForegroundColor Green

# START BOT
Write-Host ""
Write-Host "[4/4] Starting bot..." -ForegroundColor Yellow
Write-Host "==============================" -ForegroundColor Cyan

py (Join-Path $work "animal_farm.py")

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] Bot exited with an error." -ForegroundColor Red
}

Write-Host ""
Read-Host "Press Enter to exit"

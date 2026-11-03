@echo off
setlocal
cd /d "%~dp0"

REM Odstranit Mark of the Web (blokace stazenych souboru SmartScreenem)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%~dp0' -Recurse -Force -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue" >nul 2>&1

if not exist ".portable" (
    echo Pripravuji prenositelnou instalaci...
    call "%~dp0install.bat"
    if errorlevel 1 (
        exit /b 1
    )
)

REM pyw / pythonw = GUI bez konzole; start ukonci toto CMD okamzite
where pyw >nul 2>&1
if %errorlevel%==0 (
    start "" /D "%~dp0" pyw -3 "%~dp0main.py"
    exit /b 0
)

where pythonw >nul 2>&1
if %errorlevel%==0 (
    start "" /D "%~dp0" pythonw "%~dp0main.py"
    exit /b 0
)

where py >nul 2>&1
if %errorlevel%==0 (
    start "" /D "%~dp0" py -3 "%~dp0main.py"
    exit /b 0
)

where python >nul 2>&1
if %errorlevel%==0 (
    start "" /D "%~dp0" python "%~dp0main.py"
    exit /b 0
)

echo Python 3 was not found. Run install.bat first. / Python 3 nebyl nalezen. Spustte nejdrive install.bat.
pause
exit /b 1

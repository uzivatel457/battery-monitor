@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PY_VER=3.12.10"
set "PY_INSTALLER=%TEMP%\python-%PY_VER%-amd64.exe"
set "PY_URL=https://www.python.org/ftp/python/%PY_VER%/python-%PY_VER%-amd64.exe"
set "EXIT_CODE=0"
set "PYTHON_EXE="
set "PYTHON_ARGS="

set "UI=en"
for /f "usebackq delims=" %%L in (`powershell -NoProfile -Command "try { [cultureinfo]::CurrentUICulture.TwoLetterISOLanguageName } catch { 'en' }"`) do set "UI=%%L"
if /I "%UI%"=="cs" goto :msg_cs
if /I "%UI%"=="sk" goto :msg_sk
if /I "%UI%"=="de" goto :msg_de
if /I "%UI%"=="pl" goto :msg_pl
if /I "%UI%"=="fr" goto :msg_fr
if /I "%UI%"=="es" goto :msg_es
goto :msg_en

:msg_cs
set "M_TITLE=Battery monitor by u457 - instalace"
set "M_UNBLOCK=Odblokovavam soubory v teto slozce (Windows: stazeno z internetu)..."
set "M_NO_PY=Python 3 nebyl nalezen."
set "M_GET=Stahuji instalator Python"
set "M_GET_FAIL=Stazeni Pythonu selhalo. Zkontrolujte internet nebo stahnete rucne:"
set "M_NO_FILE=Instalacni soubor Pythonu nebyl vytvoren."
set "M_SETUP=Spoustim instalaci Pythonu (uzivatelska instalace, PATH, tcl/tk). Pockejte na dokonceni."
set "M_SETUP_FAIL=Instalace Pythonu skoncila s kodem"
set "M_SETUP_HINT=Zkuste spustit instalator znovu a zaskrtnete Add to PATH a tcl/tk."
set "M_INSTALLED=Python nainstalovan. Obnovuji PATH v teto session..."
set "M_PATH1=Python je nainstalovan, ale v teto session jeste neni v PATH."
set "M_PATH2=Zavrete toto okno a spustte install.bat znovu, nebo spustte run.bat."
set "M_FOUND=Nalezen Python:"
set "M_PREP=Pripravuji Battery monitor by u457..."
set "M_DEF=Volitelne: pridavam vyjimku Windows Defender pro tuto slozku (muze vyzadat UAC)..."
set "M_DONE=Hotovo. Spustte run.bat nebo BatteryMonitor.vbs"
set "M_FAIL=Instalace selhala, kod"
set "M_KEY=Stisknete libovolnou klavesu pro ukonceni..."
goto :msg_ready

:msg_sk
set "M_TITLE=Battery monitor by u457 - instalacia"
set "M_UNBLOCK=Odblokuvam subory v tomto priecinku (Windows: stiahnute z internetu)..."
set "M_NO_PY=Python 3 sa nenasiel."
set "M_GET=Stahujem instalator Python"
set "M_GET_FAIL=Stiahnutie Pythonu zlyhalo. Skontrolujte internet alebo stiahnite rucne:"
set "M_NO_FILE=Instalacny subor Pythonu nebol vytvoreny."
set "M_SETUP=Spustam instalaciu Pythonu (pouzivatelska instalacia, PATH, tcl/tk). Pockajte na dokoncenie."
set "M_SETUP_FAIL=Instalacia Pythonu skoncila s kodom"
set "M_SETUP_HINT=Skuste spustit instalator znova a zaskrtnite Add to PATH a tcl/tk."
set "M_INSTALLED=Python je nainstalovany. Obnovujem PATH v tejto session..."
set "M_PATH1=Python je nainstalovany, ale v tejto session este nie je v PATH."
set "M_PATH2=Zavrite toto okno a spustite install.bat znova, alebo spustite run.bat."
set "M_FOUND=Najdeny Python:"
set "M_PREP=Pripravujem Battery monitor by u457..."
set "M_DEF=Volitelne: pridavam vynimku Windows Defender pre tento priecinok (moze vyzadovat UAC)..."
set "M_DONE=Hotovo. Spustite run.bat alebo BatteryMonitor.vbs"
set "M_FAIL=Instalacia zlyhala, kod"
set "M_KEY=Stlacte lubovolny klaves pre ukoncenie..."
goto :msg_ready

:msg_de
set "M_TITLE=Battery monitor by u457 - Installation"
set "M_UNBLOCK=Entsperre heruntergeladene Dateien in diesem Ordner..."
set "M_NO_PY=Python 3 wurde nicht gefunden."
set "M_GET=Lade den Python-Installer"
set "M_GET_FAIL=Download von Python fehlgeschlagen. Internet pruefen oder manuell laden:"
set "M_NO_FILE=Die Python-Installationsdatei wurde nicht erstellt."
set "M_SETUP=Starte die Python-Installation (Benutzer, PATH, tcl/tk). Bitte warten."
set "M_SETUP_FAIL=Python-Installation endete mit Code"
set "M_SETUP_HINT=Installer erneut starten und Add to PATH sowie tcl/tk waehlen."
set "M_INSTALLED=Python wurde installiert. PATH dieser Sitzung wird aktualisiert..."
set "M_PATH1=Python ist installiert, aber in dieser Sitzung noch nicht im PATH."
set "M_PATH2=Fenster schliessen und install.bat oder run.bat erneut starten."
set "M_FOUND=Python gefunden:"
set "M_PREP=Bereite Battery monitor by u457 vor..."
set "M_DEF=Optional: Windows-Defender-Ausnahme fuer diesen Ordner (UAC moeglich)..."
set "M_DONE=Fertig. Starten Sie run.bat oder BatteryMonitor.vbs"
set "M_FAIL=Installation fehlgeschlagen, Code"
set "M_KEY=Beliebige Taste zum Beenden..."
goto :msg_ready

:msg_pl
set "M_TITLE=Battery monitor by u457 - instalacja"
set "M_UNBLOCK=Odblokowuje pobrane pliki w tym folderze..."
set "M_NO_PY=Nie znaleziono Python 3."
set "M_GET=Pobieram instalator Python"
set "M_GET_FAIL=Pobieranie Python nie powiodlo sie. Sprawdz internet albo pobierz recznie:"
set "M_NO_FILE=Plik instalacyjny Python nie zostal utworzony."
set "M_SETUP=Uruchamiam instalacje Python (uzytkownik, PATH, tcl/tk). Prosze czekac."
set "M_SETUP_FAIL=Instalacja Python zakonczyla sie kodem"
set "M_SETUP_HINT=Uruchom instalator ponownie i zaznacz Add to PATH oraz tcl/tk."
set "M_INSTALLED=Python zostal zainstalowany. Odswiezam PATH tej sesji..."
set "M_PATH1=Python jest zainstalowany, ale w tej sesji nie ma go jeszcze w PATH."
set "M_PATH2=Zamknij okno i uruchom install.bat albo run.bat ponownie."
set "M_FOUND=Znaleziono Python:"
set "M_PREP=Przygotowuje Battery monitor by u457..."
set "M_DEF=Opcjonalnie: wyjatek Windows Defender dla tego folderu (moze wymagac UAC)..."
set "M_DONE=Gotowe. Uruchom run.bat albo BatteryMonitor.vbs"
set "M_FAIL=Instalacja nie powiodla sie, kod"
set "M_KEY=Nacisnij dowolny klawisz, aby zakonczyc..."
goto :msg_ready

:msg_fr
set "M_TITLE=Battery monitor by u457 - installation"
set "M_UNBLOCK=Deblocage des fichiers telecharges dans ce dossier..."
set "M_NO_PY=Python 3 est introuvable."
set "M_GET=Telechargement de l'installateur Python"
set "M_GET_FAIL=Echec du telechargement de Python. Verifiez Internet ou telechargez :"
set "M_NO_FILE=Le fichier d'installation Python n'a pas ete cree."
set "M_SETUP=Installation de Python (utilisateur, PATH, tcl/tk). Veuillez patienter."
set "M_SETUP_FAIL=L'installation de Python s'est terminee avec le code"
set "M_SETUP_HINT=Relancez l'installateur et cochez Add to PATH et tcl/tk."
set "M_INSTALLED=Python est installe. Mise a jour du PATH de cette session..."
set "M_PATH1=Python est installe, mais pas encore dans le PATH de cette session."
set "M_PATH2=Fermez cette fenetre puis relancez install.bat ou run.bat."
set "M_FOUND=Python trouve :"
set "M_PREP=Preparation de Battery monitor by u457..."
set "M_DEF=Optionnel : exception Windows Defender pour ce dossier (UAC possible)..."
set "M_DONE=Termine. Lancez run.bat ou BatteryMonitor.vbs"
set "M_FAIL=Echec de l'installation, code"
set "M_KEY=Appuyez sur une touche pour quitter..."
goto :msg_ready

:msg_es
set "M_TITLE=Battery monitor by u457 - instalacion"
set "M_UNBLOCK=Desbloqueando los archivos descargados de esta carpeta..."
set "M_NO_PY=No se encontro Python 3."
set "M_GET=Descargando el instalador de Python"
set "M_GET_FAIL=Fallo la descarga de Python. Compruebe Internet o descarguelo:"
set "M_NO_FILE=No se creo el archivo de instalacion de Python."
set "M_SETUP=Iniciando la instalacion de Python (usuario, PATH, tcl/tk). Espere."
set "M_SETUP_FAIL=La instalacion de Python termino con el codigo"
set "M_SETUP_HINT=Ejecute el instalador de nuevo y marque Add to PATH y tcl/tk."
set "M_INSTALLED=Python instalado. Actualizando PATH de esta sesion..."
set "M_PATH1=Python esta instalado, pero aun no esta en el PATH de esta sesion."
set "M_PATH2=Cierre esta ventana y ejecute install.bat o run.bat de nuevo."
set "M_FOUND=Python encontrado:"
set "M_PREP=Preparando Battery monitor by u457..."
set "M_DEF=Opcional: excepcion de Windows Defender para esta carpeta (puede pedir UAC)..."
set "M_DONE=Listo. Ejecute run.bat o BatteryMonitor.vbs"
set "M_FAIL=La instalacion fallo, codigo"
set "M_KEY=Pulse una tecla para salir..."
goto :msg_ready

:msg_en
set "M_TITLE=Battery monitor by u457 - setup"
set "M_UNBLOCK=Unblocking downloaded files in this folder..."
set "M_NO_PY=Python 3 was not found."
set "M_GET=Downloading the Python installer"
set "M_GET_FAIL=Python download failed. Check the internet or download it manually:"
set "M_NO_FILE=The Python installer file was not created."
set "M_SETUP=Starting the Python setup (per-user, PATH, tcl/tk). Please wait."
set "M_SETUP_FAIL=Python setup finished with code"
set "M_SETUP_HINT=Run the installer again and include Add to PATH and tcl/tk."
set "M_INSTALLED=Python was installed. Refreshing PATH for this session..."
set "M_PATH1=Python is installed, but it is not on PATH in this session yet."
set "M_PATH2=Close this window and run install.bat again, or run run.bat."
set "M_FOUND=Python found:"
set "M_PREP=Preparing Battery monitor by u457..."
set "M_DEF=Optional: adding a Windows Defender exclusion for this folder (UAC may appear)..."
set "M_DONE=Done. Start run.bat or BatteryMonitor.vbs"
set "M_FAIL=Setup failed, code"
set "M_KEY=Press any key to close..."

:msg_ready
echo ========================================
echo  %M_TITLE%
echo ========================================
echo.

REM Odblokovani souboru stazenych z internetu (Mark of the Web / Zone.Identifier).
REM Bez toho Windows SmartScreen casto blokuje .bat / .vbs / .py.
echo %M_UNBLOCK%
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%~dp0' -Recurse -Force -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue"
echo.

call :find_python
if defined PYTHON_EXE goto :have_python

echo %M_NO_PY%
echo %M_GET% %PY_VER% ...
echo   %PY_URL%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_INSTALLER%' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo.
    echo %M_GET_FAIL%
    echo   %PY_URL%
    set "EXIT_CODE=1"
    goto :finish
)

if not exist "%PY_INSTALLER%" (
    echo %M_NO_FILE%
    set "EXIT_CODE=1"
    goto :finish
)

echo.
echo %M_SETUP%
echo.

REM /passive = prubeh s UI, bez dalsich otazek
start /wait "" "%PY_INSTALLER%" /passive InstallAllUsers=0 PrependPath=1 Include_tcltk=1 Include_pip=1 Include_launcher=1 Include_test=0 SimpleInstall=1
set "PY_SETUP_ERR=!ERRORLEVEL!"

del /f /q "%PY_INSTALLER%" >nul 2>&1

if not "!PY_SETUP_ERR!"=="0" (
    echo %M_SETUP_FAIL% !PY_SETUP_ERR!.
    echo %M_SETUP_HINT%
    set "EXIT_CODE=1"
    goto :finish
)

echo %M_INSTALLED%
call :refresh_path
call :find_python
if not defined PYTHON_EXE (
    echo.
    echo %M_PATH1%
    echo %M_PATH2%
    set "EXIT_CODE=1"
    goto :finish
)

:have_python
if defined PYTHON_ARGS (
    echo %M_FOUND% %PYTHON_EXE% %PYTHON_ARGS%
) else (
    echo %M_FOUND% %PYTHON_EXE%
)
echo.

echo %M_PREP%
if defined PYTHON_ARGS (
    "%PYTHON_EXE%" %PYTHON_ARGS% "%~dp0install.py"
) else (
    "%PYTHON_EXE%" "%~dp0install.py"
)
set "EXIT_CODE=!ERRORLEVEL!"
echo.

if "!EXIT_CODE!"=="0" (
    echo %M_DEF%
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0add_defender_exclusion.ps1" -TargetPath "%~dp0"
    echo.
    echo %M_DONE%
) else (
    echo %M_FAIL% !EXIT_CODE!.
)

:finish
echo.
echo ========================================
echo  %M_KEY%
echo ========================================
pause >nul
exit /b %EXIT_CODE%


:find_python
set "PYTHON_EXE="
set "PYTHON_ARGS="

where py >nul 2>&1
if !errorlevel!==0 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
    if !errorlevel!==0 (
        for /f "delims=" %%P in ('where py 2^>nul') do (
            set "PYTHON_EXE=%%P"
            set "PYTHON_ARGS=-3"
            exit /b 0
        )
    )
)

where python >nul 2>&1
if !errorlevel!==0 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
    if !errorlevel!==0 (
        for /f "delims=" %%P in ('where python 2^>nul') do (
            set "PYTHON_EXE=%%P"
            set "PYTHON_ARGS="
            exit /b 0
        )
    )
)

if exist "%LocalAppData%\Programs\Python\Launcher\py.exe" (
    "%LocalAppData%\Programs\Python\Launcher\py.exe" -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
    if !errorlevel!==0 (
        set "PYTHON_EXE=%LocalAppData%\Programs\Python\Launcher\py.exe"
        set "PYTHON_ARGS=-3"
        exit /b 0
    )
)

for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
    if exist "%%~D\python.exe" (
        "%%~D\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
        if !errorlevel!==0 (
            set "PYTHON_EXE=%%~D\python.exe"
            set "PYTHON_ARGS="
            exit /b 0
        )
    )
)
exit /b 1


:refresh_path
set "NEWPATH="
for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "NEWPATH=%%B"
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do (
    if defined NEWPATH (
        set "NEWPATH=%%B;!NEWPATH!"
    ) else (
        set "NEWPATH=%%B"
    )
)
if defined NEWPATH set "PATH=!NEWPATH!"
exit /b 0

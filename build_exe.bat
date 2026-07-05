@echo off
setlocal EnableExtensions

cd /d "%~dp0"

echo ================================
echo DocImport build
echo ================================

where py >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python launcher "py" not found.
    echo Install Python 3.12 x64 and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    py -3.12 -m venv venv
    if errorlevel 1 (
        echo ERROR: Could not create venv with Python 3.12.
        echo Check: py -0p
        pause
        exit /b 1
    )
)

call "venv\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Could not activate venv.
    pause
    exit /b 1
)

echo Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 goto build_error

echo Installing requirements...
python -m pip install -r requirements.txt
if errorlevel 1 goto build_error

echo Building EXE...
python -m PyInstaller --noconfirm --clean DocImport.spec
if errorlevel 1 goto build_error

echo.
echo DONE.
echo Build folder: dist\DocImport
echo Copy data, input, output, logs and optional tesseract folder next to DocImport.exe.
pause
exit /b 0

:build_error
echo.
echo BUILD FAILED.
pause
exit /b 1

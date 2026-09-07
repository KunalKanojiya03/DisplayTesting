@echo off
setlocal
rem Always run from this script's own directory, regardless of where it's invoked from.
cd /d "%~dp0"
rem Prefer a local virtual environment if one exists, otherwise fall back to
rem whatever "python" resolves to on PATH.
set "PYTHON=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON=%~dp0.venv\Scripts\python.exe"
echo Using Python: %PYTHON%
"%PYTHON%" --version
if errorlevel 1 (
    echo.
    echo ERROR: Could not find a working Python interpreter.
    goto :fail
)
"%PYTHON%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller is not installed for %PYTHON%.
    echo Install it first with: "%PYTHON%" -m pip install pyinstaller
    goto :fail
)

rem Ensure runtime-output folders exist, since Git does not track empty
rem directories - a fresh clone/checkout (e.g. in CI) may be missing these
rem entirely, which would break --add-data below.
for %%D in (
    "Alpha_Image"
    "Batch"
    "Captured_Img_LCD"
    "Captured_Img_LED"
    "Captured_Img_LED_white"
    "Failed_images\failed_led"
) do (
    if not exist "%~dp0%%~D" (
        echo Creating missing folder: %%~D
        mkdir "%~dp0%%~D"
    )
)

echo.
echo Building DisplayUtility3.0 ...
echo.
"%PYTHON%" -m PyInstaller ^
    --noconfirm --onedir --windowed ^
    --icon "%~dp0resources\splash_img.ico" ^
    --name "DisplayUtility3.0" ^
    --contents-directory "data" ^
    --clean ^
    --add-data "%~dp0generate_report.py;." ^
    --add-data "%~dp0inference_report.csv;." ^
    --add-data "%~dp0pyqt5_app.py;." ^
    --add-data "%~dp0Alpha_Image;Alpha_Image/" ^
    --add-data "%~dp0Batch;Batch/" ^
    --add-data "%~dp0Captured_Img_LCD;Captured_Img_LCD/" ^
    --add-data "%~dp0Captured_Img_LED;Captured_Img_LED/" ^
    --add-data "%~dp0Captured_Img_LED_white;Captured_Img_LED_white/" ^
    --add-data "%~dp0config_files;config_files/" ^
    --add-data "%~dp0Failed_images;Failed_images/" ^
    --add-data "%~dp0general;general/" ^
    --add-data "%~dp0models;models/" ^
    --add-data "%~dp0resources;resources/" ^
    --add-data "%~dp0template;template/" ^
    --add-data "%~dp0yolov5;yolov5/" ^
    "%~dp0pyqt5_app.py"
if errorlevel 1 (
    echo.
    echo BUILD FAILED. See the PyInstaller output above for details.
    goto :fail
)
echo.
echo Build succeeded.
echo Output: %~dp0dist\DisplayUtility3.0\
goto :end
:fail
echo.
echo Build did not complete successfully.
exit /b 1
:end
rem Skip the interactive pause when running non-interactively (CI sets CI=true).
if not defined CI pause
endlocal
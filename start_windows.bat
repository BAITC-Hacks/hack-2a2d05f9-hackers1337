@echo off
setlocal
cd /d "%~dp0"

set "APP_PYTHON=.venv\Scripts\python.exe"
if exist "%APP_PYTHON%" (
    "%APP_PYTHON%" -c "import streamlit, pyarrow, openai, docx, pypdf" >nul 2>nul
    if errorlevel 1 set "APP_PYTHON=.venv-repair\Scripts\python.exe"
) else (
    set "APP_PYTHON=.venv-repair\Scripts\python.exe"
)

if not exist "%APP_PYTHON%" (
    echo Окружение приложения ещё не установлено.
    echo Сначала дважды нажми setup_windows.bat.
    pause
    exit /b 1
)

"%APP_PYTHON%" -m streamlit run app.py
if errorlevel 1 (
    echo.
    echo Приложение завершилось с ошибкой. Если не хватает библиотеки,
    echo запусти setup_windows.bat и пересоздай окружение.
    pause
)


@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Не найден Python Launcher.
    echo Установи 64-битный Python 3.12: https://www.python.org/downloads/windows/
    echo В установщике включи "Python Launcher" и "Add Python to PATH".
    pause
    exit /b 1
)

py -3.12 --version >nul 2>nul
if errorlevel 1 (
    echo Не найден Python 3.12.
    echo Установи 64-битный Python 3.12: https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

if exist ".venv" (
    echo.
    echo Будет пересоздана только папка .venv с библиотеками Python.
    echo Файлы приложения и ключ в .env останутся нетронутыми.
    choice /C YN /M "Продолжить и создать окружение заново"
    if errorlevel 2 exit /b 1
)

echo.
echo Создаю чистое окружение Python 3.12...
py -3.12 -m venv --clear .venv
if errorlevel 1 goto failed

echo Обновляю pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed

echo Устанавливаю библиотеки приложения...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

if not exist ".env" copy ".env.example" ".env" >nul

echo.
echo Готово. Добавь API-ключ в .env и запусти start_windows.bat.
pause
exit /b 0

:failed
echo.
echo Установка не завершилась. Посмотри ошибку выше и попробуй снова.
pause
exit /b 1


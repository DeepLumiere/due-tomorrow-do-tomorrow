@echo off
echo.
echo ============================================================
echo   SmartPark Parking Management System
echo   Build and Launch
echo ============================================================
echo.

where java >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Java not found. Install JDK 17+ and add to PATH.
    pause
    exit /b 1
)
echo [OK] Java detected

echo.
echo [1/2] Compiling Java sources...
if not exist classes mkdir classes

for /r src %%f in (*.java) do set JAVA_FILES=!JAVA_FILES! "%%f"
setlocal EnableDelayedExpansion

dir /s /b src\*.java > sources.txt
javac -d classes @sources.txt
del sources.txt

if %errorlevel% neq 0 (
    echo ERROR: Compilation failed.
    pause
    exit /b 1
)
echo [OK] Compilation successful

echo.
echo [2/2] Starting SmartPark server...
echo       Open browser: http://localhost:8080
echo       Press Ctrl+C to stop
echo.

java -cp classes com.parking.ParkingServer
pause

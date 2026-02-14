@echo off
REM ClaimTrackr Setup Script for Windows
REM This script automates the setup process for ClaimTrackr

echo ======================================================
echo   ClaimTrackr - AI-Powered Claims Processing Setup
echo ======================================================
echo.

REM Check Python installation
echo [1/6] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.8 or higher.
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version
echo [OK] Python found

REM Check Ollama installation
echo.
echo [2/6] Checking Ollama installation...
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Ollama not found.
    echo Please download and install Ollama from: https://ollama.ai/download
    pause
    exit /b 1
)
echo [OK] Ollama is installed

REM Check if Ollama is running
echo.
echo [3/6] Checking Ollama service...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Ollama service is not running
    echo Please open a new terminal and run: ollama serve
    echo Then press any key to continue...
    pause >nul
)
echo [OK] Ollama service is accessible

REM Pull required models
echo.
echo [4/6] Checking and pulling required models...
echo This may take a while on first run...

echo Checking llama3.1...
ollama list | findstr /C:"llama3.1" >nul 2>&1
if %errorlevel% neq 0 (
    echo Pulling llama3.1...
    ollama pull llama3.1
)

echo Checking llama3.2...
ollama list | findstr /C:"llama3.2" >nul 2>&1
if %errorlevel% neq 0 (
    echo Pulling llama3.2...
    ollama pull llama3.2
)

echo Checking nomic-embed-text...
ollama list | findstr /C:"nomic-embed-text" >nul 2>&1
if %errorlevel% neq 0 (
    echo Pulling nomic-embed-text...
    ollama pull nomic-embed-text
)

echo [OK] All models are ready

REM Create virtual environment
echo.
echo [5/6] Setting up Python virtual environment...
if not exist "venv" (
    python -m venv venv
    echo [OK] Virtual environment created
) else (
    echo [OK] Virtual environment already exists
)

REM Install dependencies
echo.
echo Installing Python dependencies...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)
echo [OK] Dependencies installed successfully

REM Create necessary directories
echo.
echo [6/6] Creating necessary directories...
if not exist "documents" mkdir documents
if not exist "Bills" mkdir Bills
echo [OK] Directories created

REM Success message
echo.
echo ======================================================
echo          Setup completed successfully!
echo ======================================================
echo.
echo Next steps:
echo 1. Add your insurance policy PDF files to the 'documents' folder
echo 2. Ensure Ollama is running (run 'ollama serve' in a separate terminal)
echo 3. Run the application:
echo    venv\Scripts\activate
echo    python main_BUPA_ollama.py
echo 4. Open your browser to http://localhost:8081
echo.
echo Press any key to exit...
pause >nul

@echo off
echo ============================================
echo   CGE System Backend Startup
echo ============================================
echo.

echo [1/3] Starting Ollama in background...
start /B ollama serve 2>nul
timeout /t 3 /nobreak >nul

echo [2/3] Checking Ollama status...
ollama list 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo   WARNING: Ollama not running. LLaVA vision OCR will be disabled.
    echo   Install Ollama from https://ollama.com
    echo   Then run: ollama pull llava:7b
) else (
    echo   Ollama is running.
)
echo.

echo [3/3] Starting FastAPI backend on port 8000...
cd backend
uvicorn main:app --reload --port 8000

@echo off
echo ===================================================
echo   Starting MineSafe AI Dual-Engine System...
echo ===================================================

:: 1. Start AI Engine (FastAPI 8000)
echo [1/3] Starting AI Engine (YOLO)...
start "AI Engine" cmd /k "cd ai-backend-yolo && if not exist minesafe_env (echo [Self-Healing] Rebuilding AI Environment... && python -m venv minesafe_env && call minesafe_env\Scripts\activate && cd backend && pip install -r requirements.txt ultralytics pandas python-multipart) else (call minesafe_env\Scripts\activate && cd backend) && uvicorn app:app --port 8000 --reload"

:: 2. Start Rule Engine (Flask 5000)
echo [2/3] Starting Rule Engine (Flask)...
start "Rule Engine" cmd /k "cd rule-backend-flask && if not exist venv (echo [Self-Healing] Rebuilding Rule Environment... && python -m venv venv && call venv\Scripts\activate && pip install -r requirements.txt) else (call venv\Scripts\activate) && python app.py"

:: 3. Start UI Frontend (Vite 5173)
echo [3/3] Starting UI Frontend...
start "UI Frontend" cmd /k "cd minesafe-ui && npm run dev"

echo ===================================================
echo   System is launching!
echo   NOTE: The first run will take a few minutes to download and install AI packages.
echo   Please wait until the left and middle windows stop downloading and show green text.
echo   Then visit: http://localhost:5173
echo ===================================================
pause
@echo off
echo Starting FXGuard AI...
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
pause

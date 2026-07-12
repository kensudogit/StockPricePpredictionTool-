@echo off
cd /d "%~dp0\.."
python scripts\run_tests.py
echo Open http://localhost:8000/tests/ or test-results\index.html

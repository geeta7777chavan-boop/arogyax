"""
run.py - Backend entry point
Run: python run.py
"""
import subprocess
import sys
import os
from pathlib import Path

# Get the project root directory
project_root = Path(__file__).resolve().parent

# Change to backend directory
os.chdir(project_root / "backend")

# Get the venv python path
venv_python = project_root / ".venv" / "Scripts" / "python.exe"

# Use venv python if it exists, otherwise use system python
python_exe = str(venv_python) if venv_python.exists() else sys.executable

# Run uvicorn (bind to 0.0.0.0 to allow connections from localhost and other interfaces)
sys.exit(subprocess.run([python_exe, "-m", "uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]).returncode)


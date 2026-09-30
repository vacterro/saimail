@echo off
setlocal
pushd "%~dp0"
python -c "import PySide6, cryptography" >nul 2>nul
if errorlevel 1 (
  echo SAIMAIL needs its desktop dependencies.
  echo From this folder run: python -m pip install -e ".[gui]"
  pause
  popd
  exit /b 2
)
pythonw -m saimail.gui_app
popd

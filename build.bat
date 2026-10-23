@echo off
rem Local release build: icon, version resource, program folder, portable ZIP and (if Inno Setup is installed) the installer.
rem The version comes from version.py. Needs:  pip install -r requirements-dev.txt
setlocal
cd /d "%~dp0"
set PY=python
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe

%PY% tools\make_icon.py || exit /b 1
%PY% tools\make_version_info.py || exit /b 1
%PY% -m PyInstaller --noconfirm Handy2.spec || exit /b 1
%PY% tools\make_portable.py || exit /b 1

for /f %%v in ('%PY% -c "from version import __version__; print(__version__)"') do set VERSION=%%v
set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if exist "%ISCC%" (
  "%ISCC%" /DMyAppVersion=%VERSION% installer.iss || exit /b 1
) else (
  echo Inno Setup 6 is not installed: skipping the installer.
)
echo Done: version %VERSION%

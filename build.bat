@echo off
rem CAD 버전 변환기 exe 만들기 (Python 3.9 이상 필요)
chcp 65001 > nul
python -m pip install -r requirements-dev.txt || goto :error
python -m PyInstaller --noconfirm --onefile --windowed --name CADVersionConverter main.py || goto :error
echo.
echo 완료: dist\CADVersionConverter.exe
pause
exit /b 0
:error
echo 빌드에 실패했습니다.
pause
exit /b 1

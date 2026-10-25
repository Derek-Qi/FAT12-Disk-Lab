@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo 请先安装 Python 3.11 或更高版本，并加入 PATH。
  pause
  exit /b 1
)
if not exist data mkdir data
if not exist data\work.img copy /y data\demo.img data\work.img >nul
python -m fat12lab --image data/work.img --create --web
if errorlevel 1 pause


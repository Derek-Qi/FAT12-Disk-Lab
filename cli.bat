@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m fat12lab --image data/work.img --create
pause


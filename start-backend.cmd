@echo off
chcp 65001 >nul
rem 后端启动脚本：用绝对路径直接调用 back\.venv 的解释器，
rem 因此在任何目录双击都能启动，也不依赖终端里 python 是否在 PATH。
rem 改了后端代码后，关掉本窗口再重新双击本脚本即可生效（没有热重载）。
cd /d "%~dp0back"
set "PY=%~dp0back\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERROR] 找不到虚拟环境解释器：
  echo         %PY%
  echo         请在 back 目录执行： uv venv .venv
  pause
  exit /b 1
)
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
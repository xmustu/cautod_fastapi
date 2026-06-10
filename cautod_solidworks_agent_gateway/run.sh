@echo off
REM 在 cautod_fastapi 目录下启动 v1/v2/v3 gateway（8501/8502/8503）
cd /d "%~dp0.."
for %%I in ("%~dp0..\..\algorithm\solidworks_agent") do set "UPSTREAM=%%~fI"

start "agent-v1" cmd /k python -m cautod_solidworks_agent_gateway --upstream "%UPSTREAM%" --version v1 --port 8501
start "agent-v2" cmd /k python -m cautod_solidworks_agent_gateway --upstream "%UPSTREAM%" --version v2 --port 8502
start "agent-v3" cmd /k python -m cautod_solidworks_agent_gateway --upstream "%UPSTREAM%" --version v3 --port 8503

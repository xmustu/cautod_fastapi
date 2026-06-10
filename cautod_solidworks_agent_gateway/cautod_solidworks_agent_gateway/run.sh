cd /d D:\CAutoD
start "agent-v1" cmd /k python -m cautod_solidworks_agent_gateway --upstream D:\CAutoD\algorithm\solidworks_agent --version v1 --port 8501
start "agent-v2" cmd /k python -m cautod_solidworks_agent_gateway --upstream D:\CAutoD\algorithm\solidworks_agent --version v2 --port 8502
start "agent-v3" cmd /k python -m cautod_solidworks_agent_gateway --upstream D:\CAutoD\algorithm\solidworks_agent --version v3 --port 8503
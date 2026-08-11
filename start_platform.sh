#!/bin/bash
# 启动线下活动经营分析平台 Flask 服务 (src/web/app.py)
cd /path/to/project

# 停止旧进程
pkill -f "src.web.app" 2>/dev/null
pkill -f "backend/app.py" 2>/dev/null
sleep 2

# 用 screen 后台启动（脱离终端会话）
screen -dmS platform bash -c '/opt/anaconda3/bin/python3 -m src.web.app > /tmp/platform_server.log 2>&1'
echo "Platform server started in screen session 'platform'"
echo "Log: /tmp/platform_server.log"
echo "URL: http://127.0.0.1:8080/"
echo ""
echo "To stop: screen -S platform -X quit"
echo "To view logs: tail -f /tmp/platform_server.log"

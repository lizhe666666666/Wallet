#!/bin/bash

# 获取正在运行的进程ID
SERVICE_NAME="BinancePriceSocketService.py"
PID=$(ps aux | grep $SERVICE_NAME | grep -v grep | awk '{print $2}')

# 停止现有服务
if [ -z "$PID" ]; then
    echo "No process found for $SERVICE_NAME. Assuming the service is not running."
else
    echo "Stopping process with PID $PID"
    kill $PID
    echo "Service stopped."
fi

# 启动新服务
nohup python BinancePriceSocketService.py &
NEW_PID=$!
echo "Service restarted with new PID $NEW_PID"

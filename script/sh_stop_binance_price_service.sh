#!/bin/bash

# 获取正在运行的进程ID
SERVICE_NAME="BinancePriceSocketService.py"
PID=$(ps aux | grep $SERVICE_NAME | grep -v grep | awk '{print $2}')

if [ -z "$PID" ]; then
    echo "No process found for $SERVICE_NAME"
else
    echo "Stopping process with PID $PID"
    kill $PID
    echo "Service stopped."
fi

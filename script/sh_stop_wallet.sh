#!/bin/bash

# 进入工作目录
cd /root/

# 检查端口5001是否在监听
if netstat -tnlp | grep -q 5001; then
    echo "服务已在运行，正在停止..."
    # 获取Python应用的进程ID并杀死它
    pid=$(netstat -tnlp | grep :5001 | awk '{print $7}' | cut -d'/' -f1)
    kill $pid
    sleep 5 # 等待进程完全停止
fi

echo "服务停止。"



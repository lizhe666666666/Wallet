#!/bin/bash

# 进入工作目录
cd /root/

# 检查端口5001是否在监听
if netstat -tnlp | grep -q 5001; then
    echo "服务已在运行，正在重启..."
    # 获取Python应用的进程ID并杀死它
    pid=$(netstat -tnlp | grep :5001 | awk '{print $7}' | cut -d'/' -f1)
    kill $pid
    sleep 5 # 等待进程完全停止
fi

# 启动服务
echo "启动服务..."
# gunicorn -w 4 -b 0.0.0.0:5001 web:app --timeout 500 --log-level debug --access-logfile access1.log --error-logfile error1.log &
# 把标准日志都重定向到 error1.log
gunicorn -w 4 -b 0.0.0.0:5001 web:app --timeout 500 --log-level debug --access-logfile access1.log --error-logfile error1.log >error1.log 2>&1 &


echo "服务启动完成。"


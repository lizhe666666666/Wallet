#!/bin/bash
# 启动服务
echo "启动服务..."
gunicorn -w 4 -b 0.0.0.0:5002 web:app --timeout 500 --log-level debug --access-logfile access1.log --error-logfile error1.log



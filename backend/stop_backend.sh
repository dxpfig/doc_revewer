#!/bin/bash
# 停止 doc_revewer 后端服务

echo "正在查找并停止后端进程..."

# 查找占用 18000 端口的进程
PID=$(lsof -ti:18000 2>/dev/null)

if [ -n "$PID" ]; then
    echo "找到进程 PID: $PID"
    kill -9 $PID
    echo "已停止进程 $PID"
else
    echo "没有找到占用 18000 端口的进程"
fi

# 也尝试通过进程名查找
PYPID=$(ps aux | grep "python.*main.py" | grep -v grep | awk '{print $2}' | head -1)

if [ -n "$PYPID" ]; then
    echo "找到 Python 进程: $PYPID"
    kill -9 $PYPID 2>/dev/null
    echo "已停止进程 $PYPID"
fi

echo "完成！现在可以重新启动后端："
echo "  cd ~/doc_revewer/backend"
echo "  python main.py"

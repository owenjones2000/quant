#!/bin/bash
# ============================================================
# A股量化交易系统 - 启动/停止/状态管理脚本
# 用法: ./run.sh [start|stop|restart|status|logs|sync]
# ============================================================

BACKEND_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$BACKEND_DIR/logs/server.pid"
LOG_FILE="$BACKEND_DIR/logs/server.log"
PYTHON="python3"
PORT=8000

mkdir -p "$BACKEND_DIR/logs"

start() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
        echo "⚠️  服务已在运行 (PID: $(cat $PID_FILE))"
        return 1
    fi
    echo "🚀 启动服务..."
    cd "$BACKEND_DIR"
    nohup $PYTHON -m uvicorn app:app --host 0.0.0.0 --port $PORT \
        >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2
    if kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
        echo "✅ 服务已启动 (PID: $(cat $PID_FILE), 端口: $PORT)"
        echo "   API文档: http://localhost:$PORT/docs"
    else
        echo "❌ 启动失败，查看日志: tail -f $LOG_FILE"
    fi
}

stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo "⚠️  服务未运行"
        return 1
    fi
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        rm -f "$PID_FILE"
        echo "✅ 服务已停止 (PID: $PID)"
    else
        rm -f "$PID_FILE"
        echo "⚠️  进程不存在，已清理PID文件"
    fi
}

status() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
        echo "✅ 运行中 (PID: $(cat $PID_FILE))"
        echo "   API: http://localhost:$PORT/docs"
        echo "   日志: $LOG_FILE"
    else
        echo "❌ 未运行"
    fi
}

logs() {
    tail -f "$LOG_FILE"
}

sync_data() {
    echo "📥 手动触发数据同步..."
    cd "$BACKEND_DIR"
    nohup $PYTHON -c "
import warnings; warnings.filterwarnings('ignore')
from data.sync import daily_sync
daily_sync()
" >> "$BACKEND_DIR/logs/sync.log" 2>&1 &
    echo "✅ 同步任务已在后台启动，查看进度: tail -f $BACKEND_DIR/logs/sync.log"
}

full_sync() {
    echo "📥 全量同步（首次使用，约10-15分钟）..."
    cd "$BACKEND_DIR"
    nohup $PYTHON -c "
import warnings; warnings.filterwarnings('ignore')
from data.sync import sync_stock_list, sync_daily_full
from data.store import get_stock_count
sync_stock_list()
sync_daily_full(max_workers=8)
print(f'完成! DB中{get_stock_count()}只股票')
" >> "$BACKEND_DIR/logs/sync.log" 2>&1 &
    echo "✅ 全量同步已在后台启动，查看进度: tail -f $BACKEND_DIR/logs/sync.log"
}

case "$1" in
    start)    start ;;
    stop)     stop ;;
    restart)  stop; sleep 1; start ;;
    status)   status ;;
    logs)     logs ;;
    sync)     sync_data ;;
    fullsync) full_sync ;;
    *)
        echo "用法: $0 {start|stop|restart|status|logs|sync|fullsync}"
        echo ""
        echo "  start     启动API服务（后台运行）"
        echo "  stop      停止服务"
        echo "  restart   重启服务"
        echo "  status    查看运行状态"
        echo "  logs      实时查看日志"
        echo "  sync      手动触发增量数据同步"
        echo "  fullsync  全量同步（首次使用）"
        ;;
esac

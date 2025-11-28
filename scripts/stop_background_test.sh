#!/bin/bash
# 백그라운드 Job 생성 및 모니터링 스크립트 종료

########################################################
# created_at: 2025-11-28
# author: LEEYH205
# description: 백그라운드 테스트 종료 스크립트
# version: 1.0.0
########################################################

LOG_DIR="/tmp"
PID_FILE_CREATOR="$LOG_DIR/background_job_creator.pid"
PID_FILE_MONITOR="$LOG_DIR/background_monitor_variants.pid"

echo "============================================================"
echo "백그라운드 테스트 종료"
echo "============================================================"

# Job 생성 스크립트 종료
if [ -f "$PID_FILE_CREATOR" ]; then
    CREATOR_PID=$(cat "$PID_FILE_CREATOR")
    if ps -p "$CREATOR_PID" > /dev/null 2>&1; then
        echo "🛑 Job 생성 스크립트 종료 중... (PID: $CREATOR_PID)"
        kill "$CREATOR_PID" 2>/dev/null || true
        sleep 2
        if ps -p "$CREATOR_PID" > /dev/null 2>&1; then
            echo "⚠️  강제 종료 중..."
            kill -9 "$CREATOR_PID" 2>/dev/null || true
        fi
        echo "✓ Job 생성 스크립트 종료 완료"
    else
        echo "⚠️  Job 생성 스크립트가 실행 중이 아닙니다."
    fi
    rm -f "$PID_FILE_CREATOR"
else
    echo "⚠️  Job 생성 스크립트 PID 파일을 찾을 수 없습니다."
fi

# 모니터링 스크립트 종료
if [ -f "$PID_FILE_MONITOR" ]; then
    MONITOR_PID=$(cat "$PID_FILE_MONITOR")
    if ps -p "$MONITOR_PID" > /dev/null 2>&1; then
        echo "🛑 모니터링 스크립트 종료 중... (PID: $MONITOR_PID)"
        kill "$MONITOR_PID" 2>/dev/null || true
        sleep 2
        if ps -p "$MONITOR_PID" > /dev/null 2>&1; then
            echo "⚠️  강제 종료 중..."
            kill -9 "$MONITOR_PID" 2>/dev/null || true
        fi
        echo "✓ 모니터링 스크립트 종료 완료"
    else
        echo "⚠️  모니터링 스크립트가 실행 중이 아닙니다."
    fi
    rm -f "$PID_FILE_MONITOR"
else
    echo "⚠️  모니터링 스크립트 PID 파일을 찾을 수 없습니다."
fi

# 남은 프로세스 확인 및 종료
REMAINING_CREATOR=$(pgrep -f "background_job_creator.py" || true)
REMAINING_MONITOR=$(pgrep -f "background_monitor_variants.py" || true)

if [ -n "$REMAINING_CREATOR" ]; then
    echo "⚠️  남은 Job 생성 프로세스 종료 중..."
    pkill -f "background_job_creator.py" || true
fi

if [ -n "$REMAINING_MONITOR" ]; then
    echo "⚠️  남은 모니터링 프로세스 종료 중..."
    pkill -f "background_monitor_variants.py" || true
fi

echo ""
echo "============================================================"
echo "✅ 백그라운드 테스트 종료 완료"
echo "============================================================"
echo ""
echo "로그 파일 위치:"
echo "  - Job 생성: $LOG_DIR/job_creator.log"
echo "  - 모니터링: $LOG_DIR/job_monitor.log"
echo "============================================================"


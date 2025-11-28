#!/bin/bash
# 백그라운드 Job 생성 및 모니터링 스크립트 실행
# 두 스크립트를 함께 백그라운드로 실행하여 롱런 테스트 수행

########################################################
# created_at: 2025-11-28
# author: LEEYH205
# description: 백그라운드 테스트 실행 스크립트
# version: 1.0.0
########################################################

set -e

# 기본값 설정
TENANT_ID="longrun_test"
CREATE_INTERVAL=60
VARIANTS_COUNT=3
CHECK_INTERVAL=30
MAX_WAIT_MINUTES=20
SCAN_INTERVAL=10
LOG_DIR="/tmp"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# PID 파일 경로
PID_FILE_CREATOR="$LOG_DIR/background_job_creator.pid"
PID_FILE_MONITOR="$LOG_DIR/background_monitor_variants.pid"

# 로그 파일 경로
LOG_FILE_CREATOR="$LOG_DIR/job_creator.log"
LOG_FILE_MONITOR="$LOG_DIR/job_monitor.log"

# 파라미터 파싱
while [[ $# -gt 0 ]]; do
    case $1 in
        --tenant-id)
            TENANT_ID="$2"
            shift 2
            ;;
        --create-interval)
            CREATE_INTERVAL="$2"
            shift 2
            ;;
        --variants-count)
            VARIANTS_COUNT="$2"
            shift 2
            ;;
        --check-interval)
            CHECK_INTERVAL="$2"
            shift 2
            ;;
        --max-wait-minutes)
            MAX_WAIT_MINUTES="$2"
            shift 2
            ;;
        --scan-interval)
            SCAN_INTERVAL="$2"
            shift 2
            ;;
        --log-dir)
            LOG_DIR="$2"
            PID_FILE_CREATOR="$LOG_DIR/background_job_creator.pid"
            PID_FILE_MONITOR="$LOG_DIR/background_monitor_variants.pid"
            LOG_FILE_CREATOR="$LOG_DIR/job_creator.log"
            LOG_FILE_MONITOR="$LOG_DIR/job_monitor.log"
            shift 2
            ;;
        --help)
            echo "사용법: $0 [옵션]"
            echo ""
            echo "옵션:"
            echo "  --tenant-id ID              Tenant ID (기본: longrun_test)"
            echo "  --create-interval SECONDS   Job 생성 간격 (기본: 60)"
            echo "  --variants-count COUNT      각 Job당 Variant 개수 (기본: 3)"
            echo "  --check-interval SECONDS    상태 확인 간격 (기본: 30)"
            echo "  --max-wait-minutes MINUTES  최대 대기 시간 (기본: 20)"
            echo "  --scan-interval SECONDS     새 Job 스캔 간격 (기본: 10)"
            echo "  --log-dir DIR              로그 디렉토리 (기본: /tmp)"
            echo "  --help                     이 도움말 표시"
            echo ""
            echo "예시:"
            echo "  $0 --tenant-id my_test --create-interval 60 --variants-count 3"
            exit 0
            ;;
        *)
            echo "알 수 없는 옵션: $1"
            echo "도움말을 보려면 --help를 사용하세요"
            exit 1
            ;;
    esac
done

# 이미 실행 중인지 확인
if [ -f "$PID_FILE_CREATOR" ] && ps -p "$(cat "$PID_FILE_CREATOR")" > /dev/null 2>&1; then
    echo "⚠️  Job 생성 스크립트가 이미 실행 중입니다. (PID: $(cat "$PID_FILE_CREATOR"))"
    echo "   종료하려면: ./scripts/stop_background_test.sh"
    exit 1
fi

if [ -f "$PID_FILE_MONITOR" ] && ps -p "$(cat "$PID_FILE_MONITOR")" > /dev/null 2>&1; then
    echo "⚠️  모니터링 스크립트가 이미 실행 중입니다. (PID: $(cat "$PID_FILE_MONITOR"))"
    echo "   종료하려면: ./scripts/stop_background_test.sh"
    exit 1
fi

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

# 스크립트 파일 확인
CREATOR_SCRIPT="$SCRIPT_DIR/background_job_creator.py"
MONITOR_SCRIPT="$SCRIPT_DIR/background_monitor_variants.py"

if [ ! -f "$CREATOR_SCRIPT" ]; then
    echo "❌ Job 생성 스크립트를 찾을 수 없습니다: $CREATOR_SCRIPT"
    exit 1
fi

if [ ! -f "$MONITOR_SCRIPT" ]; then
    echo "❌ 모니터링 스크립트를 찾을 수 없습니다: $MONITOR_SCRIPT"
    exit 1
fi

echo "============================================================"
echo "백그라운드 테스트 시작"
echo "============================================================"
echo "Tenant ID: $TENANT_ID"
echo "Job 생성 간격: ${CREATE_INTERVAL}초"
echo "Variants 개수: ${VARIANTS_COUNT}개"
echo "상태 확인 간격: ${CHECK_INTERVAL}초"
echo "최대 대기 시간: ${MAX_WAIT_MINUTES}분"
echo "새 Job 스캔 간격: ${SCAN_INTERVAL}초"
echo "로그 디렉토리: $LOG_DIR"
echo "============================================================"
echo ""

# Job 생성 스크립트 실행
echo "🚀 Job 생성 스크립트 시작..."
cd "$PROJECT_ROOT"
nohup python "$CREATOR_SCRIPT" \
    --tenant-id "$TENANT_ID" \
    --create-interval "$CREATE_INTERVAL" \
    --variants-count "$VARIANTS_COUNT" \
    > "$LOG_FILE_CREATOR" 2>&1 &

CREATOR_PID=$!
echo "$CREATOR_PID" > "$PID_FILE_CREATOR"
echo "✓ Job 생성 스크립트 실행 중 (PID: $CREATOR_PID)"
echo "  로그: $LOG_FILE_CREATOR"

# 잠시 대기
sleep 2

# 모니터링 스크립트 실행
echo "🚀 모니터링 스크립트 시작..."
cd "$PROJECT_ROOT"
nohup python "$MONITOR_SCRIPT" \
    --tenant-id "$TENANT_ID" \
    --check-interval "$CHECK_INTERVAL" \
    --max-wait-minutes "$MAX_WAIT_MINUTES" \
    --scan-interval "$SCAN_INTERVAL" \
    > "$LOG_FILE_MONITOR" 2>&1 &

MONITOR_PID=$!
echo "$MONITOR_PID" > "$PID_FILE_MONITOR"
echo "✓ 모니터링 스크립트 실행 중 (PID: $MONITOR_PID)"
echo "  로그: $LOG_FILE_MONITOR"

echo ""
echo "============================================================"
echo "✅ 백그라운드 테스트 시작 완료"
echo "============================================================"
echo "프로세스 ID:"
echo "  - Job 생성: $CREATOR_PID"
echo "  - 모니터링: $MONITOR_PID"
echo ""
echo "로그 파일:"
echo "  - Job 생성: $LOG_FILE_CREATOR"
echo "  - 모니터링: $LOG_FILE_MONITOR"
echo ""
echo "로그 확인:"
echo "  tail -f $LOG_FILE_CREATOR"
echo "  tail -f $LOG_FILE_MONITOR"
echo ""
echo "종료:"
echo "  ./scripts/stop_background_test.sh"
echo "============================================================"


"""Thread-safe 모델 로딩 테스트
여러 variants가 동시에 실행될 때 모델이 한 번만 로드되는지 확인
"""
########################################################
# created_at: 2025-11-28
# updated_at: 2025-11-28
# author: LEEYH205
# description: Thread-safe 모델 로딩 테스트
# version: 2.0.0
########################################################

import sys
import os
import uuid
import time
import subprocess
import re
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal
from sqlalchemy import text
import logging

# test_job_variants_pipeline의 함수를 직접 import
sys.path.insert(0, str(project_root / "test"))
from test_job_variants_pipeline import create_job_with_variants

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_docker_logs(container_name: str, since_seconds: int = 300):
    """Docker 컨테이너 로그 가져오기 (최근 N초)"""
    try:
        result = subprocess.run(
            ['docker', 'logs', '--since', f'{since_seconds}s', container_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10
        )
        return result.stdout.split('\n')
    except FileNotFoundError:
        # Docker 컨테이너 내부에서 실행 중인 경우
        # 로그 파일을 직접 읽거나 다른 방법 사용
        print("  ⚠️  Docker 명령어를 사용할 수 없습니다 (컨테이너 내부 실행 중)")
        print("  → 로그 모니터링을 건너뜁니다.")
        return []
    except Exception as e:
        print(f"❌ Docker 로그 가져오기 오류: {e}")
        return []

def monitor_docker_logs(container_name: str, pattern: str, timeout: int = 60):
    """Docker 컨테이너 로그에서 특정 패턴을 모니터링"""
    print(f"\n{'=' * 60}")
    print(f"Docker 로그 모니터링 시작")
    print(f"  - Container: {container_name}")
    print(f"  - Pattern: {pattern}")
    print(f"  - Timeout: {timeout}초")
    print(f"{'=' * 60}\n")
    
    matches = []
    start_time = time.time()
    last_log_count = 0
    
    try:
        # Docker 로그를 실시간으로 읽기
        process = subprocess.Popen(
            ['docker', 'logs', '-f', '--tail', '0', container_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        pattern_re = re.compile(pattern, re.IGNORECASE)
        
        while True:
            if time.time() - start_time > timeout:
                print(f"\n⏱️  타임아웃 ({timeout}초)")
                break
            
            line = process.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue
            
            if pattern_re.search(line):
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                matches.append({
                    'timestamp': timestamp,
                    'line': line.strip()
                })
                print(f"[{timestamp}] {line.strip()}")
                
                # 일정 개수 이상 매칭되면 중단 (모델 로딩은 한 번만 있어야 함)
                if len(matches) > 10:  # 예상보다 많이 나오면 문제
                    print(f"\n⚠️  예상보다 많은 매칭 발견 ({len(matches)}개)")
                    break
        
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        
    except Exception as e:
        print(f"❌ 로그 모니터링 오류: {e}")
        if 'process' in locals():
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                process.kill()
    
    return matches

def trigger_variants_simultaneously(variants: list):
    """모든 variants를 동시에 트리거 (상태 업데이트)"""
    print(f"\n{'=' * 60}")
    print(f"Variants 동시 트리거")
    print(f"{'=' * 60}")
    
    db = SessionLocal()
    try:
        # 모든 variants를 동시에 업데이트하기 위해 트랜잭션 사용
        print(f"  - 총 {len(variants)}개 variants 상태 업데이트 중...")
        
        for i, variant in enumerate(variants, 1):
            job_variants_id = variant["job_variants_id"]
            
            # 각 variant를 running 상태로 변경하여 트리거 발동
            db.execute(text("""
                UPDATE jobs_variants 
                SET status = 'running',
                    current_step = 'vlm_analyze',
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_variants_id = :job_variants_id
            """), {
                "job_variants_id": uuid.UUID(job_variants_id)
            })
            
            print(f"  [{i}/{len(variants)}] Variant {job_variants_id[:8]}... → running/vlm_analyze")
        
        db.commit()
        print(f"\n✓ 모든 variants 상태 업데이트 완료 (트리거 발동)")
        
    except Exception as e:
        db.rollback()
        print(f"❌ 오류 발생: {e}")
        raise
    finally:
        db.close()

def check_model_loading_count(logs: list):
    """로그에서 모델 로딩 횟수 확인"""
    print(f"\n{'=' * 60}")
    print(f"모델 로딩 횟수 분석")
    print(f"{'=' * 60}")
    
    # 모델 로딩 관련 키워드
    loading_keywords = [
        r'Loading LLaVa model',
        r'Downloading/loading model from Hugging Face',
        r'Loading checkpoint shards',
        r'Model loaded successfully'
    ]
    
    loading_events = []
    
    for keyword in loading_keywords:
        pattern = re.compile(keyword, re.IGNORECASE)
        matches = [log for log in logs if pattern.search(log.get('line', ''))]
        
        if matches:
            print(f"\n📊 '{keyword}' 패턴:")
            for match in matches:
                print(f"  - [{match['timestamp']}] 발견")
            loading_events.extend(matches)
    
    # 중복 제거 (같은 타임스탬프 근처의 이벤트는 하나로 간주)
    unique_events = []
    seen_timestamps = set()
    
    for event in loading_events:
        # 타임스탬프를 초 단위로 반올림하여 중복 제거
        ts_key = event['timestamp'].split(':')[2].split('.')[0]  # 초 단위
        if ts_key not in seen_timestamps:
            unique_events.append(event)
            seen_timestamps.add(ts_key)
    
    print(f"\n📈 분석 결과:")
    print(f"  - 총 모델 로딩 관련 이벤트: {len(loading_events)}개")
    print(f"  - 고유 모델 로딩 시도: {len(unique_events)}개")
    
    if len(unique_events) == 1:
        print(f"\n✅ 성공: 모델이 한 번만 로드되었습니다!")
        return True
    elif len(unique_events) > 1:
        print(f"\n❌ 실패: 모델이 {len(unique_events)}번 로드되었습니다 (예상: 1번)")
        print(f"   → Thread-safe 로딩이 제대로 작동하지 않을 수 있습니다.")
        return False
    else:
        print(f"\n⚠️  경고: 모델 로딩 이벤트를 찾을 수 없습니다.")
        print(f"   → 로그를 확인하거나 타임아웃을 늘려보세요.")
        return None

def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Thread-safe 모델 로딩 테스트")
    parser.add_argument(
        "--variants",
        type=int,
        default=3,
        help="동시에 실행할 Variant 개수 (기본값: 3)"
    )
    parser.add_argument(
        "--container",
        type=str,
        default="feedlyai-work-yh",
        help="Docker 컨테이너 이름 (기본값: feedlyai-work-yh)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="로그 모니터링 타임아웃 (초, 기본값: 120)"
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default="thread_safe_test_tenant",
        help="테넌트 ID (기본값: thread_safe_test_tenant)"
    )
    
    args = parser.parse_args()
    
    variants_count = args.variants
    container_name = args.container
    timeout = args.timeout
    tenant_id = args.tenant_id
    
    print("=" * 60)
    print("Thread-safe 모델 로딩 테스트")
    print("=" * 60)
    print(f"  - 동시 실행 Variant 개수: {variants_count}개")
    print(f"  - Docker 컨테이너: {container_name}")
    print(f"  - 로그 모니터링 타임아웃: {timeout}초")
    print("=" * 60)
    
    # 1. Job 및 Variants 생성
    print("\n" + "=" * 60)
    print("1단계: Job 및 Variants 생성")
    print("=" * 60)
    
    result = create_job_with_variants(
        tenant_id=tenant_id,
        variants_count=variants_count
    )
    job_id = result["job_id"]
    job_variants = result["job_variants"]
    
    print(f"\n✓ 생성 완료:")
    print(f"  - Job ID: {job_id}")
    print(f"  - Variants: {len(job_variants)}개")
    
    # 2. Variants 동시 트리거
    print("\n" + "=" * 60)
    print("3단계: Variants 동시 트리거")
    print("=" * 60)
    
    trigger_start_time = time.time()
    trigger_variants_simultaneously(job_variants)
    trigger_end_time = time.time()
    
    print(f"\n⏱️  트리거 소요 시간: {trigger_end_time - trigger_start_time:.2f}초")
    
    # 3. 로그 모니터링 (트리거 후 일정 시간 동안)
    print("\n" + "=" * 60)
    print("3단계: 로그 모니터링 (모델 로딩 확인)")
    print("=" * 60)
    
    log_pattern = r'(Loading LLaVa model|Downloading/loading model|Loading checkpoint shards|Model loaded successfully|meta tensor)'
    
    print(f"\n⏳ {timeout}초 동안 로그를 모니터링합니다...")
    print(f"   (모델 로딩은 보통 1-2분 정도 소요됩니다)\n")
    
    logs = monitor_docker_logs(container_name, log_pattern, timeout=timeout)
    
    # 4. 결과 분석
    print("\n" + "=" * 60)
    print("4단계: 결과 분석")
    print("=" * 60)
    
    result = check_model_loading_count(logs)
    
    # 6. 최종 결과
    print("\n" + "=" * 60)
    print("최종 결과")
    print("=" * 60)
    
    if result is True:
        print("\n✅ 테스트 성공!")
        print("   → Thread-safe 모델 로딩이 정상적으로 작동합니다.")
        print("   → 여러 variants가 동시에 실행되어도 모델은 한 번만 로드됩니다.")
    elif result is False:
        print("\n❌ 테스트 실패!")
        print("   → 모델이 여러 번 로드되었습니다.")
        print("   → Thread-safe 로딩 로직을 확인해야 합니다.")
    else:
        print("\n⚠️  테스트 결과 불명확")
        print("   → 로그를 직접 확인하거나 타임아웃을 늘려보세요.")
    
    print("\n" + "=" * 60)
    print("테스트 완료")
    print("=" * 60)

if __name__ == "__main__":
    main()


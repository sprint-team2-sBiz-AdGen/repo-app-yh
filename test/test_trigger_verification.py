"""PostgreSQL 트리거 확인 스크립트
Job State Change Notification Trigger가 제대로 생성되었는지 확인
"""
########################################################
# created_at: 2025-11-28
# author: LEEYH205
# description: PostgreSQL 트리거 확인 스크립트
# version: 1.0.0
########################################################

import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal, engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_trigger_function():
    """트리거 함수 존재 확인"""
    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT 
                proname as function_name,
                pg_get_functiondef(oid) as function_definition
            FROM pg_proc
            WHERE proname = 'notify_job_state_change'
        """))
        
        row = result.fetchone()
        if row:
            logger.info("✓ 트리거 함수 'notify_job_state_change' 존재 확인")
            logger.info(f"  함수 정의 (일부): {row[1][:200]}...")
            return True
        else:
            logger.error("❌ 트리거 함수 'notify_job_state_change'를 찾을 수 없습니다")
            return False
    except Exception as e:
        logger.error(f"❌ 트리거 함수 확인 중 오류: {e}", exc_info=True)
        return False
    finally:
        db.close()

def check_trigger():
    """트리거 존재 확인"""
    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT 
                tgname as trigger_name,
                tgrelid::regclass as table_name,
                tgenabled as is_enabled
            FROM pg_trigger
            WHERE tgname = 'job_state_change_trigger'
        """))
        
        row = result.fetchone()
        if row:
            logger.info("✓ 트리거 'job_state_change_trigger' 존재 확인")
            logger.info(f"  테이블: {row[1]}")
            logger.info(f"  활성화: {'Yes' if row[2] == 'O' else 'No'}")
            return True
        else:
            logger.error("❌ 트리거 'job_state_change_trigger'를 찾을 수 없습니다")
            return False
    except Exception as e:
        logger.error(f"❌ 트리거 확인 중 오류: {e}", exc_info=True)
        return False
    finally:
        db.close()

def test_notify():
    """NOTIFY 테스트 (수동)"""
    logger.info("\n" + "=" * 60)
    logger.info("NOTIFY 테스트")
    logger.info("=" * 60)
    logger.info("다음 SQL을 직접 실행하여 테스트할 수 있습니다:")
    logger.info("""
-- 테스트용 job 생성 (이미 있다면 생략)
INSERT INTO jobs (job_id, tenant_id, status, current_step)
VALUES (gen_random_uuid(), 'test_tenant', 'queued', 'img_gen')
ON CONFLICT DO NOTHING;

-- job 상태 업데이트 (트리거 발동)
UPDATE jobs 
SET status = 'done', current_step = 'img_gen'
WHERE tenant_id = 'test_tenant' AND current_step = 'img_gen'
LIMIT 1;

-- 다른 세션에서 LISTEN 확인:
-- LISTEN job_state_changed;
-- (업데이트 후 NOTIFY 메시지가 수신되는지 확인)
    """)

def main():
    """메인 함수"""
    print("\n" + "=" * 60)
    print("PostgreSQL 트리거 확인")
    print("=" * 60)
    
    # 트리거 함수 확인
    print("\n[1/2] 트리거 함수 확인 중...")
    func_ok = check_trigger_function()
    
    # 트리거 확인
    print("\n[2/2] 트리거 확인 중...")
    trigger_ok = check_trigger()
    
    # 결과 요약
    print("\n" + "=" * 60)
    print("확인 결과")
    print("=" * 60)
    if func_ok and trigger_ok:
        print("✓ 모든 트리거가 정상적으로 생성되었습니다!")
        print("\n다음 단계:")
        print("1. 애플리케이션 재시작 (의존성 설치 포함)")
        print("2. 로그에서 'Job State Listener 시작' 메시지 확인")
        print("3. job 상태 변경 시 자동 파이프라인 실행 확인")
    else:
        print("❌ 트리거 생성에 문제가 있습니다.")
        print("\n해결 방법:")
        print("1. db/init/02_job_state_notify_trigger.sql 파일 확인")
        print("2. SQL을 다시 실행하여 트리거 생성")
    
    # NOTIFY 테스트 안내
    print("\n" + "=" * 60)
    test_notify()

if __name__ == "__main__":
    main()


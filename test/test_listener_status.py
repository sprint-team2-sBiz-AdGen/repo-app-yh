#!/usr/bin/env python3
"""리스너 상태 확인 스크립트

YE 파트 개발자가 리스너가 제대로 동작하는지 확인하는 스크립트입니다.

사용 방법:
    python3 test/test_listener_status.py
    python3 test/test_listener_status.py --test-trigger  # 실제 트리거 테스트
"""
########################################################
# created_at: 2025-12-02
# author: LEEYH205
# description: 리스너 상태 확인 및 테스트
# version: 1.0.0
########################################################

import sys
import os
import uuid
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def check_fastapi_server():
    """FastAPI 서버 실행 상태 확인"""
    print("\n" + "="*60)
    print("1. FastAPI 서버 실행 상태 확인")
    print("="*60)
    
    try:
        import requests
        response = requests.get("http://localhost:8000/health", timeout=2)
        if response.status_code == 200:
            print("✅ FastAPI 서버가 실행 중입니다")
            return True
        else:
            print(f"⚠️ FastAPI 서버 응답 코드: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ FastAPI 서버에 연결할 수 없습니다")
        print("   → 서버가 실행 중인지 확인하세요")
        return False
    except Exception as e:
        print(f"❌ FastAPI 서버 확인 중 오류: {e}")
        return False


def check_listener_config():
    """리스너 설정 확인"""
    print("\n" + "="*60)
    print("2. 리스너 설정 확인")
    print("="*60)
    
    try:
        from config import ENABLE_JOB_STATE_LISTENER
        if ENABLE_JOB_STATE_LISTENER:
            print("✅ ENABLE_JOB_STATE_LISTENER = True")
            return True
        else:
            print("❌ ENABLE_JOB_STATE_LISTENER = False")
            print("   → .env 파일에서 ENABLE_JOB_STATE_LISTENER=True로 설정하세요")
            return False
    except Exception as e:
        print(f"❌ 설정 확인 중 오류: {e}")
        return False


def check_listener_logs():
    """리스너 로그 확인"""
    print("\n" + "="*60)
    print("3. 리스너 로그 확인")
    print("="*60)
    
    print("다음 명령어로 리스너 로그를 확인하세요:")
    print("  docker logs feedlyai-work-yh --tail 100 | grep -E 'Job State Listener|LISTENER|리스너'")
    print("\n확인할 로그 메시지:")
    print("  ✅ 'Job State Listener 시작' - 리스너가 시작됨")
    print("  ✅ 'PostgreSQL 연결 성공' - 데이터베이스 연결 성공")
    print("  ✅ 'LISTEN 시작' - NOTIFY 채널 구독 시작")
    print("  ✅ 'Job Variant 상태 변화 감지' - 이벤트 수신 성공")
    
    print("\n실시간 로그 모니터링:")
    print("  docker logs -f feedlyai-work-yh | grep -E 'Job Variant|트리거|trigger'")
    
    return True


def check_postgresql_trigger():
    """PostgreSQL 트리거 확인"""
    print("\n" + "="*60)
    print("4. PostgreSQL 트리거 확인")
    print("="*60)
    
    db = SessionLocal()
    try:
        # 트리거 함수 확인
        trigger_func = db.execute(text("""
            SELECT proname 
            FROM pg_proc 
            WHERE proname = 'notify_job_variant_state_change'
        """)).first()
        
        if trigger_func:
            print("✅ 트리거 함수 존재: notify_job_variant_state_change")
        else:
            print("❌ 트리거 함수를 찾을 수 없습니다")
            print("   → db/init/03_job_variants_state_notify_trigger.sql 실행 필요")
            return False
        
        # 트리거 확인
        trigger = db.execute(text("""
            SELECT tgname 
            FROM pg_trigger 
            WHERE tgname = 'job_variant_state_change_trigger'
        """)).first()
        
        if trigger:
            print("✅ 트리거 존재: job_variant_state_change_trigger")
            return True
        else:
            print("❌ 트리거를 찾을 수 없습니다")
            print("   → db/init/03_job_variants_state_notify_trigger.sql 실행 필요")
            return False
            
    except Exception as e:
        print(f"❌ 트리거 확인 중 오류: {e}")
        return False
    finally:
        db.close()


def test_trigger(db, tenant_id: str = "ye_listener_test_tenant"):
    """실제 트리거 테스트"""
    print("\n" + "="*60)
    print("5. 트리거 테스트 (실제 이벤트 발동)")
    print("="*60)
    
    try:
        # 1. 테스트용 Job 생성
        print("\n[1단계] 테스트용 Job 생성 중...")
        job_id = uuid.uuid4()
        
        # Tenant 생성
        db.execute(text("""
            INSERT INTO tenants (tenant_id, display_name, created_at, updated_at)
            VALUES (:tenant_id, :display_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (tenant_id) DO NOTHING
        """), {
            "tenant_id": tenant_id,
            "display_name": f"Listener Test Tenant"
        })
        db.commit()
        
        # Job 생성
        db.execute(text("""
            INSERT INTO jobs (
                job_id, tenant_id, status, current_step,
                created_at, updated_at
            ) VALUES (
                :job_id, :tenant_id, :status, :current_step,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "status": "done",
            "current_step": "user_img_input"
        })
        db.commit()
        print(f"✅ Job 생성 완료: {job_id}")
        
        # 2. 이미지 asset 생성 (필요한 경우)
        image_asset_id = uuid.uuid4()
        db.execute(text("""
            INSERT INTO image_assets (
                image_asset_id, image_type, image_url, width, height,
                tenant_id, created_at, updated_at
            ) VALUES (
                :image_asset_id, 'generated', :image_url, :width, :height,
                :tenant_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "image_asset_id": image_asset_id,
            "image_url": "/test/listener_test.jpg",
            "width": 100,
            "height": 100,
            "tenant_id": tenant_id
        })
        db.commit()
        
        # 3. Variant 생성 (user_img_input done 상태)
        job_variants_id = uuid.uuid4()
        db.execute(text("""
            INSERT INTO jobs_variants (
                job_variants_id, job_id, img_asset_id, creation_order,
                status, current_step, created_at, updated_at
            ) VALUES (
                :job_variants_id, :job_id, :img_asset_id, :creation_order,
                :status, :current_step, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "job_variants_id": job_variants_id,
            "job_id": job_id,
            "img_asset_id": image_asset_id,
            "creation_order": 1,
            "status": "done",
            "current_step": "user_img_input"
        })
        db.commit()
        print(f"✅ Variant 생성 완료: {job_variants_id}")
        print(f"   상태: user_img_input (done)")
        
        # 4. img_gen 완료 상태로 업데이트 (트리거 발동!)
        print("\n[2단계] img_gen 완료 상태로 업데이트 중... (트리거 발동)")
        print("   → 리스너가 이벤트를 감지하면 로그에 'Job Variant 상태 변화 감지' 메시지가 나타납니다")
        
        db.execute(text("""
            UPDATE jobs_variants
            SET status = 'done',
                current_step = 'img_gen',
                updated_at = CURRENT_TIMESTAMP
            WHERE job_variants_id = :job_variants_id
        """), {"job_variants_id": job_variants_id})
        db.commit()
        
        print("✅ 상태 업데이트 완료: img_gen (done)")
        print("\n[3단계] 리스너 반응 확인")
        print("   다음 명령어로 로그를 확인하세요:")
        print(f"   docker logs feedlyai-work-yh --tail 50 | grep -E 'Job Variant|{job_variants_id[:8]}'")
        print("\n   예상되는 로그:")
        print("   - 'Job Variant 상태 변화 감지: job_variants_id=...'")
        print("   - '[TRIGGER] 파이프라인 단계 트리거 (variant): ...'")
        print("   - '다음 단계: vlm_analyze'")
        
        # 5. 상태 확인
        print("\n[4단계] 상태 확인 (5초 후)")
        import time
        time.sleep(5)
        
        result = db.execute(text("""
            SELECT status, current_step, updated_at
            FROM jobs_variants
            WHERE job_variants_id = :job_variants_id
        """), {"job_variants_id": job_variants_id}).first()
        
        if result:
            status, current_step, updated_at = result
            print(f"   현재 상태: {current_step} ({status})")
            
            if current_step == 'vlm_analyze':
                print("   ✅ 리스너가 정상 작동했습니다! 다음 단계로 자동 진행되었습니다.")
            elif current_step == 'img_gen':
                print("   ⚠️ 아직 img_gen 상태입니다. 리스너가 이벤트를 감지하지 못했을 수 있습니다.")
                print("   → 로그를 확인하세요: docker logs feedlyai-work-yh --tail 100")
            else:
                print(f"   ℹ️ 현재 단계: {current_step}")
        
        print(f"\n✅ 테스트 완료")
        print(f"   Job ID: {job_id}")
        print(f"   Variant ID: {job_variants_id}")
        print(f"   Tenant ID: {tenant_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"트리거 테스트 중 오류: {e}", exc_info=True)
        db.rollback()
        return False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="리스너 상태 확인")
    parser.add_argument(
        "--test-trigger",
        action="store_true",
        help="실제 트리거 테스트 실행"
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default="ye_listener_test_tenant",
        help="테스트용 Tenant ID"
    )
    
    args = parser.parse_args()
    
    print("="*60)
    print("리스너 상태 확인")
    print("="*60)
    
    results = []
    
    # 1. FastAPI 서버 확인
    results.append(("FastAPI 서버", check_fastapi_server()))
    
    # 2. 리스너 설정 확인
    results.append(("리스너 설정", check_listener_config()))
    
    # 3. 리스너 로그 확인 방법 안내
    check_listener_logs()
    
    # 4. PostgreSQL 트리거 확인
    results.append(("PostgreSQL 트리거", check_postgresql_trigger()))
    
    # 5. 트리거 테스트 (옵션)
    if args.test_trigger:
        db = SessionLocal()
        try:
            results.append(("트리거 테스트", test_trigger(db, args.tenant_id)))
        finally:
            db.close()
    else:
        print("\n" + "="*60)
        print("트리거 테스트를 실행하려면:")
        print("  python3 test/test_listener_status.py --test-trigger")
        print("="*60)
    
    # 결과 요약
    print("\n" + "="*60)
    print("확인 결과 요약")
    print("="*60)
    for name, result in results:
        status = "✅ 통과" if result else "❌ 실패"
        print(f"  {name}: {status}")
    
    all_passed = all(result for _, result in results)
    if all_passed:
        print("\n✅ 모든 확인 항목이 통과했습니다!")
    else:
        print("\n⚠️ 일부 확인 항목이 실패했습니다. 위의 메시지를 확인하세요.")
    
    print("="*60)


if __name__ == "__main__":
    main()


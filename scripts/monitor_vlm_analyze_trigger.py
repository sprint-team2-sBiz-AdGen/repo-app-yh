#!/usr/bin/env python3
"""
Job의 variants가 vlm_analyze, queued 상태가 되면 파이프라인 트리거를 확인하는 모니터링 스크립트
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from sqlalchemy import text
import time
from datetime import datetime

def monitor_job_variants(job_id: str):
    """Job의 variants 상태를 모니터링하고 vlm_analyze, queued 상태를 감지"""
    db = SessionLocal()
    
    try:
        print(f"🔍 Job {job_id} 모니터링 시작...")
        print("="*70)
        print("💡 vlm_analyze, queued 상태가 나타나면 파이프라인 트리거를 확인합니다.")
        print()
        
        check_count = 0
        vlm_analyze_queued_detected = False
        
        while check_count < 120:  # 최대 20분 모니터링
            check_count += 1
            current_time = datetime.now().strftime("%H:%M:%S")
            
            # Job 상태
            job = db.execute(text('''
                SELECT status, current_step, updated_at
                FROM jobs
                WHERE job_id = :job_id
            '''), {'job_id': job_id}).first()
            
            if not job:
                print(f"[{check_count}/120] {current_time} - ❌ Job을 찾을 수 없습니다")
                break
            
            job_status, job_step, job_updated = job
            
            # Variants 상태
            variants = db.execute(text('''
                SELECT 
                    job_variants_id,
                    creation_order,
                    current_step,
                    status,
                    updated_at
                FROM jobs_variants
                WHERE job_id = :job_id
                ORDER BY creation_order
            '''), {'job_id': job_id}).fetchall()
            
            if variants:
                print(f"[{check_count}/120] {current_time} - Job: {job_status}/{job_step}, Variants: {len(variants)}개")
                
                for variant in variants:
                    variant_id, order, step, status, updated = variant
                    print(f"  Variant {order}: {status}/{step} (ID: {str(variant_id)[:8]}...)")
                    
                    if step == 'vlm_analyze' and status == 'queued':
                        if not vlm_analyze_queued_detected:
                            vlm_analyze_queued_detected = True
                            print()
                            print("="*70)
                            print("✅✅✅ vlm_analyze, queued 상태 감지!")
                            print(f"  - Variant ID: {variant_id}")
                            print(f"  - Creation Order: {order}")
                            print(f"  - Updated At: {updated}")
                            print()
                            print("🔍 파이프라인 트리거 확인 중...")
                            print("="*70)
                            
                            # 파이프라인 트리거 로그 확인
                            check_pipeline_trigger(job_id, variant_id)
                            
                            # 이후에도 계속 모니터링하여 파이프라인 진행 상황 확인
                            print()
                            print("📊 파이프라인 진행 상황 모니터링 계속...")
                            print()
            else:
                if check_count % 6 == 0:  # 1분마다 한 번만 출력
                    print(f"[{check_count}/120] {current_time} - Job: {job_status}/{job_step}, ⏳ Variants 생성 대기 중...")
            
            time.sleep(10)  # 10초마다 확인
        
        if not vlm_analyze_queued_detected:
            print()
            print("="*70)
            print("⏳ 모니터링 시간 내에 vlm_analyze, queued 상태가 감지되지 않았습니다.")
            print("   JS→YE 파트가 아직 진행 중이거나 다른 상태일 수 있습니다.")
            print("="*70)
    
    finally:
        db.close()

def check_pipeline_trigger(job_id: str, variant_id: str):
    """파이프라인 트리거 로그 확인"""
    import subprocess
    
    print(f"📋 최근 파이프라인 트리거 로그 확인 (Job: {job_id[:8]}..., Variant: {str(variant_id)[:8]}...):")
    print()
    
    # Docker 로그에서 관련 메시지 확인
    try:
        result = subprocess.run(
            ['docker', 'logs', 'feedlyai-work-yh', '--tail', '50', '2>&1'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        logs = result.stdout + result.stderr
        
        # 관련 로그 필터링
        relevant_logs = []
        for line in logs.split('\n'):
            if (job_id[:8] in line or str(variant_id)[:8] in line) and (
                'vlm_analyze' in line.lower() or 
                'trigger' in line.lower() or
                'pipeline' in line.lower() or
                'queued' in line.lower()
            ):
                relevant_logs.append(line)
        
        if relevant_logs:
            print("📝 관련 로그:")
            for log in relevant_logs[-10:]:  # 최근 10개만
                print(f"  {log}")
        else:
            print("  ⚠️ 관련 로그를 찾을 수 없습니다.")
        
        print()
        
        # Variant 상태 재확인
        db = SessionLocal()
        try:
            variant = db.execute(text('''
                SELECT current_step, status, updated_at
                FROM jobs_variants
                WHERE job_variants_id = :variant_id
            '''), {'variant_id': variant_id}).first()
            
            if variant:
                step, status, updated = variant
                print(f"📊 현재 Variant 상태: {status}/{step} (업데이트: {updated})")
                
                if step != 'vlm_analyze' or status != 'queued':
                    print(f"  ⚠️ 상태가 변경되었습니다: {status}/{step}")
                else:
                    print(f"  ✅ 아직 vlm_analyze, queued 상태입니다.")
        finally:
            db.close()
    
    except Exception as e:
        print(f"  ❌ 로그 확인 중 오류: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python monitor_vlm_analyze_trigger.py <job_id>")
        sys.exit(1)
    
    job_id = sys.argv[1]
    monitor_job_variants(job_id)


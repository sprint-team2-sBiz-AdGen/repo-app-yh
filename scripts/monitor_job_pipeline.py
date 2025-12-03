#!/usr/bin/env python3
"""
Job Pipeline 모니터링 스크립트
Job의 진행 상황을 실시간으로 모니터링하고, 완료 시 상세 정보를 출력합니다.
"""

import sys
import os
import time
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from database import SessionLocal


def get_absolute_path(url: str) -> str:
    """URL을 절대 경로로 변환"""
    if not url:
        return None
    
    if url.startswith('/assets/'):
        return url.replace('/assets/', '/opt/feedlyai/assets/')
    elif url.startswith('/'):
        return os.path.join('/opt/feedlyai/assets', url.lstrip('/'))
    else:
        return url


def check_listener_and_trigger_status(job_id: str):
    """리스너와 트리거 상태 확인"""
    import subprocess
    
    print('='*80)
    print('🔍 리스너 및 트리거 상태 확인')
    print('='*80)
    print()
    
    # 리스너 설정 확인
    try:
        from config import ENABLE_JOB_STATE_LISTENER
        if ENABLE_JOB_STATE_LISTENER:
            print('✅ 리스너 활성화됨 (ENABLE_JOB_STATE_LISTENER=True)')
        else:
            print('⚠️  리스너 비활성화됨 (ENABLE_JOB_STATE_LISTENER=False)')
    except Exception as e:
        print(f'⚠️  리스너 설정 확인 실패: {e}')
    
    print()
    
    # 리스너 로그 확인 안내
    print('📋 리스너/트리거 로그 확인:')
    print('  ⚠️  컨테이너 내부에서는 docker 명령어를 사용할 수 없습니다.')
    print('  호스트에서 다음 명령어로 로그를 확인하세요:')
    print()
    print(f'  docker logs feedlyai-work-yh --tail 200 | grep -E "{job_id[:8]}|LISTENER|TRIGGER"')
    print()
    print('  또는 실시간 모니터링:')
    print(f'  docker logs -f feedlyai-work-yh | grep -E "{job_id[:8]}|LISTENER|TRIGGER"')
    print()


def monitor_job(job_id: str, max_iterations: int = 120, check_interval: int = 10):
    """
    Job의 진행 상황을 모니터링합니다.
    
    Args:
        job_id: 모니터링할 Job ID
        max_iterations: 최대 반복 횟수 (기본값: 120, 약 20분)
        check_interval: 확인 간격 (초, 기본값: 10초)
    """
    db = SessionLocal()
    
    try:
        print('='*80)
        print('🔍 Job Pipeline 모니터링 시작')
        print('='*80)
        print(f'Job ID: {job_id}')
        print(f'최대 모니터링 시간: {max_iterations * check_interval / 60:.1f}분')
        print(f'확인 간격: {check_interval}초')
        print()
        
        # 리스너 및 트리거 상태 확인
        check_listener_and_trigger_status(job_id)
        
        # 파이프라인 단계 순서
        pipeline_steps = [
            'vlm_analyze', 'yolo_detect', 'planner', 'overlay',
            'vlm_judge', 'ocr_eval', 'readability_eval', 'iou_eval'
        ]
        
        last_status = {}
        
        for i in range(max_iterations):
            current_time = datetime.now().strftime('%H:%M:%S')
            
            # Job 정보
            job = db.execute(text('''
                SELECT tenant_id, status, current_step, updated_at
                FROM jobs
                WHERE job_id = :job_id
            '''), {'job_id': job_id}).first()
            
            if not job:
                print(f'[{i+1}/{max_iterations}] {current_time} - ❌ Job을 찾을 수 없습니다')
                break
            
            tenant_id, status, step, updated = job
            
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
                # 상태 변경 감지
                current_status = {v[1]: (v[2], v[3]) for v in variants}
                status_changed = current_status != last_status
                
                if status_changed or i % 6 == 0:  # 상태 변경 시 또는 1분마다 출력
                    print(f'[{i+1}/{max_iterations}] {current_time} - Job: {status}/{step}, Variants: {len(variants)}개')
                    
                    for variant in variants:
                        variant_id, order, v_step, v_status, v_updated = variant
                        
                        # 진행률 계산
                        if v_step in pipeline_steps:
                            step_index = pipeline_steps.index(v_step)
                            progress = ((step_index + 1) / len(pipeline_steps)) * 100
                        elif v_status == 'done' and v_step == 'iou_eval':
                            progress = 100
                        else:
                            progress = 0
                        
                        status_icon = '✅' if v_status == 'done' and v_step == 'iou_eval' else '⏳' if v_status == 'running' else '🔄' if v_status == 'queued' else '✅' if v_status == 'done' else '❌'
                        
                        print(f'  {status_icon} Variant {order}: {v_status}/{v_step} ({progress:.1f}%)')
                        
                        # 상태 변경 표시
                        if order in last_status:
                            old_step, old_status = last_status[order]
                            if old_step != v_step or old_status != v_status:
                                print(f'      📍 변경: {old_status}/{old_step} → {v_status}/{v_step}')
                    
                    last_status = current_status
                    print()
                
                # 모든 variants가 완료되었는지 확인
                all_done = all(v[3] == 'done' and v[2] == 'iou_eval' for v in variants)
                if all_done:
                    print(f'\n✅ 모든 variants가 파이프라인을 완료했습니다!')
                    print()
                    break
            else:
                if i % 6 == 0:  # 1분마다 한 번만 출력
                    print(f'[{i+1}/{max_iterations}] {current_time} - Job: {status}/{step}, ⏳ Variants 생성 대기 중...')
            
            time.sleep(check_interval)
        
        # 최종 상태 및 상세 정보 출력
        print_final_status(db, job_id)
        
    finally:
        db.close()


def print_final_status(db: SessionLocal, job_id: str):
    """최종 상태 및 상세 정보를 출력합니다."""
    print('='*80)
    print('📊 최종 상태 및 상세 정보')
    print('='*80)
    print()
    
    # Job 정보
    job = db.execute(text('''
        SELECT tenant_id, status, current_step, created_at, updated_at
        FROM jobs
        WHERE job_id = :job_id
    '''), {'job_id': job_id}).first()
    
    if job:
        tenant_id, status, step, created, updated = job
        print(f'Job ID: {job_id}')
        print(f'Tenant ID: {tenant_id}')
        print(f'Status: {status}')
        print(f'Current Step: {step}')
        print(f'Created: {created}')
        print(f'Updated: {updated}')
        print()
    
    # Variants 상세 정보
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
        print(f'Variants ({len(variants)}개):')
        print()
        
        for variant in variants:
            variant_id, order, v_step, v_status, v_updated = variant
            print(f'{"="*80}')
            print(f'Variant {order}')
            print(f'{"="*80}')
            print(f'  Variant ID: {str(variant_id)[:8]}...')
            print(f'  Status: {v_status}')
            print(f'  Current Step: {v_step}')
            print(f'  Updated: {v_updated}')
            print()
            
            # Planner 이미지 경로
            print('  🗺️  Planner 이미지:')
            # planner_proposals의 layout에서 proposal_image_asset_id 조회 시도
            planner_image = db.execute(text('''
                SELECT 
                    pp.layout->>'proposal_image_asset_id' as proposal_img_id,
                    pp.layout->>'proposal_image_url' as proposal_img_url
                FROM planner_proposals pp
                JOIN jobs_variants jv ON pp.image_asset_id = jv.img_asset_id
                WHERE jv.job_variants_id = :variant_id
                ORDER BY pp.created_at DESC
                LIMIT 1
            '''), {'variant_id': variant_id}).first()
            
            if planner_image and planner_image[0]:
                # proposal_image_asset_id로 image_assets에서 조회
                proposal_img_id = planner_image[0]
                proposal_img_url = planner_image[1]
                
                if proposal_img_id:
                    planner_asset = db.execute(text('''
                        SELECT image_asset_id, image_url
                        FROM image_assets
                        WHERE image_asset_id = :img_id
                    '''), {'img_id': proposal_img_id}).first()
                    
                    if planner_asset:
                        img_id, url = planner_asset
                        abs_path = get_absolute_path(url)
                        print(f'    Image Asset ID: {str(img_id)[:8]}...')
                        print(f'    URL: {url}')
                        print(f'    절대 경로: {abs_path}')
                    else:
                        # proposal_image_url 직접 사용
                        abs_path = get_absolute_path(proposal_img_url)
                        print(f'    URL: {proposal_img_url}')
                        print(f'    절대 경로: {abs_path}')
                elif proposal_img_url:
                    abs_path = get_absolute_path(proposal_img_url)
                    print(f'    URL: {proposal_img_url}')
                    print(f'    절대 경로: {abs_path}')
                else:
                    print('    ⚠️  Planner 이미지 정보를 찾을 수 없습니다')
            else:
                # Fallback: job_id와 creation_order로 매칭 (생성 시간 순서)
                planner_images = db.execute(text('''
                    SELECT 
                        ia.image_asset_id,
                        ia.image_url,
                        ia.created_at
                    FROM image_assets ia
                    WHERE ia.job_id = :job_id
                    AND ia.image_type = 'planner'
                    ORDER BY ia.created_at
                '''), {'job_id': job_id}).fetchall()
                
                # variant의 creation_order에 맞는 planner 이미지 선택
                variant_order = order - 1  # 0-based index
                if variant_order < len(planner_images):
                    img_id, url, created = planner_images[variant_order]
                    abs_path = get_absolute_path(url)
                    print(f'    Image Asset ID: {str(img_id)[:8]}...')
                    print(f'    URL: {url}')
                    print(f'    절대 경로: {abs_path}')
                else:
                    print('    ⚠️  Planner 이미지를 찾을 수 없습니다')
            
            if planner_image:
                img_id, url = planner_image
                abs_path = get_absolute_path(url)
                print(f'    Image Asset ID: {str(img_id)[:8]}...')
                print(f'    URL: {url}')
                print(f'    절대 경로: {abs_path}')
            else:
                print('    ⚠️  Planner 이미지를 찾을 수 없습니다')
            print()
            
            # 최종 결과 이미지 (Overlaid) 경로
            print('  🎨 최종 결과 이미지 (Overlaid):')
            overlaid_image = db.execute(text('''
                SELECT 
                    jv.overlaid_img_asset_id,
                    ia.image_url
                FROM jobs_variants jv
                LEFT JOIN image_assets ia ON jv.overlaid_img_asset_id = ia.image_asset_id
                WHERE jv.job_variants_id = :variant_id
                AND jv.overlaid_img_asset_id IS NOT NULL
            '''), {'variant_id': variant_id}).first()
            
            if overlaid_image:
                img_id, url = overlaid_image
                abs_path = get_absolute_path(url)
                print(f'    Image Asset ID: {str(img_id)[:8] if img_id else "None"}...')
                print(f'    URL: {url}')
                print(f'    절대 경로: {abs_path}')
            else:
                # overlay_layouts에서 조회 시도
                overlay_layout = db.execute(text('''
                    SELECT ol.layout->'render'->>'url' as render_url
                    FROM overlay_layouts ol
                    WHERE ol.job_variants_id = :variant_id
                    ORDER BY ol.created_at DESC
                    LIMIT 1
                '''), {'variant_id': variant_id}).first()
                
                if overlay_layout and overlay_layout[0]:
                    url = overlay_layout[0]
                    abs_path = get_absolute_path(url)
                    print(f'    URL: {url}')
                    print(f'    절대 경로: {abs_path}')
                else:
                    print('    ⚠️  최종 결과 이미지를 찾을 수 없습니다')
            print()
        
        print('='*80)
        print('📝 Instagram Feed 정보')
        print('='*80)
        print()
        
        # Instagram Feed 정보
        instagram_feeds = db.execute(text('''
            SELECT 
                instagram_feed_id,
                refined_ad_copy_eng,
                ad_copy_kor,
                instagram_ad_copy,
                hashtags,
                created_at
            FROM instagram_feeds
            WHERE job_id = :job_id
            ORDER BY created_at DESC
            LIMIT 1
        '''), {'job_id': job_id}).first()
        
        if instagram_feeds:
            feed_id, refined_eng, ad_kor, insta_copy, hashtags, created = instagram_feeds
            print(f'Instagram Feed ID: {str(feed_id)[:8]}...')
            print(f'생성 시간: {created}')
            print()
            
            if refined_eng:
                print('조정된 영어 광고문구:')
                print(f'  {refined_eng}')
                print()
            
            if ad_kor:
                print('한글 광고문구:')
                print(f'  {ad_kor}')
                print()
            
            if insta_copy:
                print('인스타그램 피드 글:')
                print(f'  {insta_copy}')
                print()
            
            if hashtags:
                print('해시태그:')
                print(f'  {hashtags}')
                print()
        else:
            print('⚠️  Instagram Feed를 찾을 수 없습니다')
            print()
        
        # GPT 광고문구
        print('='*80)
        print('📝 GPT 광고문구')
        print('='*80)
        print()
        
        ad_copy = db.execute(text('''
            SELECT 
                ad_copy_kor,
                ad_copy_eng,
                generation_stage,
                created_at
            FROM txt_ad_copy_generations
            WHERE job_id = :job_id
            ORDER BY created_at DESC
            LIMIT 1
        '''), {'job_id': job_id}).first()
        
        if ad_copy:
            ad_kor, ad_eng, stage, created = ad_copy
            print(f'생성 시간: {created}')
            print(f'생성 단계: {stage}')
            print()
            if ad_kor:
                print('한국어 광고문구:')
                print(f'  {ad_kor}')
                print()
            if ad_eng:
                print('영어 광고문구:')
                print(f'  {ad_eng}')
                print()
        else:
            print('⚠️  광고문구를 찾을 수 없습니다')
            print()
        
        # 피드글
        print('='*80)
        print('📄 피드글')
        print('='*80)
        print()
        
        job_input = db.execute(text('''
            SELECT 
                desc_eng,
                desc_kor,
                created_at
            FROM job_inputs
            WHERE job_id = :job_id
        '''), {'job_id': job_id}).first()
        
        if job_input:
            desc_eng, desc_kor, created = job_input
            print(f'생성 시간: {created}')
            print()
            if desc_eng:
                print('영어 설명:')
                print(f'  {desc_eng}')
                print()
            if desc_kor:
                print('한국어 설명:')
                print(f'  {desc_kor}')
                print()
        else:
            print('⚠️  피드글을 찾을 수 없습니다')
            print()


def main():
    """메인 함수"""
    if len(sys.argv) < 2:
        print("Usage: python monitor_job_pipeline.py <job_id> [max_iterations] [check_interval]")
        print("  job_id: 모니터링할 Job ID (필수)")
        print("  max_iterations: 최대 반복 횟수 (선택, 기본값: 120)")
        print("  check_interval: 확인 간격 초 (선택, 기본값: 10)")
        sys.exit(1)
    
    job_id = sys.argv[1]
    max_iterations = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    check_interval = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    
    try:
        monitor_job(job_id, max_iterations, check_interval)
    except KeyboardInterrupt:
        print('\n\n모니터링이 중단되었습니다.')
        print('최종 상태를 출력합니다...')
        print()
        db = SessionLocal()
        try:
            print_final_status(db, job_id)
        finally:
            db.close()
    except Exception as e:
        print(f'\n❌ 오류 발생: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()


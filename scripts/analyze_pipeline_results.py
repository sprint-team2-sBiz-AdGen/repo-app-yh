#!/usr/bin/env python3
"""
파이프라인 결과 분석 스크립트
Job ID 또는 Tenant ID를 기반으로 파이프라인 실행 결과를 종합 분석
"""

import sys
import os
import argparse
import json
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal
from sqlalchemy import text


def analyze_job(job_id: str, db: SessionLocal):
    """Job ID를 기반으로 결과 분석"""
    print('='*70)
    print('파이프라인 결과 분석')
    print('='*70)
    print(f'Job ID: {job_id}\n')
    
    # Job 정보
    job = db.execute(text('''
        SELECT 
            j.job_id,
            j.tenant_id,
            j.status,
            j.current_step,
            j.created_at,
            j.updated_at
        FROM jobs j
        WHERE j.job_id = :job_id
    '''), {'job_id': job_id}).first()
    
    if not job:
        print('❌ Job을 찾을 수 없습니다')
        return
    
    job_id, tenant_id, status, step, created_at, updated_at = job
    print('📋 Job 정보:')
    print(f'  - Tenant ID: {tenant_id}')
    print(f'  - Status: {status}')
    print(f'  - Current Step: {step}')
    print(f'  - Created At: {created_at}')
    print(f'  - Updated At: {updated_at}')
    
    # Variants 정보
    variants = db.execute(text('''
        SELECT 
            jv.job_variants_id,
            jv.creation_order,
            jv.current_step,
            jv.status,
            jv.overlaid_img_asset_id,
            jv.updated_at
        FROM jobs_variants jv
        WHERE jv.job_id = :job_id
        ORDER BY jv.creation_order
    '''), {'job_id': job_id}).fetchall()
    
    if not variants:
        print('\n⚠️ Variants를 찾을 수 없습니다')
        return
    
    print(f'\n📊 Variants: {len(variants)}개')
    
    for variant in variants:
        variant_id, order, v_step, v_status, overlaid_id, v_updated = variant
        print(f'\n{"="*70}')
        print(f'Variant {order}')
        print(f'{"="*70}')
        print(f'  - Variant ID: {variant_id}')
        print(f'  - Current Step: {v_step}')
        print(f'  - Status: {v_status}')
        print(f'  - Updated At: {v_updated}')
        
        # Overlay Layout 정보
        overlay = db.execute(text('''
            SELECT 
                ol.overlay_id,
                ol.layout,
                ol.x_ratio,
                ol.y_ratio,
                ol.width_ratio,
                ol.height_ratio,
                ol.proposal_id
            FROM overlay_layouts ol
            WHERE ol.job_variants_id = :variant_id
            ORDER BY ol.created_at DESC
            LIMIT 1
        '''), {'variant_id': variant_id}).first()
        
        if overlay:
            overlay_id, layout_json, x, y, w, h, proposal_id = overlay
            layout = json.loads(layout_json) if isinstance(layout_json, str) else layout_json
            text_val = layout.get('text', '') if isinstance(layout, dict) else ''
            wrapped_text = layout.get('wrapped_text', None) if isinstance(layout, dict) else None
            text_len = len(text_val) if text_val else 0
            
            print(f'\n📋 Overlay 정보:')
            print(f'  - Overlay ID: {overlay_id}')
            print(f'  - 텍스트: {text_val[:80]}...' if text_len > 80 else f'  - 텍스트: {text_val}')
            print(f'  - 텍스트 길이: {text_len}자')
            print(f'  - 위치: x={float(x):.3f}, y={float(y):.3f}, w={float(w):.3f}, h={float(h):.3f}')
            print(f'  - Proposal ID: {proposal_id}')
            
            # wrapped_text 정보 출력
            if wrapped_text:
                lines = wrapped_text.split('\n')
                print(f'\n📝 줄바꿈된 텍스트 ({len(lines)}줄):')
                for i, line in enumerate(lines, 1):
                    print(f'  {i}: "{line}"')
                    if ',' in line:
                        comma_pos = line.find(',')
                        is_at_end = comma_pos == len(line) - 1
                        print(f'    → 쉼표 위치: {comma_pos} (줄 끝: {is_at_end})')
                        if is_at_end:
                            print(f'    ✅ 쉼표가 줄 끝에 있음 - 다음 줄로 넘어갔을 가능성')
                    if '.' in line:
                        period_pos = line.find('.')
                        is_at_end = period_pos == len(line) - 1
                        print(f'    → 마침표 위치: {period_pos} (줄 끝: {is_at_end})')
                        if is_at_end:
                            print(f'    ✅ 마침표가 줄 끝에 있음 - 다음 줄로 넘어갔을 가능성')
            else:
                print(f'\n⚠️ wrapped_text 필드가 없습니다! (줄바꿈 정보 확인 불가)')
            
            # Planner Proposal 정보
            proposal = db.execute(text('''
                SELECT 
                    pp.proposal_id,
                    pp.layout->'proposals' as proposals,
                    pp.layout->'forbidden_position' as forbidden_pos,
                    pp.layout->'avoid' as avoid
                FROM planner_proposals pp
                INNER JOIN image_assets ia ON pp.image_asset_id = ia.image_asset_id
                INNER JOIN job_inputs ji ON ia.image_asset_id = ji.img_asset_id
                WHERE ji.job_id = :job_id
                ORDER BY pp.created_at DESC
                LIMIT 1
            '''), {'job_id': job_id}).first()
            
            if proposal:
                prop_id, proposals_json, forbidden_pos, avoid = proposal
                
                if proposals_json:
                    proposals = json.loads(proposals_json) if isinstance(proposals_json, str) else proposals_json
                    if isinstance(proposals, list):
                        # 선택된 proposal 찾기
                        selected_prop = None
                        min_diff = float('inf')
                        
                        for prop in proposals:
                            prop_xywh = prop.get('xywh', [])
                            if len(prop_xywh) == 4:
                                px, py, pw, ph = prop_xywh
                                diff = abs(float(px) - float(x)) + abs(float(py) - float(y)) + abs(float(pw) - float(w)) + abs(float(ph) - float(h))
                                if diff < min_diff:
                                    min_diff = diff
                                    selected_prop = prop
                        
                        if selected_prop:
                            source = selected_prop.get('source', 'unknown')
                            score = selected_prop.get('score', 0)
                            
                            print(f'\n✅ 선택된 Proposal:')
                            print(f'  - Source: {source}')
                            print(f'  - Score: {score:.2f}')
                            print(f'  - 위치: {selected_prop.get("xywh")}')
                            print(f'  - 차이: {min_diff:.4f}')
                            
                            # Forbidden 위치 정보
                            if forbidden_pos:
                                forbidden_dict = json.loads(forbidden_pos) if isinstance(forbidden_pos, str) else forbidden_pos
                                if isinstance(forbidden_dict, dict):
                                    print(f'\n📊 Forbidden 영역 위치:')
                                    print(f'  - 중심: ({forbidden_dict.get("center_x", 0):.2f}, {forbidden_dict.get("center_y", 0):.2f})')
                                    print(f'  - 중앙(x축): {forbidden_dict.get("is_center_x", False)}')
                                    print(f'  - 위쪽: {forbidden_dict.get("is_top_y", False)}')
                                    print(f'  - 아래쪽: {forbidden_dict.get("is_bottom_y", False)}')
                                    
                                    is_center_x = forbidden_dict.get('is_center_x', False)
                                    is_top_y = forbidden_dict.get('is_top_y', False)
                                    is_bottom_y = forbidden_dict.get('is_bottom_y', False)
                                    
                                    print(f'\n💡 Forbidden 위치 기반 가중치:')
                                    if is_top_y:
                                        print(f'  - ✅ bottom 그룹에 +0.3 보너스 (Forbidden이 위쪽에 있음)')
                                    if is_bottom_y:
                                        print(f'  - ✅ top 그룹에 +0.3 보너스 (Forbidden이 아래쪽에 있음)')
                                    if is_center_x:
                                        print(f'  - ⚠️ left, right 그룹에 -0.3 페널티 (Forbidden이 중앙에 있음)')
                            
                            # 텍스트 길이 보너스 계산
                            text_length_bonus = 0.0
                            if text_len >= 20:
                                text_length_bonus = min(1.0, (text_len - 20) / 80.0)
                            
                            print(f'\n📊 텍스트 길이 분석:')
                            print(f'  - 텍스트 길이: {text_len}자')
                            print(f'  - 보너스 점수: {text_length_bonus:.2f} (최대 1.0)')
                            if text_len >= 100:
                                print(f'  - ✅ 매우 긴 텍스트 → max_size 강제 선택 또는 높은 확률')
                            
                            # max_size인지 확인
                            if 'max_size' in source.lower():
                                print(f'\n🎉 SUCCESS: max_size proposal이 선택되었습니다!')
                                print(f'   ✅ 긴 텍스트({text_len}자)에 대해 max_size proposal이 선택됨')
                                if text_len >= 100:
                                    print(f'   ✅ 매우 긴 텍스트로 인해 강제 선택 또는 높은 확률로 선택됨')
                            else:
                                print(f'\n⚠️ max_size proposal이 선택되지 않았습니다.')
                                print(f'   선택된: {source}')
                            
                            # 모든 proposals 표시 (원래 점수와 조정 후 점수)
                            print(f'\n📊 모든 Proposals 상세 점수:')
                            sorted_props = sorted(proposals, key=lambda x: x.get('score', 0), reverse=True)
                            
                            for i, prop in enumerate(sorted_props[:10], 1):
                                prop_source = prop.get('source', 'unknown')
                                original_score = prop.get('score', 0)
                                prop_score = original_score
                                
                                # max_size면 보너스 추가
                                bonus_text = ''
                                if 'max_size' in prop_source.lower() and text_length_bonus > 0:
                                    prop_score += text_length_bonus
                                    bonus_text += f' +{text_length_bonus:.2f}(텍스트길이)'
                                
                                # Forbidden 위치 기반 보너스/페널티
                                if forbidden_pos:
                                    forbidden_dict = json.loads(forbidden_pos) if isinstance(forbidden_pos, str) else forbidden_pos
                                    if isinstance(forbidden_dict, dict):
                                        is_center_x = forbidden_dict.get('is_center_x', False)
                                        is_top_y = forbidden_dict.get('is_top_y', False)
                                        is_bottom_y = forbidden_dict.get('is_bottom_y', False)
                                        
                                        if 'bottom' in prop_source.lower() and is_top_y:
                                            prop_score += 0.3
                                            bonus_text += f' +0.30(Forbidden위치)'
                                        if 'top' in prop_source.lower() and is_bottom_y:
                                            prop_score += 0.3
                                            bonus_text += f' +0.30(Forbidden위치)'
                                        if ('left' in prop_source.lower() or 'right' in prop_source.lower()) and is_center_x:
                                            prop_score -= 0.3
                                            bonus_text += f' -0.30(Forbidden위치)'
                                
                                marker = '👉' if prop == selected_prop else '  '
                                print(f'{marker} {i}. {prop_source}')
                                print(f'     원래 점수: {original_score:.2f}{bonus_text}')
                                print(f'     조정 후 점수: {prop_score:.2f}')
                                print(f'     위치: {prop.get("xywh", [])}')
                                if prop == selected_prop:
                                    print(f'     ✅ 선택됨 (차이: {min_diff:.4f})')
                                print()
            
            # 평가 결과
            print(f'\n📊 평가 결과:')
            
            # OCR 평가
            ocr_eval = db.execute(text('''
                SELECT e.metrics
                FROM evaluations e
                INNER JOIN overlay_layouts ol ON e.overlay_id = ol.overlay_id
                WHERE ol.job_variants_id = :variant_id
                  AND e.evaluation_type = 'ocr'
                ORDER BY e.created_at DESC
                LIMIT 1
            '''), {'variant_id': variant_id}).first()
            
            if ocr_eval and ocr_eval[0]:
                ocr_metrics = ocr_eval[0]
                if isinstance(ocr_metrics, dict):
                    print(f'\n  1. OCR 평가:')
                    print(f'     - OCR 정확도: {ocr_metrics.get("ocr_accuracy", "N/A")}')
                    print(f'     - 유사도: {ocr_metrics.get("similarity", "N/A")}')
                    print(f'     - OCR 신뢰도: {ocr_metrics.get("ocr_confidence", "N/A")}')
                    print(f'     - 단어 일치율: {ocr_metrics.get("word_match_rate", "N/A")}')
                    print(f'     - 원본 텍스트: {ocr_metrics.get("original_text", "N/A")[:50]}...')
                    print(f'     - 인식된 텍스트: {ocr_metrics.get("recognized_text", "N/A")[:50]}...')
            
            # Readability 평가
            readability_eval = db.execute(text('''
                SELECT e.metrics
                FROM evaluations e
                INNER JOIN overlay_layouts ol ON e.overlay_id = ol.overlay_id
                WHERE ol.job_variants_id = :variant_id
                  AND e.evaluation_type = 'readability'
                ORDER BY e.created_at DESC
                LIMIT 1
            '''), {'variant_id': variant_id}).first()
            
            if readability_eval and readability_eval[0]:
                read_metrics = readability_eval[0]
                if isinstance(read_metrics, dict):
                    print(f'\n  2. Readability 평가:')
                    print(f'     - 가독성 점수: {read_metrics.get("readability_score", "N/A")}')
                    print(f'     - 대비 비율: {read_metrics.get("contrast_ratio", "N/A")}:1')
                    print(f'     - WCAG AA 준수: {read_metrics.get("wcag_aa_compliant", "N/A")}')
                    print(f'     - WCAG AAA 준수: {read_metrics.get("wcag_aaa_compliant", "N/A")}')
                    print(f'     - WCAG 레벨: {read_metrics.get("wcag_level", "N/A")}')
            
            # IoU 평가
            iou_eval = db.execute(text('''
                SELECT e.metrics
                FROM evaluations e
                INNER JOIN overlay_layouts ol ON e.overlay_id = ol.overlay_id
                WHERE ol.job_variants_id = :variant_id
                  AND e.evaluation_type = 'iou'
                ORDER BY e.created_at DESC
                LIMIT 1
            '''), {'variant_id': variant_id}).first()
            
            if iou_eval and iou_eval[0]:
                iou_metrics = iou_eval[0]
                if isinstance(iou_metrics, dict):
                    print(f'\n  3. IoU 평가:')
                    print(f'     - IoU 점수: {iou_metrics.get("iou", "N/A")}')
                    print(f'     - 음식 영역과 IoU: {iou_metrics.get("iou_with_food", "N/A")}')
                    print(f'     - 겹침 감지: {iou_metrics.get("overlap_detected", "N/A")}')
                    print(f'     - 제안 위치: {iou_metrics.get("proposal_xywh", "N/A")}')
                    print(f'     - 실제 위치: {iou_metrics.get("actual_xywh", "N/A")}')
            
            # VLM Judge 평가
            vlm_judge = db.execute(text('''
                SELECT vt.response
                FROM vlm_traces vt
                WHERE vt.job_id = :job_id
                  AND vt.operation_type = 'judge'
                ORDER BY vt.created_at DESC
                LIMIT 1
            '''), {'job_id': job_id}).first()
            
            if vlm_judge and vlm_judge[0]:
                vlm_response = vlm_judge[0]
                if isinstance(vlm_response, dict):
                    print(f'\n  4. VLM Judge 평가:')
                    print(f'     - Brief 준수: {vlm_response.get("on_brief", "N/A")}')
                    print(f'     - 가림 여부: {vlm_response.get("occlusion", "N/A")}')
                    print(f'     - 대비 적절성: {vlm_response.get("contrast_ok", "N/A")}')
                    print(f'     - CTA 존재: {vlm_response.get("cta_present", "N/A")}')
                    print(f'     - 이슈: {vlm_response.get("issues", "N/A")}')
                    analysis = vlm_response.get('analysis')
                    if analysis:
                        if isinstance(analysis, str):
                            try:
                                analysis_dict = json.loads(analysis)
                                print(f'     - Analysis: {json.dumps(analysis_dict, indent=6, ensure_ascii=False)[:200]}...')
                            except:
                                print(f'     - Analysis: {analysis[:200]}...')
                        else:
                            print(f'     - Analysis: {analysis}')
            
            # 최종 이미지 경로
            if overlaid_id:
                overlaid_asset = db.execute(text('''
                    SELECT image_asset_id, image_url, width, height
                    FROM image_assets
                    WHERE image_asset_id = :asset_id
                '''), {'asset_id': overlaid_id}).first()
                
                if overlaid_asset:
                    asset_id, img_url, width, height = overlaid_asset
                    print(f'\n📁 최종 오버레이 이미지:')
                    print(f'  - Image Asset ID: {asset_id}')
                    print(f'  - URL: {img_url}')
                    print(f'  - 크기: {width}x{height}')
                    
                    # 파일 경로 확인
                    import os
                    from config import ASSETS_DIR
                    file_path = os.path.join(ASSETS_DIR, img_url[8:]) if img_url.startswith('/assets/') else None
                    if file_path and os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                        print(f'  - 파일 경로: {file_path}')
                        print(f'  - 파일 크기: {file_size:,} bytes ({file_size/1024:.2f} KB)')
                        print(f'  - ✅ 파일 존재 확인됨')


def analyze_tenant(tenant_id: str, db: SessionLocal, limit: int = 5):
    """Tenant ID를 기반으로 최근 Job들 분석"""
    print('='*70)
    print(f'Tenant 최근 Job 분석: {tenant_id}')
    print('='*70)
    
    jobs = db.execute(text('''
        SELECT job_id, status, current_step, created_at
        FROM jobs
        WHERE tenant_id = :tenant_id
        ORDER BY created_at DESC
        LIMIT :limit
    '''), {'tenant_id': tenant_id, 'limit': limit}).fetchall()
    
    if not jobs:
        print(f'\n⚠️ {tenant_id}에 대한 Job을 찾을 수 없습니다')
        return
    
    print(f'\n📋 최근 Job {len(jobs)}개:\n')
    for i, job in enumerate(jobs, 1):
        job_id, status, step, created_at = job
        print(f'{i}. Job ID: {job_id}')
        print(f'   Status: {status}, Step: {step}, Created: {created_at}')
    
    print(f'\n{"="*70}')
    print('가장 최근 Job 상세 분석:')
    print('='*70)
    
    if jobs:
        latest_job_id = jobs[0][0]
        analyze_job(latest_job_id, db)


def main():
    parser = argparse.ArgumentParser(description='파이프라인 결과 분석 스크립트')
    parser.add_argument('--job-id', type=str, help='Job ID')
    parser.add_argument('--tenant-id', type=str, help='Tenant ID (최근 Job 분석)')
    parser.add_argument('--limit', type=int, default=5, help='Tenant 분석 시 최대 Job 개수 (기본: 5)')
    
    args = parser.parse_args()
    
    if not args.job_id and not args.tenant_id:
        parser.print_help()
        sys.exit(1)
    
    db = SessionLocal()
    try:
        if args.job_id:
            analyze_job(args.job_id, db)
        elif args.tenant_id:
            analyze_tenant(args.tenant_id, db, args.limit)
    except Exception as e:
        print(f'\n❌ 오류 발생: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()


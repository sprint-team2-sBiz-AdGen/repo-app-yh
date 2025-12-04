"""Pipeline Trigger Service
Job 상태 변화에 따라 다음 파이프라인 단계를 자동으로 트리거하는 서비스
"""
########################################################
# created_at: 2025-11-28
# updated_at: 2025-12-03
# author: LEEYH205
# description: Job 상태 변화에 따라 다음 파이프라인 단계를 자동으로 트리거
# version: 2.2.1
# status: development
# tags: pipeline, trigger, automation
# dependencies: httpx, asyncpg
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import logging
import httpx
import uuid
from typing import Optional
from config import HOST, PORT

logger = logging.getLogger(__name__)

# 파이프라인 단계 매핑
PIPELINE_STAGES = {
    ('img_gen', 'done'): {
        'next_step': 'vlm_analyze',
        'api_endpoint': '/api/yh/llava/stage1/validate',
        'method': 'POST',
        'needs_overlay_id': False
    },
    ('vlm_analyze', 'done'): {
        'next_step': 'yolo_detect',
        'api_endpoint': '/api/yh/yolo/detect',
        'method': 'POST',
        'needs_overlay_id': False
    },
    ('yolo_detect', 'done'): {
        'next_step': 'planner',
        'api_endpoint': '/api/yh/planner',
        'method': 'POST',
        'needs_overlay_id': False
    },
    ('planner', 'done'): {
        'next_step': 'overlay',
        'api_endpoint': '/api/yh/overlay',
        'method': 'POST',
        'needs_overlay_id': False,
        'needs_text_and_proposal': True  # overlay는 text와 proposal_id가 필요
    },
    ('overlay', 'done'): {
        'next_step': 'vlm_judge',
        'api_endpoint': '/api/yh/llava/stage2/judge',
        'method': 'POST',
        'needs_overlay_id': True  # LLaVA Stage 2는 overlay_id가 필요 (Optional이지만 있으면 좋음)
    },
    ('vlm_judge', 'done'): {
        'next_step': 'ocr_eval',
        'api_endpoint': '/api/yh/ocr/evaluate',
        'method': 'POST',
        'needs_overlay_id': True  # OCR은 overlay_id가 필요
    },
    ('ocr_eval', 'done'): {
        'next_step': 'readability_eval',
        'api_endpoint': '/api/yh/readability/evaluate',
        'method': 'POST',
        'needs_overlay_id': True  # Readability는 overlay_id가 필요
    },
    ('readability_eval', 'done'): {
        'next_step': 'iou_eval',
        'api_endpoint': '/api/yh/iou/evaluate',
        'method': 'POST',
        'needs_overlay_id': True  # IoU는 overlay_id가 필요
    },
    # 텍스트 생성 단계 (Job 레벨)
    ('iou_eval', 'done'): {
        'next_step': 'ad_copy_gen_kor',
        'api_endpoint': '/api/yh/gpt/eng-to-kor',
        'method': 'POST',
        'is_job_level': True,  # Job 레벨 단계 (variant별 실행 아님)
        'needs_overlay_id': False
    },
    ('ad_copy_gen_kor', 'done'): {
        'next_step': 'instagram_feed_gen',
        'api_endpoint': '/api/yh/instagram/feed',
        'method': 'POST',
        'is_job_level': True,  # Job 레벨 단계 (variant별 실행 아님)
        'needs_overlay_id': False
    },
}

async def trigger_next_pipeline_stage(
    job_id: str,
    current_step: Optional[str],
    status: str,
    tenant_id: str
):
    """다음 파이프라인 단계 트리거"""
    
    # 트리거 조건 확인
    if not current_step or status != 'done':
        logger.debug(
            f"트리거 조건 불만족: job_id={job_id}, "
            f"current_step={current_step}, status={status}"
        )
        return
    
    # 다음 단계 정보 조회
    stage_info = PIPELINE_STAGES.get((current_step, status))
    if not stage_info:
        logger.debug(
            f"다음 단계 없음: job_id={job_id}, "
            f"current_step={current_step}, status={status}"
        )
        return
    
    # Job 레벨 단계가 아닌 경우 (variant별 실행) 스킵
    # (variant별 단계는 _process_job_variant_state_change에서 처리)
    if not stage_info.get('is_job_level', False):
        logger.debug(
            f"Variant별 실행 단계이므로 Job 레벨 트리거 스킵: job_id={job_id}, "
            f"next_step={stage_info['next_step']}"
        )
        return
    
    # 중복 실행 방지: job 상태 재확인
    # (다른 워커가 이미 처리했을 수 있음)
    if not await _verify_job_state(job_id, current_step, status, tenant_id):
        logger.info(
            f"Job 상태가 변경되어 스킵: job_id={job_id}, "
            f"expected: current_step={current_step}, status={status}"
        )
        return
    
    # API 호출
    api_url = f"http://{HOST}:{PORT}{stage_info['api_endpoint']}"
    request_data = {
        'job_id': job_id,
        'tenant_id': tenant_id
    }
    
    # overlay_id가 필요한 경우 조회
    if stage_info.get('needs_overlay_id', False):
        overlay_id = await _get_overlay_id_from_job(job_id, tenant_id)
        if not overlay_id:
            logger.warning(
                f"overlay_id를 찾을 수 없어 {stage_info['next_step']} 트리거를 건너뜁니다: job_id={job_id}"
            )
            return
        request_data['overlay_id'] = overlay_id
        logger.info(f"overlay_id 조회 성공: job_id={job_id}, overlay_id={overlay_id}")
    
    # text와 proposal_id가 필요한 경우 조회 (overlay 단계)
    if stage_info.get('needs_text_and_proposal', False):
        text_and_proposal = await _get_text_and_proposal_from_job(job_id, tenant_id)
        if not text_and_proposal or not text_and_proposal.get('text'):
            logger.warning(
                f"text를 찾을 수 없어 {stage_info['next_step']} 트리거를 건너뜁니다: job_id={job_id}"
            )
            return
        request_data['text'] = text_and_proposal['text']
        request_data['x_align'] = 'center'
        request_data['y_align'] = 'top'
        if text_and_proposal.get('proposal_id'):
            request_data['proposal_id'] = text_and_proposal['proposal_id']
            logger.info(f"proposal_id 조회 성공: job_id={job_id}, proposal_id={text_and_proposal['proposal_id']}")
        logger.info(f"text 조회 성공: job_id={job_id}, text_length={len(text_and_proposal['text'])}")
    
    print(f"[TRIGGER] 파이프라인 단계 트리거: job_id={job_id}, next_step={stage_info['next_step']}")
    logger.info(
        f"파이프라인 단계 트리거: job_id={job_id}, "
        f"next_step={stage_info['next_step']}, api={api_url}"
    )
    
    try:
        async with httpx.AsyncClient(timeout=1800.0) as client:  # 30분 타임아웃
            response = await client.post(api_url, json=request_data)
            response.raise_for_status()
            logger.info(
                f"파이프라인 단계 실행 성공: job_id={job_id}, "
                f"next_step={stage_info['next_step']}"
            )
    except httpx.HTTPError as e:
        logger.error(
            f"파이프라인 단계 실행 실패: job_id={job_id}, "
            f"next_step={stage_info['next_step']}, error={e}"
        )
        # 에러는 상위로 전파하지 않음 (로깅만)
    except Exception as e:
        logger.error(
            f"파이프라인 단계 실행 중 예상치 못한 오류: job_id={job_id}, "
            f"next_step={stage_info['next_step']}, error={e}",
            exc_info=True
        )


async def retry_pipeline_stage(
    job_id: str,
    current_step: str,
    tenant_id: str,
):
    """현재 단계 재실행 (Job이 failed인 경우 재시도 용도)
    
    PIPELINE_STAGES에서 next_step이 current_step인 항목을 찾아
    해당 단계의 API를 다시 호출한다.
    
    Variant 레벨 단계인 경우, 모든 failed variants를 재시도합니다.
    """
    if not current_step:
        logger.debug(f"[RETRY] current_step 누락으로 재시도 스킵: job_id={job_id}")
        return
    
    # current_step을 next_step으로 사용하는 stage_info 찾기
    stage_info = None
    for (_step, _status), info in PIPELINE_STAGES.items():
        if info.get("next_step") == current_step:
            stage_info = info
            break
    
    if not stage_info:
        logger.debug(
            f"[RETRY] 재시도 가능한 단계 정보 없음: job_id={job_id}, current_step={current_step}"
        )
        return
    
    # Job 레벨 단계인 경우 기존 로직 사용
    if stage_info.get('is_job_level', False):
        api_url = f"http://{HOST}:{PORT}{stage_info['api_endpoint']}"
        request_data = {
            "job_id": job_id,
            "tenant_id": tenant_id,
        }
        
        logger.info(
            f"[RETRY] 파이프라인 단계 재시도 (Job 레벨): job_id={job_id}, "
            f"current_step={current_step}, api={api_url}"
        )
        
        try:
            async with httpx.AsyncClient(timeout=1800.0) as client:  # 30분 타임아웃
                response = await client.post(api_url, json=request_data)
                response.raise_for_status()
                logger.info(
                    f"[RETRY] 파이프라인 단계 재실행 성공 (Job 레벨): job_id={job_id}, "
                    f"current_step={current_step}"
                )
        except httpx.HTTPError as e:
            logger.error(
                f"[RETRY] 파이프라인 단계 재실행 실패 (Job 레벨): job_id={job_id}, "
                f"current_step={current_step}, error={e}"
            )
        except Exception as e:
            logger.error(
                f"[RETRY] 파이프라인 단계 재실행 중 예상치 못한 오류 (Job 레벨): job_id={job_id}, "
                f"current_step={current_step}, error={e}",
                exc_info=True,
            )
        return
    
    # Variant 레벨 단계인 경우: 모든 failed variants 재시도
    import asyncpg
    from config import DATABASE_URL
    
    asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
    
    try:
        conn = await asyncpg.connect(asyncpg_url)
        try:
            # 해당 단계에서 failed인 모든 variants 조회
            failed_variants = await conn.fetch(
                """
                SELECT job_variants_id, img_asset_id
                FROM jobs_variants
                WHERE job_id = $1
                  AND current_step = $2
                  AND status = 'failed'
                ORDER BY creation_order
                """,
                uuid.UUID(job_id),
                current_step
            )
            
            if not failed_variants:
                logger.debug(
                    f"[RETRY] 재시도할 failed variants 없음: job_id={job_id}, current_step={current_step}"
                )
                return
            
            logger.info(
                f"[RETRY] 파이프라인 단계 재시도 (Variant 레벨): job_id={job_id}, "
                f"current_step={current_step}, failed_variants={len(failed_variants)}개"
            )
            
            # 각 variant 재시도
            api_url = f"http://{HOST}:{PORT}{stage_info['api_endpoint']}"
            
            for variant in failed_variants:
                variant_id = str(variant['job_variants_id'])
                img_asset_id = str(variant['img_asset_id']) if variant['img_asset_id'] else ''
                
                # variant를 queued 상태로 변경하여 현재 단계 재실행
                await conn.execute(
                    """
                    UPDATE jobs_variants
                    SET status = 'queued',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_variants_id = $1
                      AND current_step = $2
                      AND status = 'failed'
                    """,
                    uuid.UUID(variant_id),
                    current_step
                )
                
                # API 호출 준비
                request_data = {
                    'job_variants_id': variant_id,
                    'job_id': job_id,
                    'tenant_id': tenant_id
                }
                
                # overlay_id가 필요한 경우 조회
                if stage_info.get('needs_overlay_id', False):
                    overlay_id = await _get_overlay_id_from_job_variant(variant_id, job_id, tenant_id)
                    if overlay_id:
                        request_data['overlay_id'] = overlay_id
                        logger.info(f"[RETRY] overlay_id 조회 성공: variant_id={variant_id}, overlay_id={overlay_id}")
                    else:
                        logger.warning(f"[RETRY] overlay_id를 찾을 수 없어 재시도 스킵: variant_id={variant_id}")
                        continue
                
                # text와 proposal_id가 필요한 경우 조회
                if stage_info.get('needs_text_and_proposal', False):
                    text_and_proposal = await _get_text_and_proposal_from_job_variant(variant_id, job_id, tenant_id)
                    if text_and_proposal:
                        request_data['text'] = text_and_proposal['text']
                        if text_and_proposal.get('proposal_id'):
                            request_data['proposal_id'] = text_and_proposal['proposal_id']
                    else:
                        logger.warning(f"[RETRY] text를 찾을 수 없어 재시도 스킵: variant_id={variant_id}")
                        continue
                
                # API 호출
                try:
                    async with httpx.AsyncClient(timeout=1800.0) as client:  # 30분 타임아웃
                        response = await client.post(api_url, json=request_data)
                        response.raise_for_status()
                        logger.info(
                            f"[RETRY] Variant 재시도 성공: job_variants_id={variant_id}, "
                            f"current_step={current_step}"
                        )
                except httpx.HTTPError as e:
                    logger.error(
                        f"[RETRY] Variant 재시도 실패: job_variants_id={variant_id}, "
                        f"current_step={current_step}, error={e}"
                    )
                    # 실패 시 다시 failed로 변경
                    await conn.execute(
                        """
                        UPDATE jobs_variants
                        SET status = 'failed',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE job_variants_id = $1
                        """,
                        uuid.UUID(variant_id)
                    )
                except Exception as e:
                    logger.error(
                        f"[RETRY] Variant 재시도 중 예상치 못한 오류: job_variants_id={variant_id}, "
                        f"current_step={current_step}, error={e}",
                        exc_info=True
                    )
                    # 실패 시 다시 failed로 변경
                    await conn.execute(
                        """
                        UPDATE jobs_variants
                        SET status = 'failed',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE job_variants_id = $1
                        """,
                        uuid.UUID(variant_id)
                    )
        finally:
            await conn.close()
    except Exception as e:
        logger.error(
            f"[RETRY] 파이프라인 단계 재시도 중 오류 (Variant 레벨): job_id={job_id}, "
            f"current_step={current_step}, error={e}",
            exc_info=True
        )

async def _verify_job_state(
    job_id: str,
    expected_step: str,
    expected_status: str,
    tenant_id: str
) -> bool:
    """Job 상태 재확인 (중복 실행 방지)"""
    import asyncpg
    from config import DATABASE_URL
    
    asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
    
    try:
        conn = await asyncpg.connect(asyncpg_url)
        try:
            row = await conn.fetchrow(
                """
                SELECT current_step, status, tenant_id
                FROM jobs
                WHERE job_id = $1
                """,
                job_id
            )
            
            if not row:
                logger.warning(f"Job을 찾을 수 없음: job_id={job_id}")
                return False
            
            # 상태 확인
            if (row['current_step'] == expected_step 
                and row['status'] == expected_status
                and row['tenant_id'] == tenant_id):
                return True
            
            logger.debug(
                f"Job 상태 불일치: job_id={job_id}, "
                f"expected: step={expected_step}, status={expected_status}, "
                f"actual: step={row['current_step']}, status={row['status']}"
            )
            return False
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Job 상태 확인 오류: {e}", exc_info=True)
        return False

async def _get_overlay_id_from_job(job_id: str, tenant_id: str) -> Optional[str]:
    """
    job_id로부터 최신 overlay_id 조회
    
    job → job_inputs → planner_proposals → overlay_layouts 경로로 조회
    
    Args:
        job_id: Job ID
        tenant_id: Tenant ID
    
    Returns:
        overlay_id (str) 또는 None
    """
    import asyncpg
    from config import DATABASE_URL
    
    asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
    
    try:
        conn = await asyncpg.connect(asyncpg_url)
        try:
            # job → job_inputs → planner_proposals → overlay_layouts 조회
            row = await conn.fetchrow(
                """
                SELECT ol.overlay_id
                FROM jobs j
                INNER JOIN job_inputs ji ON j.job_id = ji.job_id
                INNER JOIN planner_proposals pp ON ji.img_asset_id = pp.image_asset_id
                INNER JOIN overlay_layouts ol ON pp.proposal_id = ol.proposal_id
                WHERE j.job_id = $1
                  AND j.tenant_id = $2
                ORDER BY ol.created_at DESC
                LIMIT 1
                """,
                job_id,
                tenant_id
            )
            
            if row and row['overlay_id']:
                return str(row['overlay_id'])
            
            logger.warning(f"overlay_id를 찾을 수 없음: job_id={job_id}, tenant_id={tenant_id}")
            return None
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"overlay_id 조회 오류: {e}", exc_info=True)
        return None

async def trigger_next_pipeline_stage_for_variant(
    job_variants_id: str,
    job_id: str,
    current_step: Optional[str],
    status: str,
    tenant_id: str,
    img_asset_id: str
):
    """다음 파이프라인 단계 트리거 (job_variants_id 기반)"""
    
    # 트리거 조건 확인: done 또는 queued 상태 허용
    # queued 상태는 현재 단계를 실행해야 하는 상태 (예: vlm_analyze, queued → vlm_analyze API 호출)
    if not current_step or status not in ['done', 'queued']:
        logger.debug(
            f"트리거 조건 불만족: job_variants_id={job_variants_id}, "
            f"current_step={current_step}, status={status} (done 또는 queued 필요)"
        )
        return
    
    # 다음 단계 정보 조회
    # queued 상태일 때는 현재 단계를 실행해야 하므로, (current_step, 'done') 매핑을 사용
    # (queued → running → done 흐름에서 done 상태의 매핑을 재사용)
    if status == 'queued':
        # queued 상태는 현재 단계를 실행하는 상태이므로, done 상태의 매핑을 사용
        stage_info = PIPELINE_STAGES.get((current_step, 'done'))
        if not stage_info:
            logger.debug(
                f"다음 단계 없음 (queued 상태): job_variants_id={job_variants_id}, "
                f"current_step={current_step}"
            )
            return
        logger.info(
            f"queued 상태에서 현재 단계 실행: job_variants_id={job_variants_id}, "
            f"current_step={current_step}, next_step={stage_info['next_step']}"
        )
    else:
        # done 상태일 때는 일반적인 다음 단계 매핑 사용
        stage_info = PIPELINE_STAGES.get((current_step, status))
        if not stage_info:
            logger.debug(
                f"다음 단계 없음: job_variants_id={job_variants_id}, "
                f"current_step={current_step}, status={status}"
            )
            return
    
    # Job 레벨 단계인 경우 variant 레벨 트리거에서 스킵
    # (Job 레벨 단계는 모든 variants 완료 후 Job 레벨 트리거에서 처리)
    if stage_info.get('is_job_level', False):
        logger.debug(
            f"Job 레벨 단계이므로 Variant 레벨 트리거 스킵: job_variants_id={job_variants_id}, "
            f"next_step={stage_info['next_step']}. 모든 variants 완료 후 Job 레벨 트리거에서 처리됩니다."
        )
        # 모든 variants 완료 확인 및 Job 레벨 트리거 실행
        await _check_and_trigger_job_level_stage(job_id, current_step, status, tenant_id, stage_info)
        return
    
    # 중복 실행 방지: job_variant 상태 재확인
    # queued 상태일 때는 queued 상태로 확인 (현재 단계 실행 중)
    verify_status = status if status == 'queued' else status
    if not await _verify_job_variant_state(job_variants_id, current_step, verify_status, tenant_id):
        logger.info(
            f"Job Variant 상태가 변경되어 스킵: job_variants_id={job_variants_id}, "
            f"expected: current_step={current_step}, status={verify_status}"
        )
        return
    
    # API 호출
    api_url = f"http://{HOST}:{PORT}{stage_info['api_endpoint']}"
    request_data = {
        'job_variants_id': job_variants_id,  # 필수 파라미터
        'job_id': job_id,  # 호환성을 위해 유지
        'tenant_id': tenant_id
    }
    
    # overlay_id가 필요한 경우 조회 (job_variants 기준)
    if stage_info.get('needs_overlay_id', False):
        overlay_id = await _get_overlay_id_from_job_variant(job_variants_id, job_id, tenant_id)
        if not overlay_id:
            logger.warning(
                f"overlay_id를 찾을 수 없어 {stage_info['next_step']} 트리거를 건너뜁니다: job_variants_id={job_variants_id}"
            )
            return
        request_data['overlay_id'] = overlay_id
        logger.info(f"overlay_id 조회 성공: job_variants_id={job_variants_id}, overlay_id={overlay_id}")
    
    # text와 proposal_id가 필요한 경우 조회 (overlay 단계)
    if stage_info.get('needs_text_and_proposal', False):
        text_and_proposal = await _get_text_and_proposal_from_job_variant(job_variants_id, job_id, tenant_id)
        if not text_and_proposal or not text_and_proposal.get('text'):
            logger.warning(
                f"text를 찾을 수 없어 {stage_info['next_step']} 트리거를 건너뜁니다: job_variants_id={job_variants_id}"
            )
            return
        request_data['text'] = text_and_proposal['text']
        request_data['x_align'] = 'center'
        request_data['y_align'] = 'top'
        if text_and_proposal.get('proposal_id'):
            request_data['proposal_id'] = text_and_proposal['proposal_id']
            logger.info(f"proposal_id 조회 성공: job_variants_id={job_variants_id}, proposal_id={text_and_proposal['proposal_id']}")
        logger.info(f"text 조회 성공: job_variants_id={job_variants_id}, text_length={len(text_and_proposal['text'])}")
    
    print(f"[TRIGGER] 파이프라인 단계 트리거 (variant): job_variants_id={job_variants_id}, job_id={job_id}, next_step={stage_info['next_step']}")
    logger.info(
        f"파이프라인 단계 트리거 (variant): job_variants_id={job_variants_id}, job_id={job_id}, "
        f"next_step={stage_info['next_step']}, api={api_url}"
    )
    
    try:
        async with httpx.AsyncClient(timeout=1800.0) as client:  # 30분 타임아웃
            response = await client.post(api_url, json=request_data)
            response.raise_for_status()
            logger.info(
                f"파이프라인 단계 실행 성공 (variant): job_variants_id={job_variants_id}, "
                f"next_step={stage_info['next_step']}"
            )
    except httpx.HTTPError as e:
        logger.error(
            f"파이프라인 단계 실행 실패 (variant): job_variants_id={job_variants_id}, "
            f"next_step={stage_info['next_step']}, error={e}"
        )
        # 에러는 상위로 전파하지 않음 (로깅만)
    except Exception as e:
        logger.error(
            f"파이프라인 단계 실행 중 예상치 못한 오류 (variant): job_variants_id={job_variants_id}, "
            f"next_step={stage_info['next_step']}, error={e}",
            exc_info=True
        )

async def _verify_job_variant_state(
    job_variants_id: str,
    expected_step: str,
    expected_status: str,
    tenant_id: str
) -> bool:
    """Job Variant 상태 재확인 (중복 실행 방지)"""
    import asyncpg
    from config import DATABASE_URL
    
    asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
    
    try:
        conn = await asyncpg.connect(asyncpg_url)
        try:
            row = await conn.fetchrow(
                """
                SELECT jv.status, jv.current_step, j.tenant_id
                FROM jobs_variants jv
                INNER JOIN jobs j ON jv.job_id = j.job_id
                WHERE jv.job_variants_id = $1
                """,
                job_variants_id
            )
            
            if not row:
                logger.warning(f"Job Variant를 찾을 수 없음: job_variants_id={job_variants_id}")
                return False
            
            # 상태 확인
            if (row['current_step'] == expected_step 
                and row['status'] == expected_status
                and row['tenant_id'] == tenant_id):
                return True
            
            logger.debug(
                f"Job Variant 상태 불일치: job_variants_id={job_variants_id}, "
                f"expected: step={expected_step}, status={expected_status}, "
                f"actual: step={row['current_step']}, status={row['status']}"
            )
            return False
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Job Variant 상태 확인 오류: {e}", exc_info=True)
        return False

async def _get_overlay_id_from_job_variant(job_variants_id: str, job_id: str, tenant_id: str) -> Optional[str]:
    """
    job_variants_id로부터 최신 overlay_id 조회
    
    job_variants → img_asset_id → planner_proposals → overlay_layouts 경로로 조회
    
    Args:
        job_variants_id: Job Variant ID
        job_id: Job ID (검증용)
        tenant_id: Tenant ID
    
    Returns:
        overlay_id (str) 또는 None
    """
    import asyncpg
    from config import DATABASE_URL
    
    asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
    
    try:
        conn = await asyncpg.connect(asyncpg_url)
        try:
            # job_variants_id로 직접 조회 (job_variants_id 컬럼 추가 후)
            row = await conn.fetchrow(
                """
                SELECT ol.overlay_id
                FROM overlay_layouts ol
                INNER JOIN jobs_variants jv ON ol.job_variants_id = jv.job_variants_id
                INNER JOIN jobs j ON jv.job_id = j.job_id
                WHERE ol.job_variants_id = $1
                  AND j.job_id = $2
                  AND j.tenant_id = $3
                ORDER BY ol.created_at DESC
                LIMIT 1
                """,
                job_variants_id,
                job_id,
                tenant_id
            )
            
            if row and row['overlay_id']:
                return str(row['overlay_id'])
            
            logger.warning(f"overlay_id를 찾을 수 없음: job_variants_id={job_variants_id}, job_id={job_id}, tenant_id={tenant_id}")
            return None
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"overlay_id 조회 오류 (variant): {e}", exc_info=True)
        return None

async def _get_text_and_proposal_from_job_variant(job_variants_id: str, job_id: str, tenant_id: str) -> Optional[dict]:
    """
    job_variants_id로부터 text와 proposal_id 조회
    
    오버레이에 사용할 텍스트는 한글 광고문구(ad_copy_kor)를 사용합니다.
    JS 파트에서 사용자 입력 한글 description → 영어 번역 → GPT로 한글 광고문구 생성한 것을 사용.
    
    job_variants → img_asset_id → planner_proposals에서 최신 proposal_id 조회
    
    Args:
        job_variants_id: Job Variant ID
        job_id: Job ID
        tenant_id: Tenant ID
    
    Returns:
        {'text': str, 'proposal_id': Optional[str]} 또는 None
    """
    import asyncpg
    from config import DATABASE_URL
    
    asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
    
    try:
        conn = await asyncpg.connect(asyncpg_url)
        try:
            # 1. txt_ad_copy_generations에서 ad_copy_kor 조회 (우선순위)
            # JS 파트에서 생성한 한글 광고문구를 오버레이에 사용
            ad_copy_row = await conn.fetchrow(
                """
                SELECT ad_copy_kor
                FROM txt_ad_copy_generations
                WHERE job_id = $1
                  AND generation_stage = 'ad_copy_kor'
                  AND status = 'done'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                job_id
            )
            
            text = None
            if ad_copy_row and ad_copy_row['ad_copy_kor']:
                text = ad_copy_row['ad_copy_kor']
                logger.info(f"한글 광고문구 조회 성공: job_id={job_id}, text_length={len(text)}")
            
            # 2. txt_ad_copy_generations에서 찾지 못한 경우 job_inputs.desc_kor 조회 (fallback)
            if not text:
                text_row = await conn.fetchrow(
                    """
                    SELECT ji.desc_kor
                    FROM jobs j
                    INNER JOIN job_inputs ji ON j.job_id = ji.job_id
                    WHERE j.job_id = $1
                      AND j.tenant_id = $2
                    """,
                    job_id,
                    tenant_id
                )
                
                if text_row and text_row['desc_kor']:
                    text = text_row['desc_kor']
                    logger.info(f"한글 설명 조회 성공 (fallback): job_id={job_id}, text_length={len(text)}")
            
            if not text:
                logger.warning(f"한글 텍스트를 찾을 수 없음: job_variants_id={job_variants_id}, job_id={job_id}, tenant_id={tenant_id}")
                return None
            
            # job_variants → img_asset_id → planner_proposals에서 최신 proposal_id 조회
            proposal_row = await conn.fetchrow(
                """
                SELECT pp.proposal_id
                FROM jobs_variants jv
                INNER JOIN planner_proposals pp ON jv.img_asset_id = pp.image_asset_id
                WHERE jv.job_variants_id = $1
                ORDER BY pp.created_at DESC
                LIMIT 1
                """,
                job_variants_id
            )
            
            proposal_id = str(proposal_row['proposal_id']) if proposal_row and proposal_row['proposal_id'] else None
            
            return {
                'text': text,
                'proposal_id': proposal_id
            }
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"text 및 proposal_id 조회 오류 (variant): {e}", exc_info=True)
        return None


async def _get_text_and_proposal_from_job(job_id: str, tenant_id: str) -> Optional[dict]:
    """
    job_id로부터 text와 proposal_id 조회
    
    job → job_inputs에서 text(desc_eng) 조회
    job → job_inputs → planner_proposals에서 최신 proposal_id 조회
    
    Args:
        job_id: Job ID
        tenant_id: Tenant ID
    
    Returns:
        {'text': str, 'proposal_id': Optional[str]} 또는 None
    """
    import asyncpg
    from config import DATABASE_URL
    
    asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
    
    try:
        conn = await asyncpg.connect(asyncpg_url)
        try:
            # job → job_inputs에서 text 조회 (txt_ad_copy_generations에서 우선 조회)
            # 1. txt_ad_copy_generations에서 ad_copy_eng 조회 (우선순위)
            ad_copy_row = await conn.fetchrow(
                """
                SELECT ad_copy_eng, refined_ad_copy_eng
                FROM txt_ad_copy_generations
                WHERE job_id = $1
                  AND generation_stage IN ('ad_copy_eng', 'refined_ad_copy')
                  AND status = 'done'
                ORDER BY 
                    CASE generation_stage
                        WHEN 'refined_ad_copy' THEN 1
                        WHEN 'ad_copy_eng' THEN 2
                    END,
                    created_at DESC
                LIMIT 1
                """,
                job_id
            )
            
            text = None
            if ad_copy_row:
                text = ad_copy_row['refined_ad_copy_eng'] or ad_copy_row['ad_copy_eng']
            
            # 2. txt_ad_copy_generations에서 찾지 못한 경우 job_inputs.desc_eng 조회 (fallback)
            if not text:
                text_row = await conn.fetchrow(
                    """
                    SELECT ji.desc_eng
                    FROM jobs j
                    INNER JOIN job_inputs ji ON j.job_id = ji.job_id
                    WHERE j.job_id = $1
                      AND j.tenant_id = $2
                    """,
                    job_id,
                    tenant_id
                )
                
                if text_row and text_row['desc_eng']:
                    text = text_row['desc_eng']
            
            if not text:
                logger.warning(f"text를 찾을 수 없음: job_id={job_id}, tenant_id={tenant_id}")
                return None
            
            # job → job_inputs → planner_proposals에서 최신 proposal_id 조회
            proposal_row = await conn.fetchrow(
                """
                SELECT pp.proposal_id
                FROM jobs j
                INNER JOIN job_inputs ji ON j.job_id = ji.job_id
                INNER JOIN planner_proposals pp ON ji.img_asset_id = pp.image_asset_id
                WHERE j.job_id = $1
                  AND j.tenant_id = $2
                ORDER BY pp.created_at DESC
                LIMIT 1
                """,
                job_id,
                tenant_id
            )
            
            proposal_id = str(proposal_row['proposal_id']) if proposal_row and proposal_row['proposal_id'] else None
            
            return {
                'text': text,
                'proposal_id': proposal_id
            }
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"text 및 proposal_id 조회 오류: {e}", exc_info=True)
        return None

async def _check_and_trigger_job_level_stage(
    job_id: str,
    current_step: str,
    status: str,
    tenant_id: str,
    stage_info: dict
):
    """
    모든 variants가 완료되었는지 확인하고, Job 레벨 단계 트리거
    
    Args:
        job_id: Job ID
        current_step: 현재 단계 (예: 'iou_eval')
        status: 현재 상태 (예: 'done')
        tenant_id: Tenant ID
        stage_info: 다음 단계 정보
    """
    import asyncpg
    from config import DATABASE_URL
    
    asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
    
    try:
        conn = await asyncpg.connect(asyncpg_url)
        try:
            # 모든 variants가 current_step (done) 완료되었는지 확인
            row = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total_variants,
                    COUNT(*) FILTER (
                        WHERE status = 'done' AND current_step = $2
                    ) as completed_variants
                FROM jobs_variants
                WHERE job_id = $1
                """,
                uuid.UUID(job_id),
                current_step
            )
            
            if not row:
                logger.warning(f"Job variants를 찾을 수 없음: job_id={job_id}")
                return
            
            total_variants = row['total_variants'] or 0
            completed_variants = row['completed_variants'] or 0
            
            if total_variants == 0:
                logger.warning(f"Job에 variants가 없음: job_id={job_id}")
                return
            
            # 모든 variants가 완료되었는지 확인
            if completed_variants < total_variants:
                logger.debug(
                    f"아직 모든 variants가 완료되지 않음: job_id={job_id}, "
                    f"completed={completed_variants}/{total_variants}"
                )
                return
            
            # Job 상태 확인 및 업데이트
            job_row = await conn.fetchrow(
                """
                SELECT status, current_step
                FROM jobs
                WHERE job_id = $1
                """,
                uuid.UUID(job_id)
            )
            
            if not job_row:
                logger.warning(f"Job을 찾을 수 없음: job_id={job_id}")
                return
            
            # Job이 아직 current_step에 있으면 다음 단계로 진행
            if job_row['current_step'] == current_step and job_row['status'] != 'done':
                # Job 상태를 done으로 업데이트 (트리거 발동)
                await conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'done',
                        current_step = $2,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_id = $1
                      AND current_step = $2
                    """,
                    uuid.UUID(job_id),
                    current_step
                )
                logger.info(
                    f"✅ 모든 variants 완료! Job 레벨 트리거 발동: job_id={job_id}, "
                    f"current_step={current_step} → next_step={stage_info['next_step']}"
                )
            elif job_row['current_step'] == current_step and job_row['status'] == 'done':
                # 이미 done 상태이면 Job 레벨 트리거 직접 실행
                logger.info(
                    f"모든 variants 완료, Job 레벨 트리거 실행: job_id={job_id}, "
                    f"next_step={stage_info['next_step']}"
                )
                await trigger_next_pipeline_stage(
                    job_id=job_id,
                    current_step=current_step,
                    status=status,
                    tenant_id=tenant_id
                )
        finally:
            await conn.close()
    except Exception as e:
        logger.error(
            f"Job 레벨 단계 확인 및 트리거 오류: job_id={job_id}, error={e}",
            exc_info=True
        )


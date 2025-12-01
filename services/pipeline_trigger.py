"""Pipeline Trigger Service
Job 상태 변화에 따라 다음 파이프라인 단계를 자동으로 트리거하는 서비스
"""
########################################################
# created_at: 2025-11-28
# updated_at: 2025-11-28
# author: LEEYH205
# description: Job 상태 변화에 따라 다음 파이프라인 단계를 자동으로 트리거
# version: 1.1.0
# status: development
# tags: pipeline, trigger, automation
# dependencies: httpx, asyncpg
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import logging
import httpx
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
        async with httpx.AsyncClient(timeout=600.0) as client:
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
    
    api_url = f"http://{HOST}:{PORT}{stage_info['api_endpoint']}"
    request_data = {
        "job_id": job_id,
        "tenant_id": tenant_id,
    }
    
    # overlay_id 등이 필요한 단계는 재시도 대상에서 제외 (vlm_analyze, yolo_detect 중심)
    if stage_info.get("needs_overlay_id") or stage_info.get("needs_text_and_proposal"):
        logger.warning(
            f"[RETRY] overlay_id/text가 필요한 단계는 재시도 스킵: "
            f"job_id={job_id}, current_step={current_step}, api={api_url}"
        )
        return
    
    logger.info(
        f"[RETRY] 파이프라인 단계 재시도: job_id={job_id}, "
        f"current_step={current_step}, api={api_url}"
    )
    
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(api_url, json=request_data)
            response.raise_for_status()
            logger.info(
                f"[RETRY] 파이프라인 단계 재실행 성공: job_id={job_id}, "
                f"current_step={current_step}"
            )
    except httpx.HTTPError as e:
        logger.error(
            f"[RETRY] 파이프라인 단계 재실행 실패: job_id={job_id}, "
            f"current_step={current_step}, error={e}"
        )
    except Exception as e:
        logger.error(
            f"[RETRY] 파이프라인 단계 재실행 중 예상치 못한 오류: job_id={job_id}, "
            f"current_step={current_step}, error={e}",
            exc_info=True,
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
    
    # 트리거 조건 확인
    if not current_step or status != 'done':
        logger.debug(
            f"트리거 조건 불만족: job_variants_id={job_variants_id}, "
            f"current_step={current_step}, status={status}"
        )
        return
    
    # 다음 단계 정보 조회
    stage_info = PIPELINE_STAGES.get((current_step, status))
    if not stage_info:
        logger.debug(
            f"다음 단계 없음: job_variants_id={job_variants_id}, "
            f"current_step={current_step}, status={status}"
        )
        return
    
    # 중복 실행 방지: job_variant 상태 재확인
    if not await _verify_job_variant_state(job_variants_id, current_step, status, tenant_id):
        logger.info(
            f"Job Variant 상태가 변경되어 스킵: job_variants_id={job_variants_id}, "
            f"expected: current_step={current_step}, status={status}"
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
        async with httpx.AsyncClient(timeout=600.0) as client:
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
    
    job → job_inputs에서 text(desc_eng) 조회
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
                logger.warning(f"text를 찾을 수 없음: job_variants_id={job_variants_id}, job_id={job_id}, tenant_id={tenant_id}")
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


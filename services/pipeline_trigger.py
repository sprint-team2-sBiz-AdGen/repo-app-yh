"""Pipeline Trigger Service
Job 상태 변화에 따라 다음 파이프라인 단계를 자동으로 트리거하는 서비스
"""
########################################################
# created_at: 2025-11-28
# author: LEEYH205
# description: Job 상태 변화에 따라 다음 파이프라인 단계를 자동으로 트리거
# version: 1.0.0
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
        'method': 'POST'
    },
    ('vlm_analyze', 'done'): {
        'next_step': 'yolo_detect',
        'api_endpoint': '/api/yh/yolo/detect',
        'method': 'POST'
    },
    ('yolo_detect', 'done'): {
        'next_step': 'planner',
        'api_endpoint': '/api/yh/planner',
        'method': 'POST'
    },
    ('planner', 'done'): {
        'next_step': 'overlay',
        'api_endpoint': '/api/yh/overlay',
        'method': 'POST'
    },
    ('overlay', 'done'): {
        'next_step': 'vlm_judge',
        'api_endpoint': '/api/yh/llava/stage2/judge',
        'method': 'POST'
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


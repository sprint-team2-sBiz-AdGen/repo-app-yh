
"""LLaVa Stage 2 Validation 라우터"""
########################################################
# LLaVa Stage 2 Validation API
# - 최종 광고 시각 결과물 판단
# - brief 준수 여부 확인
# - 가림, 대비, CTA 등 품질 요소 검증
# - DB에 결과 저장 (vlm_traces)
# - job 상태 업데이트
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-30
# author: LEEYH205
# description: LLaVa Stage 2 validation API
# version: 1.1.0
# status: production
# tags: llava, stage2, validation, judge
# dependencies: fastapi, pydantic, PIL, sqlalchemy
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter, HTTPException, Depends
from PIL import Image
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
import json
import time
from models import JudgeIn, JudgeOut
from utils import abs_from_url
from services.llava_service import judge_final_ad
from database import get_db, Job, OverlayLayout, VLMTrace, JobVariant, ImageAsset
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/llava/stage2", tags=["llava-stage2"])


@router.post("/judge", response_model=JudgeOut)
def judge(body: JudgeIn, db: Session = Depends(get_db)):
    """
    LLaVa Stage 2 Validation: 최종 광고 시각 결과물 판단
    
    최종 광고 시각 결과물에 대한 심층 검증을 수행합니다.
    
    Args:
        body: JudgeIn 모델
            - job_id: 기존 job의 ID (업데이트할 job) - 필수
            - tenant_id: 테넌트 ID - 필수
            - overlay_id: Overlay ID (Optional, overlay_layouts에서 render_asset_url을 가져올 수 있으면 생략 가능)
            - render_asset_url: 렌더링된 이미지 URL (Optional, overlay_id가 있으면 생략 가능)
        
    Returns:
        JudgeOut:
            - job_id: str                  # 업데이트된 job 레코드 ID
            - vlm_trace_id: str            # 생성된 vlm_trace 레코드 ID
            - on_brief: bool               # brief 준수 여부
            - occlusion: bool             # 가림 여부 (True면 가림 있음)
            - contrast_ok: bool           # 대비 적절성
            - cta_present: bool           # CTA 존재 여부
            - analysis: str                # LLaVA 분석 결과 텍스트
            - issues: List[str]            # 발견된 이슈 목록
    
    Raises:
        HTTPException 404: job 또는 overlay_layout을 찾을 수 없는 경우
        HTTPException 400: 이미지 파일을 찾을 수 없거나 로드할 수 없는 경우
        HTTPException 500: LLaVa 모델 로드, 판단, 또는 DB 저장 중 오류 발생
    """
    try:
        # Step 0: job_variants_id 및 job_id 검증
        try:
            job_variants_id = uuid.UUID(body.job_variants_id)
            job_id = uuid.UUID(body.job_id)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid UUID format: {str(e)}"
            )
        
        # job_variants 조회
        job_variant = db.query(JobVariant).filter(JobVariant.job_variants_id == job_variants_id).first()
        if not job_variant:
            logger.error(f"Job variant not found: job_variants_id={body.job_variants_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Job variant not found: {body.job_variants_id}"
            )
        
        # job 조회 및 검증
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            logger.error(f"Job not found: job_id={body.job_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Job not found: {body.job_id}"
            )
        
        # job_variant와 job의 job_id 일치 확인
        if job_variant.job_id != job_id:
            logger.error(f"Job variant job_id mismatch: job_variant.job_id={job_variant.job_id}, request.job_id={job_id}")
            raise HTTPException(
                status_code=400,
                detail=f"Job variant job_id mismatch"
            )
        
        if job.tenant_id != body.tenant_id:
            logger.error(f"Job tenant_id mismatch: job.tenant_id={job.tenant_id}, request.tenant_id={body.tenant_id}")
            raise HTTPException(
                status_code=400,
                detail=f"Job tenant_id mismatch"
            )
        
        # Step 0.5: job_variant 상태 확인 (current_step='overlay', status='done'이어야 함)
        if job_variant.current_step != 'overlay' or job_variant.status != 'done':
            logger.error(f"Job variant 상태가 judge 실행 조건을 만족하지 않음: current_step={job_variant.current_step}, status={job_variant.status}")
            raise HTTPException(
                status_code=400,
                detail=f"Job variant 상태가 judge 실행 조건을 만족하지 않습니다. current_step='overlay', status='done'이어야 합니다. (현재: current_step='{job_variant.current_step}', status='{job_variant.status}')"
            )
        
        # Step 0.6: Judge 시작 - job_variants 상태 업데이트 (current_step='vlm_judge', status='running')
        db.execute(
            text("""
                UPDATE jobs_variants 
                SET status = 'running', 
                    current_step = 'vlm_judge',
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_variants_id = :job_variants_id
            """),
            {"job_variants_id": job_variants_id}
        )
        db.flush()
        logger.info(f"Updated job_variant: {job_variants_id} - status=running, current_step=vlm_judge")
        
        # Step 1: render_asset_url 가져오기
        render_asset_url = body.render_asset_url
        if not render_asset_url:
            # 우선순위 1: job_variant에서 overlaid_img_asset_id 조회
            if job_variant.overlaid_img_asset_id:
                overlaid_asset = db.query(ImageAsset).filter(
                    ImageAsset.image_asset_id == job_variant.overlaid_img_asset_id
                ).first()
                if overlaid_asset:
                    render_asset_url = overlaid_asset.image_url
                    logger.info(f"Found overlaid image from jobs_variants: image_asset_id={job_variant.overlaid_img_asset_id}, url={render_asset_url}")
        
        if not render_asset_url:
            # 우선순위 2: overlay_id로부터 render_asset_url 조회 (하위 호환성)
            if not body.overlay_id:
                logger.error(f"render_asset_url, job_variant.overlaid_img_asset_id, 또는 overlay_id가 필요합니다: job_id={job_id}")
                raise HTTPException(
                    status_code=400,
                    detail=f"render_asset_url, job_variant.overlaid_img_asset_id, 또는 overlay_id가 필요합니다"
                )
            
            try:
                overlay_id_uuid = uuid.UUID(body.overlay_id)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid overlay_id format: {body.overlay_id}"
                )
            
            overlay = db.query(OverlayLayout).filter(OverlayLayout.overlay_id == overlay_id_uuid).first()
            if not overlay:
                logger.error(f"Overlay layout not found: overlay_id={body.overlay_id}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Overlay layout not found: {body.overlay_id}"
                )
            
            # overlay.layout에서 render 정보 가져오기 (fallback)
            layout = overlay.layout if isinstance(overlay.layout, dict) else json.loads(overlay.layout) if isinstance(overlay.layout, str) else {}
            render = layout.get('render', {})
            render_asset_url = render.get('url')
            
            if not render_asset_url:
                logger.error(f"Render URL not found in overlay layout: overlay_id={body.overlay_id}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Render URL not found in overlay layout"
                )
            
            logger.warning(f"Using render URL from overlay_layouts (fallback): overlay_id={body.overlay_id}, URL: {render_asset_url}")
        
        # Step 2: 이미지 로드
        try:
            image = Image.open(abs_from_url(render_asset_url)).convert("RGB")
        except Exception as e:
            logger.error(f"이미지 로드 실패: {e}")
            raise HTTPException(status_code=400, detail=f"이미지를 로드할 수 없습니다: {str(e)}")
        
        # Step 3: LLaVA를 사용한 판단
        start_time = time.time()
        try:
            result = judge_final_ad(image=image)
        except Exception as e:
            logger.error(f"LLaVA 판단 실패: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"LLaVA 판단 중 오류가 발생했습니다: {str(e)}")
        
        latency_ms = (time.time() - start_time) * 1000
        
        # Step 4: vlm_traces에 저장
        vlm_trace_id = uuid.uuid4()
        request_data = {
            "render_asset_url": render_asset_url,
            "overlay_id": body.overlay_id
        }
        response_data = result
        
        try:
            db.execute(
                text("""
                    INSERT INTO vlm_traces (
                        vlm_trace_id, job_id, provider, operation_type, 
                        request, response, latency_ms, created_at, updated_at
                    )
                    VALUES (
                        :vlm_trace_id, :job_id, :provider, :operation_type,
                        CAST(:request AS jsonb), CAST(:response AS jsonb), :latency_ms,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                """),
                {
                    "vlm_trace_id": vlm_trace_id,
                    "job_id": job_id,
                    "provider": "llava",
                    "operation_type": "judge",
                    "request": json.dumps(request_data),
                    "response": json.dumps(response_data),
                    "latency_ms": latency_ms
                }
            )
            db.commit()
            logger.info(f"Saved to DB: job_id={job_id}, vlm_trace_id={vlm_trace_id}, latency_ms={latency_ms:.2f}")
        except Exception as e:
            logger.error(f"Failed to save to DB: {str(e)}", exc_info=True)
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save judge result to database: {str(e)}"
            )
        
        # Step 5: Job 상태를 'done'으로 업데이트
        try:
            db.execute(
                text("""
                    UPDATE jobs_variants 
                    SET status = 'done', 
                        current_step = 'vlm_judge',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_variants_id = :job_variants_id
                """),
                {"job_variants_id": job_variants_id}
            )
            db.commit()
            logger.info(f"Job variant 상태 업데이트: job_variants_id={job_variants_id}, status='done'")
        except Exception as e:
            logger.error(f"Job 상태 업데이트 실패: {e}")
            db.rollback()
            # 상태 업데이트 실패해도 결과는 반환
            logger.warning(f"Job 상태 업데이트 실패했지만 결과는 반환합니다: {e}")
        
        # Step 6: 응답 반환
        return JudgeOut(
            job_id=body.job_id,
            vlm_trace_id=str(vlm_trace_id),
            on_brief=result.get("on_brief", False),
            occlusion=result.get("occlusion", False),
            contrast_ok=result.get("contrast_ok", False),
            cta_present=result.get("cta_present", False),
            analysis=result.get("analysis", ""),
            issues=result.get("issues", [])
        )
        
    except HTTPException:
        # HTTPException 발생 시 job_variants 상태를 failed로 업데이트
        try:
            if 'job_variants_id' in locals():
                db.execute(
                    text("""
                        UPDATE jobs_variants 
                        SET status = 'failed', 
                            updated_at = CURRENT_TIMESTAMP
                        WHERE job_variants_id = :job_variants_id
                    """),
                    {"job_variants_id": job_variants_id}
                )
                db.commit()
                logger.info(f"Job variant 상태 업데이트: job_variants_id={job_variants_id}, status='failed' (오류 발생)")
        except Exception as e:
            logger.error(f"Job variant 상태 업데이트 실패 (오류 처리 중): {e}")
            db.rollback()
        raise
    except Exception as e:
        # 기타 예외 발생 시 job_variants 상태를 failed로 업데이트
        try:
            if 'job_variants_id' in locals():
                db.execute(
                    text("""
                        UPDATE jobs_variants 
                        SET status = 'failed', 
                            updated_at = CURRENT_TIMESTAMP
                        WHERE job_variants_id = :job_variants_id
                    """),
                    {"job_variants_id": job_variants_id}
                )
                db.commit()
                logger.info(f"Job variant 상태 업데이트: job_variants_id={job_variants_id}, status='failed' (예외 발생)")
        except Exception as update_error:
            logger.error(f"Job variant 상태 업데이트 실패 (예외 처리 중): {update_error}")
            db.rollback()
        logger.error(f"Judge API 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")


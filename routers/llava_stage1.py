"""LLaVa Stage 1 Validation 라우터"""
########################################################
# LLaVa Stage 1 Validation API
# - 이미지와 광고문구의 논리적 일관성 검증
# - 이미지 품질 검증
# - 관련성 점수 계산
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-28
# author: LEEYH205
# description: LLaVa Stage 1 validation API
# version: 1.1.0
# status: production
# tags: llava, stage1, validation
# dependencies: fastapi, pydantic, PIL, transformers
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter, HTTPException, Depends
from PIL import Image
from sqlalchemy.orm import Session
from sqlalchemy import and_, text
import uuid
from models import LLaVaStage1In, LLaVaStage1Out
from utils import abs_from_url
from services.llava_service import validate_image_and_text
from database import get_db, ImageAsset, Job, JobInput, VLMTrace, JobVariant
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/llava/stage1", tags=["llava-stage1"])


@router.post("/validate", response_model=LLaVaStage1Out)
def stage1_validate(body: LLaVaStage1In, db: Session = Depends(get_db)):
    """
    LLaVa Stage 1 Validation: 이미지와 광고문구의 적합성 검증
    
    이미지와 광고문구의 논리적 일관성을 검증하고, 관련성 점수를 계산합니다.
    
    Args:
        body: LLaVaStage1In 모델
            - job_id: 기존 job의 ID (업데이트할 job)
            - tenant_id: 테넌트 ID
            - asset_url: 이미지 URL (Optional, job_inputs에서 가져올 수 있으면 생략 가능)
            - ad_copy_text: 광고 문구 텍스트 (Optional, job_inputs에서 가져올 수 있으면 생략 가능)
        
    Note:
        - job_inputs 테이블에서 img_asset_id와 desc_eng을 가져와서 사용합니다.
        - 요청에 asset_url이나 ad_copy_text가 제공되면 그것을 우선 사용합니다.
            - prompt: 커스텀 검증 프롬프트 (Optional, None이면 기본 프롬프트 사용)
    
    Returns:
        LLaVaStage1Out:
            - job_id: str                  # 업데이트된 job 레코드 ID
            - vlm_trace_id: str            # 생성된 vlm_trace 레코드 ID
            - is_valid: bool               # 적합성 여부
            - image_quality_ok: bool       # 이미지 품질 OK 여부
            - relevance_score: float       # 관련성 점수 (0.0-1.0)
            - analysis: str                # LLaVa 분석 결과 텍스트
            - issues: List[str]            # 발견된 이슈 목록
            - recommendations: List[str]   # 추천사항 목록
    
    Raises:
        HTTPException 404: job 또는 image_asset을 찾을 수 없는 경우
        HTTPException 400: 이미지 파일을 찾을 수 없거나 로드할 수 없는 경우
        HTTPException 500: LLaVa 모델 로드, 검증, 또는 DB 저장 중 오류 발생
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
        
        # job의 tenant_id 확인
        if job.tenant_id != body.tenant_id:
            logger.error(f"Job tenant_id mismatch: job.tenant_id={job.tenant_id}, request.tenant_id={body.tenant_id}")
            raise HTTPException(
                status_code=400,
                detail=f"Job tenant_id mismatch"
            )
        
        # job_variants 상태 업데이트: current_step='vlm_analyze', status='running'
        db.execute(
            text("""
                UPDATE jobs_variants 
                SET status = 'running', 
                    current_step = 'vlm_analyze',
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_variants_id = :job_variants_id
            """),
            {"job_variants_id": job_variants_id}
        )
        db.flush()
        logger.info(f"Updated job_variant: {job_variants_id} - status=running, current_step=vlm_analyze")
        
        # Step 1: jobs_variants에서 이미지 가져오기
        image_asset_id = job_variant.img_asset_id
        if not image_asset_id:
            logger.error(f"Image asset ID not found in job_variant: job_variants_id={job_variants_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Image asset ID not found in job variant"
            )
        
        # image_assets에서 이미지 정보 가져오기
        image_asset = db.query(ImageAsset).filter(ImageAsset.image_asset_id == image_asset_id).first()
        if not image_asset:
            logger.error(f"Image asset not found: image_asset_id={image_asset_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Image asset not found: {image_asset_id}"
            )
        
        asset_url = image_asset.image_url
        logger.info(f"Found image asset from job_variant: {image_asset_id}, URL: {asset_url}")
        
        # 광고문구 조회 (우선순위: body.ad_copy_text → txt_ad_copy_generations → job_inputs.desc_eng)
        ad_copy_text = None
        
        # 1순위: 요청에 ad_copy_text가 있으면 사용
        if body.ad_copy_text:
            ad_copy_text = body.ad_copy_text
            logger.info(f"Using ad_copy_text from request body")
        else:
            # 2순위: txt_ad_copy_generations 테이블에서 ad_copy_eng 조회
            ad_copy_gen = db.execute(
                text("""
                    SELECT ad_copy_eng
                    FROM txt_ad_copy_generations
                    WHERE job_id = :job_id
                      AND generation_stage = 'ad_copy_eng'
                      AND status = 'done'
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"job_id": job_id}
            ).first()
            
            if ad_copy_gen and ad_copy_gen.ad_copy_eng:
                ad_copy_text = ad_copy_gen.ad_copy_eng
                logger.info(f"Using ad_copy_eng from txt_ad_copy_generations: job_id={job_id}")
            else:
                # 3순위: job_inputs에서 desc_eng 조회 (하위 호환성)
                job_input = db.query(JobInput).filter(JobInput.job_id == job_id).first()
                if job_input and job_input.desc_eng:
                    ad_copy_text = job_input.desc_eng
                    logger.info(f"Using desc_eng from job_inputs: job_id={job_id}")
        
        if not ad_copy_text:
            logger.warning(f"Ad copy text not found in request, txt_ad_copy_generations, or job_input: job_id={job_id}")
        
        # Step 2: 이미지 로드
        try:
            image_path = abs_from_url(asset_url)
            image = Image.open(image_path)
            logger.info(f"Image loaded successfully: {image_path}, size: {image.size}")
        except FileNotFoundError:
            logger.error(f"Image file not found: {asset_url}")
            raise HTTPException(
                status_code=400,
                detail=f"Image file not found: {asset_url}"
            )
        except Exception as e:
            logger.error(f"Failed to load image: {asset_url}, error: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to load image: {str(e)}"
            )
        
        # Step 3: 검증 프롬프트 구성
        # ad_copy_text가 있으면 검증 프롬프트에 포함, 없으면 이미지 분석만
        validation_prompt = body.prompt
        if validation_prompt is None and ad_copy_text:
            # 기본 검증 프롬프트는 validate_image_and_text 내부에서 생성됨
            pass
        
        # Step 4: job_inputs 레코드 업데이트 (요청에 ad_copy_text가 있으면)
        if body.ad_copy_text and body.ad_copy_text != job_input.desc_eng:
            db.execute(
                text("""
                    UPDATE job_inputs 
                    SET desc_eng = :desc_eng,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_id = :job_id
                """),
                {
                    "job_id": job_id,
                    "desc_eng": body.ad_copy_text
                }
            )
            db.flush()
            logger.info(f"Updated job_input desc_eng for job: {job_id}")
        
        # Step 5: LLaVa를 사용한 검증
        import json
        import time
        start_time = time.time()
        try:
            result = validate_image_and_text(
                image=image,
                ad_copy_text=ad_copy_text,  # job_inputs에서 가져온 값 사용
                validation_prompt=validation_prompt
            )
            latency_ms = (time.time() - start_time) * 1000
            logger.info(f"Validation completed: is_valid={result.get('is_valid')}, score={result.get('relevance_score')}, latency={latency_ms:.2f}ms")
        except Exception as e:
            logger.error(f"LLaVa validation failed: {str(e)}", exc_info=True)
            # job_variants 상태를 'failed'로 업데이트
            try:
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
            except Exception as update_error:
                logger.error(f"Failed to update job_variant status to failed: {update_error}")
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"LLaVa validation failed: {str(e)}"
            )
        
        # Step 7: vlm_traces 레코드 생성 (검증 결과 저장)
        vlm_trace_id = uuid.uuid4()
        
        # 요청 데이터 구성
        request_data = {
            "asset_url": asset_url,  # job_inputs에서 가져온 값 사용
            "ad_copy_text": ad_copy_text,  # job_inputs에서 가져온 값 사용
            "prompt": validation_prompt
        }
        
        # 응답 데이터 구성 (검증 결과)
        response_data = result
        
        # vlm_traces에 저장
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
                "operation_type": "analyze",
                "request": json.dumps(request_data),
                "response": json.dumps(response_data),
                "latency_ms": latency_ms
            }
        )
        
        # Step 8: jobs_variants 상태를 'done'으로 업데이트
        db.execute(
            text("""
                UPDATE jobs_variants 
                SET status = 'done', 
                    current_step = 'vlm_analyze',
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_variants_id = :job_variants_id
            """),
            {"job_variants_id": job_variants_id}
        )
        
        # Step 9: 커밋
        try:
            db.commit()
            logger.info(f"Saved to DB: job_id={job_id}, vlm_trace_id={vlm_trace_id}, latency_ms={latency_ms:.2f}")
        except Exception as e:
            logger.error(f"Failed to commit to DB: {str(e)}", exc_info=True)
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save validation result to database: {str(e)}"
            )
        
        # Step 10: 응답 반환
        # font_recommendation 딕셔너리를 FontRecommendation 모델로 변환
        font_rec_dict = result.get('font_recommendation')
        font_recommendation = None
        if font_rec_dict:
            from models import FontRecommendation
            try:
                font_recommendation = FontRecommendation(**font_rec_dict)
            except Exception as e:
                logger.warning(f"Failed to parse font recommendation: {e}")
        
        return LLaVaStage1Out(
            job_id=body.job_id,  # 요청에서 받은 job_id 그대로 반환
            vlm_trace_id=str(vlm_trace_id),
            is_valid=result.get('is_valid'),
            image_quality_ok=result.get('image_quality_ok'),
            relevance_score=result.get('relevance_score'),
            analysis=result.get('analysis', ''),
            issues=result.get('issues', []),
            recommendations=result.get('recommendations', []),
            font_recommendation=font_recommendation
        )
    
    except HTTPException:
        # HTTPException은 그대로 재발생
        raise
    except Exception as e:
        # 예상치 못한 오류 - job_variants 상태를 'failed'로 업데이트
        logger.error(f"Unexpected error in stage1_validate: {str(e)}", exc_info=True)
        if db:
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
            except Exception as update_error:
                logger.error(f"Failed to update job_variant status to failed: {update_error}")
            db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


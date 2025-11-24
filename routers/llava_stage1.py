"""LLaVa Stage 1 Validation 라우터"""
########################################################
# LLaVa Stage 1 Validation API
# - 이미지와 광고문구의 논리적 일관성 검증
# - 이미지 품질 검증
# - 관련성 점수 계산
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-20
# author: LEEYH205
# description: LLaVa Stage 1 validation API
# version: 1.0.0
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
from database import get_db, ImageAsset, LLMImage, LLMTraces
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
            - tenant_id: 테넌트 ID
            - asset_url: 이미지 URL (예: /assets/yh/image_to_use/...)
            - ad_copy_text: 광고 문구 텍스트 (Optional)
            - prompt: 커스텀 검증 프롬프트 (Optional, None이면 기본 프롬프트 사용)
    
    Returns:
        LLaVaStage1Out:
            - llm_image_id: str           # 생성된 llm_image 레코드 ID
            - llm_trace_id: str            # 생성된 llm_trace 레코드 ID
            - is_valid: bool               # 적합성 여부
            - image_quality_ok: bool       # 이미지 품질 OK 여부
            - relevance_score: float       # 관련성 점수 (0.0-1.0)
            - analysis: str                # LLaVa 분석 결과 텍스트
            - issues: List[str]            # 발견된 이슈 목록
            - recommendations: List[str]   # 추천사항 목록
    
    Raises:
        HTTPException 404: image_asset을 찾을 수 없는 경우
        HTTPException 400: 이미지 파일을 찾을 수 없거나 로드할 수 없는 경우
        HTTPException 500: LLaVa 모델 로드, 검증, 또는 DB 저장 중 오류 발생
    """
    try:
        # Step 1: image_assets에서 image_asset_id 조회
        image_asset = db.query(ImageAsset).filter(
            and_(
                ImageAsset.image_url == body.asset_url,
                ImageAsset.tenant_id == body.tenant_id
            )
        ).first()
        
        if not image_asset:
            logger.error(f"Image asset not found: asset_url={body.asset_url}, tenant_id={body.tenant_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Image asset not found for URL: {body.asset_url}"
            )
        
        image_asset_id = image_asset.image_asset_id
        logger.info(f"Found image asset: {image_asset_id} for URL: {body.asset_url}")
        
        # Step 2: 이미지 로드
        try:
            image_path = abs_from_url(body.asset_url)
            image = Image.open(image_path)
            logger.info(f"Image loaded successfully: {image_path}, size: {image.size}")
        except FileNotFoundError:
            logger.error(f"Image file not found: {body.asset_url}")
            raise HTTPException(
                status_code=400,
                detail=f"Image file not found: {body.asset_url}"
            )
        except Exception as e:
            logger.error(f"Failed to load image: {body.asset_url}, error: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to load image: {str(e)}"
            )
        
        # Step 3: 검증 프롬프트 구성
        # ad_copy_text가 있으면 검증 프롬프트에 포함, 없으면 이미지 분석만
        validation_prompt = body.prompt
        if validation_prompt is None and body.ad_copy_text:
            # 기본 검증 프롬프트는 validate_image_and_text 내부에서 생성됨
            pass
        
        # Step 4: llm_image 레코드 생성 (pk는 SERIAL이므로 raw SQL 사용)
        llm_image_id = uuid.uuid4()
        llm_image_uid = uuid.uuid4().hex
        
        # pk는 SERIAL 타입이므로 DB에서 자동 생성됨 (raw SQL로 제외)
        db.execute(
            text("""
                INSERT INTO llm_image (llm_image_id, image_id, prompt, uid, created_at, updated_at)
                VALUES (:llm_image_id, :image_id, :prompt, :uid, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """),
            {
                "llm_image_id": llm_image_id,
                "image_id": image_asset_id,
                "prompt": validation_prompt if validation_prompt else (body.ad_copy_text or ""),
                "uid": llm_image_uid
            }
        )
        db.flush()  # ID를 얻기 위해 flush
        
        logger.info(f"Created llm_image record: {llm_image_id}")
        
        # Step 5: LLaVa를 사용한 검증
        try:
            result = validate_image_and_text(
                image=image,
                ad_copy_text=body.ad_copy_text,
                validation_prompt=validation_prompt
            )
            logger.info(f"Validation completed: is_valid={result.get('is_valid')}, score={result.get('relevance_score')}")
        except Exception as e:
            logger.error(f"LLaVa validation failed: {str(e)}", exc_info=True)
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"LLaVa validation failed: {str(e)}"
            )
        
        # Step 6: llm_traces 레코드 생성 (검증 결과 저장, pk는 SERIAL이므로 raw SQL 사용)
        llm_trace_id = uuid.uuid4()
        llm_trace_uid = uuid.uuid4().hex
        
        # pk는 SERIAL 타입이므로 DB에서 자동 생성됨 (raw SQL로 제외)
        import json
        db.execute(
            text("""
                INSERT INTO llm_traces (llm_trace_id, llm_image_id, response, uid, created_at, updated_at)
                VALUES (:llm_trace_id, :llm_image_id, :response::jsonb, :uid, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """),
            {
                "llm_trace_id": llm_trace_id,
                "llm_image_id": llm_image_id,
                "response": json.dumps(result),  # JSONB에 딕셔너리를 JSON 문자열로 변환
                "uid": llm_trace_uid
            }
        )
        
        # Step 7: 커밋
        try:
            db.commit()
            logger.info(f"Saved to DB: llm_image_id={llm_image_id}, llm_trace_id={llm_trace_id}")
        except Exception as e:
            logger.error(f"Failed to commit to DB: {str(e)}", exc_info=True)
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save validation result to database: {str(e)}"
            )
        
        # Step 8: 응답 반환
        return LLaVaStage1Out(
            llm_image_id=str(llm_image_id),
            llm_trace_id=str(llm_trace_id),
            is_valid=result.get('is_valid'),
            image_quality_ok=result.get('image_quality_ok'),
            relevance_score=result.get('relevance_score'),
            analysis=result.get('analysis', ''),
            issues=result.get('issues', []),
            recommendations=result.get('recommendations', [])
        )
    
    except HTTPException:
        # HTTPException은 그대로 재발생
        raise
    except Exception as e:
        # 예상치 못한 오류
        logger.error(f"Unexpected error in stage1_validate: {str(e)}", exc_info=True)
        if db:
            db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


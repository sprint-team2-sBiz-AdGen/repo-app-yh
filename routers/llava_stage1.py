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

from fastapi import APIRouter, HTTPException
from PIL import Image
from models import LLaVaStage1In
from utils import abs_from_url
from services.llava_service import validate_image_and_text
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/llava/stage1", tags=["llava-stage1"])


@router.post("/validate")
def stage1_validate(body: LLaVaStage1In):
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
        {
            "is_valid": bool,              # 적합성 여부
            "image_quality_ok": bool,      # 이미지 품질 OK 여부
            "relevance_score": float,      # 관련성 점수 (0.0-1.0)
            "analysis": str,               # LLaVa 분석 결과 텍스트
            "issues": List[str],            # 발견된 이슈 목록
            "recommendations": List[str]    # 추천사항 목록
        }
    
    Raises:
        HTTPException 400: 이미지를 찾을 수 없거나 로드할 수 없는 경우
        HTTPException 500: LLaVa 모델 로드 또는 검증 중 오류 발생
    """
    try:
        # 이미지 로드
        try:
            image_path = abs_from_url(body.asset_url)
            image = Image.open(image_path)
            logger.info(f"Image loaded successfully: {image_path}, size: {image.size}")
        except FileNotFoundError:
            logger.error(f"Image not found: {body.asset_url}")
            raise HTTPException(
                status_code=400,
                detail=f"Image not found: {body.asset_url}"
            )
        except Exception as e:
            logger.error(f"Failed to load image: {body.asset_url}, error: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to load image: {str(e)}"
            )
        
        # LLaVa를 사용한 검증
        try:
            result = validate_image_and_text(
                image=image,
                ad_copy_text=body.ad_copy_text,
                validation_prompt=body.prompt
            )
            logger.info(f"Validation completed: is_valid={result.get('is_valid')}, score={result.get('relevance_score')}")
            return result
        except Exception as e:
            logger.error(f"LLaVa validation failed: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"LLaVa validation failed: {str(e)}"
            )
    
    except HTTPException:
        # HTTPException은 그대로 재발생
        raise
    except Exception as e:
        # 예상치 못한 오류
        logger.error(f"Unexpected error in stage1_validate: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


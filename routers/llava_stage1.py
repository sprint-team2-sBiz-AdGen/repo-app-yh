
"""LLaVa Stage 1 Validation 라우터"""
########################################################
# TODO: Implement the actual LLaVa Stage 1 validation logic
#       - Load LLaVa model
#       - Process image with LLaVa
#       - Validate image and ad copy text compatibility
#       - Check image quality
#       - Check relevance between image and ad copy
#       - Return validation results
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-20
# author: LEEYH205
# description: LLaVa Stage 1 validation logic
# version: 0.1.0
# status: development
# tags: llava, stage1, validation
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter
from PIL import Image
from models import LLaVaStage1In
from utils import abs_from_url
from services.llava_service import validate_image_and_text

router = APIRouter(prefix="/api/yh/llava/stage1", tags=["llava-stage1"])


@router.post("/validate")
def stage1_validate(body: LLaVaStage1In):
    """LLaVa Stage 1 Validation: 초기 이미지와 광고문구 검증 (선택적)"""
    # TODO: 실제 LLaVa 모델을 사용한 검증 로직 구현
    # - 이미지와 광고문구의 적합성 검증
    # - 이미지 품질 검증
    # - 광고문구와 이미지의 관련성 검증

    # 이미지 로드
    image = Image.open(abs_from_url(body.asset_url))
    
    # LLaVa를 사용한 검증
    result = validate_image_and_text(
        image=image,
        ad_copy_text=body.ad_copy_text,
        validation_prompt=body.prompt
    )
    
    return result


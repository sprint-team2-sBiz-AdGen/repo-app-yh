
"""LLaVa Stage 2 Validation 라우터"""
########################################################
# TODO: Implement the actual LLaVa Stage 2 validation logic
#       - Load LLaVa model
#       - Process final ad visual output with LLaVa
#       - Check on_brief (brief 준수 여부)
#       - Check occlusion (가림 여부)
#       - Check contrast_ok (대비 적절성)
#       - Check cta_present (CTA 존재 여부)
#       - Return issues list
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-20
# author: LEEYH205
# description: LLaVa Stage 2 validation logic
# version: 0.1.0
# status: development
# tags: llava, stage2, validation, judge
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter
from PIL import Image
from models import JudgeIn
from utils import abs_from_url
from services.llava_service import judge_final_ad

router = APIRouter(prefix="/api/yh/llava/stage2", tags=["llava-stage2"])


@router.post("/judge")
def judge(body: JudgeIn):
    """LLaVa Stage 2 Validation: 최종 광고 시각 결과물 판단"""
    # TODO: 실제 LLaVa 모델을 사용한 판단 로직 구현
    # - 최종 광고 시각 결과물에 대한 심층 검증
    # - brief 준수 여부 확인
    # - 가림, 대비, CTA 등 품질 요소 검증

    # 이미지 로드
    image = Image.open(abs_from_url(body.render_asset_url))
    
    # LLaVa를 사용한 판단
    result = judge_final_ad(image=image)
    
    return result


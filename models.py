
"""Pydantic 모델 정의"""
########################################################
# TODO: Implement the actual Pydantic models
#       - DetectIn
#       - PlannerIn
#       - OverlayIn
#       - EvalIn
#       - JudgeIn
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-20    
# author: LEEYH205
# description: Pydantic models
# version: 0.1.0
# status: development
# tags: pydantic
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from pydantic import BaseModel
from typing import Optional


class DetectIn(BaseModel):
    """YOLO 감지 요청 모델"""
    tenant_id: str
    asset_url: str
    model: Optional[str] = "forbidden"


class PlannerIn(BaseModel):
    """Planner 요청 모델"""
    tenant_id: str
    asset_url: str
    detections: Optional[dict] = None


class OverlayIn(BaseModel):
    """Overlay 요청 모델"""
    tenant_id: str
    variant_asset_url: str
    proposal_id: Optional[str] = None
    text: str
    x_align: str = "center"
    y_align: str = "top"
    text_size: int = 32
    overlay_color: Optional[str] = None  # "00000080"
    text_color: Optional[str] = "ffffffff"
    margin: Optional[str] = "8px"


class EvalIn(BaseModel):
    """Evaluation 요청 모델"""
    tenant_id: str
    render_asset_url: str


class JudgeIn(BaseModel):
    """Judge 요청 모델"""
    tenant_id: str
    render_asset_url: str


class LLaVaStage1In(BaseModel):
    """LLaVa Stage 1 Validation 요청 모델"""
    tenant_id: str
    asset_url: str
    ad_copy_text: Optional[str] = None
    prompt: Optional[str] = None


class GPTAdCopyIn(BaseModel):
    """GPT 광고 문구 생성 요청 모델"""
    tenant_id: str
    tone_style: str  # Tone + Style
    product_description: str  # Describe Product
    store_information: str  # Store Information
    language: Optional[str] = "kor"  # 출력 언어 (kor, eng)


class RefinedAdCopyIn(BaseModel):
    """Refined Ad Copy 요청 모델"""
    tenant_id: str
    ad_copy_text: str
    available_fonts: Optional[list] = None  # 가용 폰트 리스트


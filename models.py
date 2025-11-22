
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
from typing import Optional, List


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
    min_overlay_width: Optional[float] = 0.5  # 최소 오버레이 너비 비율 (0-1)
    min_overlay_height: Optional[float] = 0.12  # 최소 오버레이 높이 비율 (0-1)
    max_proposals: Optional[int] = 10  # 최대 제안 개수
    max_forbidden_iou: Optional[float] = 0.05  # 최대 허용 금지 영역 IoU (0-1)


class ProposalOut(BaseModel):
    """제안 응답 모델"""
    proposal_id: str
    xywh: List[float]  # [x, y, width, height] (정규화된 좌표)
    source: str  # 제안 출처 (rule_top, grid_*, max_size_* 등)
    color: str  # 텍스트 색상 (hex)
    size: int  # 텍스트 크기
    score: Optional[float] = None  # 제안 점수
    occlusion_iou: Optional[float] = None  # 금지 영역과의 IoU
    area: Optional[float] = None  # 제안 영역 면적 (최대 크기 제안의 경우)


class PlannerOut(BaseModel):
    """Planner 응답 모델"""
    proposals: List[ProposalOut]  # 제안 리스트
    avoid: Optional[List[float]] = None  # 금지 영역 [x, y, width, height] (정규화된 좌표)
    min_overlay_width: Optional[float] = 0.5  # 최소 오버레이 너비 비율 (0-1)
    min_overlay_height: Optional[float] = 0.12  # 최소 오버레이 높이 비율 (0-1)
    max_proposals: Optional[int] = 10  # 최대 제안 개수
    max_forbidden_iou: Optional[float] = 0.05  # 최대 허용 금지 영역 IoU (0-1)


class ProposalOut(BaseModel):
    """제안 응답 모델"""
    proposal_id: str
    xywh: List[float]  # [x, y, width, height] (정규화된 좌표)
    source: str  # 제안 출처 (rule_top, grid_*, max_size_* 등)
    color: str  # 텍스트 색상 (hex)
    size: int  # 텍스트 크기
    score: Optional[float] = None  # 제안 점수
    occlusion_iou: Optional[float] = None  # 금지 영역과의 IoU
    area: Optional[float] = None  # 제안 영역 면적 (최대 크기 제안의 경우)


class PlannerOut(BaseModel):
    """Planner 응답 모델"""
    proposals: List[ProposalOut]  # 제안 리스트
    avoid: Optional[List[float]] = None  # 금지 영역 [x, y, width, height] (정규화된 좌표)


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


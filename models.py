
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
# updated_at: 2025-11-24    
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
    job_id: str  # 기존 job의 ID (업데이트할 job)
    tenant_id: str
    asset_url: Optional[str] = None  # Optional: job_inputs에서 가져올 수 있으면 생략 가능
    model: Optional[str] = "forbidden"


class DetectOut(BaseModel):
    """YOLO 감지 응답 모델 (DB ID 포함)"""
    job_id: str  # UUID 문자열
    detection_ids: List[str]  # UUID 문자열 리스트 (detections 테이블에 저장된 detection_id들)
    boxes: List[List[float]]  # 감지된 박스 리스트 (xyxy 형식)
    model: str  # 사용된 모델 이름
    confidences: List[float]  # 신뢰도 리스트
    classes: List[int]  # 클래스 ID 리스트
    labels: List[str]  # 라벨 리스트
    areas: List[float]  # 영역 면적 리스트
    widths: List[float]  # 너비 리스트
    heights: List[float]  # 높이 리스트
    forbidden_mask_url: Optional[str] = None  # 금지 영역 마스크 URL
    detections: List[dict] = []  # JSON 형식 감지 결과


class PlannerIn(BaseModel):
    """Planner 요청 모델"""
    job_id: str  # 기존 job의 ID (DB에서 detections를 가져올 job)
    tenant_id: str
    asset_url: Optional[str] = None  # Optional: job_inputs에서 가져올 수 있으면 생략 가능
    detections: Optional[dict] = None  # Optional: DB에서 가져올 수 있으면 생략 가능 (하위 호환성 유지)
    min_overlay_width: Optional[float] = 0.5  # 최소 오버레이 너비 비율 (0-1)
    min_overlay_height: Optional[float] = 0.12  # 최소 오버레이 높이 비율 (0-1)
    max_proposals: Optional[int] = 10  # 최대 제안 개수
    max_forbidden_iou: Optional[float] = 0.01  # 최대 허용 금지 영역 IoU (0-1) - 겹치지 않도록 엄격하게 (기존: 0.05)


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
    max_forbidden_iou: Optional[float] = 0.01  # 최대 허용 금지 영역 IoU (0-1) - 겹치지 않도록 엄격하게 (기존: 0.05)


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
    job_id: str  # 기존 job의 ID (업데이트할 job)
    tenant_id: str
    variant_asset_url: Optional[str] = None  # Optional: job_inputs에서 가져올 수 있으면 생략 가능
    proposal_id: Optional[str] = None
    text: str
    x_align: str = "center"
    y_align: str = "top"
    text_size: Optional[int] = None  # None이면 동적 폰트 크기 조정 사용
    overlay_color: Optional[str] = None  # "00000080"
    text_color: Optional[str] = "ffffffff"
    margin: Optional[str] = "8px"


class OverlayOut(BaseModel):
    """Overlay 응답 모델 (DB ID 포함)"""
    job_id: str  # UUID 문자열
    overlay_id: Optional[str] = None  # UUID 문자열 (overlay_layouts 테이블에 저장된 경우)
    render: dict  # 기존 render 메타데이터


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
    job_id: str  # 기존 job의 ID (업데이트할 job)
    tenant_id: str
    asset_url: Optional[str] = None  # Optional: job_inputs에서 가져올 수 있으면 생략 가능
    ad_copy_text: Optional[str] = None  # Optional: job_inputs에서 가져올 수 있으면 생략 가능
    prompt: Optional[str] = None


class FontRecommendation(BaseModel):
    """폰트 추천 모델"""
    font_style: Optional[str] = None  # "serif", "sans-serif", "bold", "italic"
    font_size_category: Optional[str] = None  # "small", "medium", "large"
    font_color_hex: Optional[str] = None  # hex color code (예: "FFFFFF")
    reasoning: Optional[str] = None  # 추천 이유


class LLaVaStage1Out(BaseModel):
    """LLaVa Stage 1 Validation 응답 모델 (DB ID 포함)"""
    job_id: str  # UUID 문자열
    vlm_trace_id: str  # UUID 문자열
    is_valid: bool
    image_quality_ok: bool
    relevance_score: float
    analysis: str
    issues: List[str]
    recommendations: List[str]
    font_recommendation: Optional[FontRecommendation] = None  # 폰트 추천 정보


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


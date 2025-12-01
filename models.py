
"""Pydantic 모델 정의"""
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-28   
# author: LEEYH205
# description: Pydantic models
# version: 1.1.0
# status: development
# tags: pydantic
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class DetectIn(BaseModel):
    """YOLO 감지 요청 모델"""
    job_variants_id: str  # 필수: Job Variant ID
    job_id: str  # 기존 job의 ID (업데이트할 job, 호환성 유지)
    tenant_id: str
    asset_url: Optional[str] = None  # Optional: jobs_variants.img_asset_id에서 가져올 수 있으면 생략 가능
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
    job_variants_id: str  # 필수: Job Variant ID
    job_id: str  # 기존 job의 ID (DB에서 detections를 가져올 job, 호환성 유지)
    tenant_id: str
    asset_url: Optional[str] = None  # Optional: jobs_variants.img_asset_id에서 가져올 수 있으면 생략 가능
    detections: Optional[dict] = None  # Optional: DB에서 가져올 수 있으면 생략 가능 (하위 호환성 유지)
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
    job_variants_id: str  # 필수: Job Variant ID
    job_id: str  # 기존 job의 ID (업데이트할 job, 호환성 유지)
    tenant_id: str
    variant_asset_url: Optional[str] = None  # Optional: jobs_variants.img_asset_id에서 가져올 수 있으면 생략 가능
    proposal_id: Optional[str] = None
    text: str
    x_align: str = "center"
    y_align: str = "top"
    text_size: Optional[int] = None  # None이면 동적 폰트 크기 조정 사용
    overlay_color: Optional[str] = None  # "00000080"
    text_color: Optional[str] = "ffffffff"
    margin: Optional[str] = "8px"
    font_name: Optional[str] = None  # 강제로 사용할 폰트 이름 (예: "Gmarket Sans", "Pretendard GOV", "Nanum Gothic", "Baemin Dohyeon")


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
    job_variants_id: str  # 필수: Job Variant ID
    job_id: str  # 기존 job의 ID (업데이트할 job, 호환성 유지)
    tenant_id: str
    overlay_id: Optional[str] = None  # Optional: overlay_layouts에서 render_asset_url을 가져올 수 있으면 생략 가능
    render_asset_url: Optional[str] = None  # Optional: overlay_id가 있으면 생략 가능


class LLaVaStage1In(BaseModel):
    """LLaVa Stage 1 Validation 요청 모델"""
    job_variants_id: str  # 필수: Job Variant ID
    job_id: str  # 기존 job의 ID (업데이트할 job, 호환성 유지)
    tenant_id: str
    asset_url: Optional[str] = None  # Optional: jobs_variants.img_asset_id에서 가져올 수 있으면 생략 가능
    ad_copy_text: Optional[str] = None  # Optional: job_inputs에서 가져올 수 있으면 생략 가능
    prompt: Optional[str] = None


class FontRecommendation(BaseModel):
    """폰트 추천 모델"""
    font_style: Optional[str] = None  # "serif", "sans-serif", "bold", "italic"
    font_name: Optional[str] = None  # 구체적인 폰트 이름 (예: "Pretendard GOV", "Gmarket Sans", "Nanum Gothic", "Nanum Myeongjo", "Baemin Dohyeon", "Baemin Euljiro")
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


class JudgeOut(BaseModel):
    """Judge 응답 모델 (DB ID 포함)"""
    job_id: str  # UUID 문자열
    vlm_trace_id: str  # UUID 문자열
    on_brief: bool  # brief 준수 여부
    occlusion: bool  # 가림 여부 (True면 가림 있음)
    contrast_ok: bool  # 대비 적절성
    cta_present: bool  # CTA 존재 여부
    analysis: str  # LLaVA 분석 결과 텍스트
    issues: List[str]  # 발견된 이슈 목록


class OCREvalIn(BaseModel):
    """OCR 평가 요청 모델"""
    job_variants_id: str  # 필수: Job Variant ID
    job_id: str  # 기존 job의 ID (호환성 유지)
    tenant_id: str
    overlay_id: str  # overlay_layouts에서 텍스트와 이미지 URL 조회


class OCREvalOut(BaseModel):
    """OCR 평가 응답 모델 (DB ID 포함)"""
    job_id: str  # UUID 문자열
    evaluation_id: str  # UUID 문자열
    overlay_id: str  # UUID 문자열
    ocr_confidence: float  # OCR 신뢰도 (0.0-1.0)
    ocr_accuracy: float  # OCR 정확도 (0.0-1.0)
    character_match_rate: float  # 문자 일치율 (0.0-1.0)
    recognized_text: str  # OCR로 인식된 텍스트
    original_text: str  # 원본 텍스트


class ReadabilityEvalIn(BaseModel):
    """가독성 평가 요청 모델"""
    job_variants_id: str  # 필수: Job Variant ID
    job_id: str  # 기존 job의 ID (호환성 유지)
    tenant_id: str
    overlay_id: str  # overlay_layouts에서 색상 정보 조회


class ReadabilityEvalOut(BaseModel):
    """가독성 평가 응답 모델 (DB ID 포함)"""
    job_id: str  # UUID 문자열
    evaluation_id: str  # UUID 문자열
    overlay_id: str  # UUID 문자열
    contrast_ratio: float  # 대비 비율
    wcag_aa_compliant: bool  # WCAG AA 기준 충족
    wcag_aaa_compliant: bool  # WCAG AAA 기준 충족
    readability_score: float  # 가독성 점수 (0.0-1.0)


class IoUEvalIn(BaseModel):
    """IoU 평가 요청 모델"""
    job_variants_id: str  # 필수: Job Variant ID
    job_id: str  # 기존 job의 ID (호환성 유지)
    tenant_id: str
    overlay_id: str  # overlay_layouts에서 텍스트 영역 좌표 조회


class IoUEvalOut(BaseModel):
    """IoU 평가 응답 모델 (DB ID 포함)"""
    job_id: str  # UUID 문자열
    evaluation_id: str  # UUID 문자열
    overlay_id: str  # UUID 문자열
    iou_with_food: float  # 음식과의 IoU (0.0-1.0)
    max_iou_detection_id: Optional[str]  # 최대 IoU를 가진 detection ID
    overlap_detected: bool  # 겹침 감지 여부


class FullEvalIn(BaseModel):
    """통합 평가 요청 모델"""
    tenant_id: str
    overlay_id: str  # overlay_layouts에서 정보 조회
    render_asset_url: Optional[str] = None  # 하위 호환성 유지
    evaluation_types: Optional[List[str]] = None  # ['ocr', 'readability', 'iou'] - None이면 모두 실행


class FullEvalOut(BaseModel):
    """통합 평가 응답 모델"""
    tenant_id: str
    overlay_id: str
    render_asset_url: Optional[str] = None
    evaluations: Dict[str, Any]  # 각 평가 타입별 결과
    overall_score: float  # 종합 점수 (0.0-1.0)
    execution_time_ms: float  # 전체 실행 시간


class InstagramFeedIn(BaseModel):
    """인스타그램 피드 글 생성 요청 모델"""
    job_id: str  # 필수: Job ID
    tenant_id: str  # 필수: Tenant ID
    # 나머지 필드는 job_id를 통해 DB에서 자동 조회


class InstagramFeedOut(BaseModel):
    """인스타그램 피드 글 생성 응답 모델"""
    instagram_feed_id: str  # UUID 문자열
    tenant_id: str
    instagram_ad_copy: str  # 인스타그램 광고문구
    hashtags: str  # 해시태그 (예: "#태그1 #태그2 #태그3")
    prompt_used: str  # 사용된 프롬프트
    generated_at: str  # 생성 시간


class EngToKorIn(BaseModel):
    """영어 → 한글 변환 요청 모델"""
    job_id: str  # 필수: Job ID
    tenant_id: str  # 필수: Tenant ID


class EngToKorOut(BaseModel):
    """영어 → 한글 변환 응답 모델"""
    job_id: str  # UUID 문자열
    llm_trace_id: str  # UUID 문자열
    ad_copy_gen_id: str  # UUID 문자열
    ad_copy_kor: str  # 한글 광고문구
    status: str  # 'done' 또는 'failed'


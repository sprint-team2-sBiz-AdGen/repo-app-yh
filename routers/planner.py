
"""Planner 라우터"""
########################################################
# 텍스트 오버레이 위치 제안 API
# 
# 기능:
# - 금지 영역을 피한 최적의 위치 제안
# - 여러 위치 옵션 생성 (상단, 하단, 좌측, 우측)
# - YOLO 감지 결과 활용
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-21
# author: LEEYH205
# description: Planner logic
# version: 0.2.0
# status: development
# tags: planner
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter, HTTPException
from PIL import Image
from models import PlannerIn, PlannerOut, ProposalOut
from utils import abs_from_url
from services.planner_service import propose_overlay_positions
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/planner", tags=["planner"])


@router.post("", response_model=PlannerOut, summary="텍스트 오버레이 위치 제안")
def planner(body: PlannerIn):
    """
    이미지에 텍스트 오버레이를 배치할 최적의 위치를 제안합니다.
    
    ## 기능
    - 금지 영역(사람, 음식 등)을 피한 최적 위치 제안
    - 최대 10개의 다양한 위치 옵션 제공
    - 최대 크기 제안 포함 (금지 영역과 겹치지 않는 최대 영역)
    
    ## 요청 파라미터
    - `tenant_id`: 테넌트 ID
    - `asset_url`: 이미지 URL
    - `detections`: YOLO 감지 결과 (선택사항)
      - `boxes`: 감지된 객체의 바운딩 박스 리스트
      - `labels`: 객체 라벨 리스트
      - `forbidden_mask_url`: 금지 영역 마스크 이미지 URL (선택사항)
    - `min_overlay_width`: 최소 오버레이 너비 비율 (기본값: 0.5)
    - `min_overlay_height`: 최소 오버레이 높이 비율 (기본값: 0.12)
    - `max_proposals`: 최대 제안 개수 (기본값: 10)
    - `max_forbidden_iou`: 최대 허용 금지 영역 IoU (기본값: 0.05)
    
    ## 응답
    - `proposals`: 제안 리스트
      - `proposal_id`: 제안 고유 ID
      - `xywh`: [x, y, width, height] 정규화된 좌표 (0-1)
      - `source`: 제안 출처 (rule_top, grid_*, max_size_* 등)
      - `color`: 텍스트 색상 (hex)
      - `size`: 텍스트 크기
      - `score`: 제안 점수 (높을수록 우선순위 높음)
      - `occlusion_iou`: 금지 영역과의 IoU (0에 가까울수록 좋음)
    - `avoid`: 금지 영역 [x, y, width, height] (정규화된 좌표)
    
    ## 사용 예시
    
    ```json
    {
      "tenant_id": "test",
      "asset_url": "/assets/image.jpg",
      "detections": {
        "boxes": [[100, 200, 300, 400]],
        "labels": ["person"],
        "forbidden_mask_url": "/assets/forbidden_mask.png"
      },
      "max_proposals": 10
    }
    ```
    """
    try:
        # 이미지 로드
        try:
            im = Image.open(abs_from_url(body.asset_url))
        except Exception as e:
            logger.error(f"이미지 로드 실패: {e}")
            raise HTTPException(status_code=400, detail=f"이미지를 로드할 수 없습니다: {str(e)}")
        
        # 금지 영역 마스크 추출 (detections에 forbidden_mask_url이 있는 경우)
        forbidden_mask = None
        if body.detections and body.detections.get("forbidden_mask_url"):
            try:
                mask_url = body.detections["forbidden_mask_url"]
                forbidden_mask = Image.open(abs_from_url(mask_url))
                logger.info(f"금지 영역 마스크 로드: {mask_url}")
            except Exception as e:
                logger.warning(f"금지 영역 마스크 로드 실패: {e}")
                # 마스크 로드 실패해도 계속 진행 (boxes만 사용)
        
        # 위치 제안 생성
        try:
            result = propose_overlay_positions(
                image=im,
                detections=body.detections,
                forbidden_mask=forbidden_mask,
                min_overlay_width=body.min_overlay_width,
                min_overlay_height=body.min_overlay_height,
                max_proposals=body.max_proposals,
                max_forbidden_iou=body.max_forbidden_iou
            )
        except Exception as e:
            logger.error(f"위치 제안 생성 실패: {e}")
            raise HTTPException(status_code=500, detail=f"위치 제안 생성 중 오류가 발생했습니다: {str(e)}")
        
        # 응답 모델로 변환
        proposals = [
            ProposalOut(**prop) for prop in result.get("proposals", [])
        ]
        
        return PlannerOut(
            proposals=proposals,
            avoid=result.get("avoid")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Planner API 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")


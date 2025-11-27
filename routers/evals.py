
"""Evaluation 라우터"""
########################################################
# 통합 평가 API
# - 모든 정량 평가를 한 번에 실행
# - OCR, 가독성, IoU 평가 통합
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-26
# author: LEEYH205
# description: Integrated evaluation API
# version: 1.0.0
# status: production
# tags: evaluation
# dependencies: fastapi, pydantic, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
import json
import time
import logging
from typing import Optional, List, Dict, Any
from models import EvalIn, FullEvalIn, FullEvalOut
from database import get_db, Job, OverlayLayout, PlannerProposal, JobInput
import requests

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/evaluations", tags=["evaluations"])


def get_job_id_from_overlay_id(db: Session, overlay_id: str, tenant_id: str) -> Optional[str]:
    """
    overlay_id로부터 job_id 찾기
    
    Args:
        db: 데이터베이스 세션
        overlay_id: Overlay ID
        tenant_id: 테넌트 ID
    
    Returns:
        job_id (str) 또는 None
    """
    try:
        overlay_id_uuid = uuid.UUID(overlay_id)
    except ValueError:
        return None
    
    overlay = db.query(OverlayLayout).filter(OverlayLayout.overlay_id == overlay_id_uuid).first()
    if not overlay:
        return None
    
    # overlay와 연결된 job 찾기 (proposal_id를 통해)
    if overlay.proposal_id:
        proposal = db.query(PlannerProposal).filter(
            PlannerProposal.proposal_id == overlay.proposal_id
        ).first()
        if proposal:
            job_input = db.query(JobInput).filter(
                JobInput.img_asset_id == proposal.image_asset_id
            ).first()
            if job_input:
                job = db.query(Job).filter(Job.job_id == job_input.job_id).first()
                if job and job.tenant_id == tenant_id:
                    return str(job.job_id)
    
    return None


@router.post("/full", response_model=FullEvalOut)
def full_evaluation(body: FullEvalIn, db: Session = Depends(get_db)):
    """
    통합 평가: 모든 정량 평가를 한 번에 실행
    
    Args:
        body: FullEvalIn 모델
            - tenant_id: 테넌트 ID - 필수
            - render_asset_url: 렌더링된 이미지 URL (하위 호환성 유지)
            - overlay_id: Overlay ID - 필수
            - evaluation_types: 평가 타입 리스트 (None이면 모두 실행)
    
    Returns:
        FullEvalOut:
            - evaluations: 각 평가 타입별 결과
            - overall_score: 종합 점수 (0.0-1.0)
            - execution_time_ms: 전체 실행 시간
    """
    start_time = time.time()
    
    try:
        # overlay_id로부터 job_id 찾기
        job_id = get_job_id_from_overlay_id(db, body.overlay_id, body.tenant_id)
        if not job_id:
            logger.error(f"Job ID를 찾을 수 없습니다: overlay_id={body.overlay_id}, tenant_id={body.tenant_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Job ID를 찾을 수 없습니다. overlay_id={body.overlay_id}"
            )
        
        # 평가 타입 결정
        evaluation_types = body.evaluation_types or ['ocr', 'readability', 'iou']
        
        # 각 평가 실행
        evaluation_results = {}
        errors = {}
        
        # API URL (현재 서버의 기본 URL 사용)
        api_base_url = "http://localhost:8011"  # TODO: 환경 변수로 설정 가능하게
        
        # OCR 평가
        if 'ocr' in evaluation_types:
            try:
                ocr_response = requests.post(
                    f"{api_base_url}/api/yh/ocr/evaluate",
                    json={
                        "job_id": job_id,
                        "tenant_id": body.tenant_id,
                        "overlay_id": body.overlay_id
                    },
                    timeout=120  # OCR은 시간이 오래 걸릴 수 있음
                )
                ocr_response.raise_for_status()
                evaluation_results['ocr'] = ocr_response.json()
                logger.info("OCR 평가 완료")
            except Exception as e:
                logger.error(f"OCR 평가 실패: {e}", exc_info=True)
                errors['ocr'] = str(e)
                evaluation_results['ocr'] = None
        
        # 가독성 평가
        if 'readability' in evaluation_types:
            try:
                readability_response = requests.post(
                    f"{api_base_url}/api/yh/readability/evaluate",
                    json={
                        "job_id": job_id,
                        "tenant_id": body.tenant_id,
                        "overlay_id": body.overlay_id
                    },
                    timeout=30
                )
                readability_response.raise_for_status()
                evaluation_results['readability'] = readability_response.json()
                logger.info("가독성 평가 완료")
            except Exception as e:
                logger.error(f"가독성 평가 실패: {e}", exc_info=True)
                errors['readability'] = str(e)
                evaluation_results['readability'] = None
        
        # IoU 평가
        if 'iou' in evaluation_types:
            try:
                iou_response = requests.post(
                    f"{api_base_url}/api/yh/iou/evaluate",
                    json={
                        "job_id": job_id,
                        "tenant_id": body.tenant_id,
                        "overlay_id": body.overlay_id
                    },
                    timeout=30
                )
                iou_response.raise_for_status()
                evaluation_results['iou'] = iou_response.json()
                logger.info("IoU 평가 완료")
            except Exception as e:
                logger.error(f"IoU 평가 실패: {e}", exc_info=True)
                errors['iou'] = str(e)
                evaluation_results['iou'] = None
        
        # 종합 점수 계산
        scores = []
        
        # OCR 점수 (accuracy 사용)
        if evaluation_results.get('ocr'):
            ocr_accuracy = evaluation_results['ocr'].get('ocr_accuracy', 0.0)
            scores.append(ocr_accuracy)
        
        # 가독성 점수 (readability_score 사용)
        if evaluation_results.get('readability'):
            readability_score = evaluation_results['readability'].get('readability_score', 0.0)
            scores.append(readability_score)
        
        # IoU 점수 (1.0 - iou_with_food, 겹치지 않을수록 높은 점수)
        if evaluation_results.get('iou'):
            iou_with_food = evaluation_results['iou'].get('iou_with_food', 0.0)
            iou_score = 1.0 - min(1.0, iou_with_food)  # IoU가 낮을수록 높은 점수
            scores.append(iou_score)
        
        # 종합 점수 (평균)
        overall_score = sum(scores) / len(scores) if scores else 0.0
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        logger.info(f"통합 평가 완료: overall_score={overall_score:.3f}, execution_time_ms={execution_time_ms:.2f}")
        
        return FullEvalOut(
            tenant_id=body.tenant_id,
            render_asset_url=body.render_asset_url,
            overlay_id=body.overlay_id,
            evaluations=evaluation_results,
            overall_score=float(overall_score),
            execution_time_ms=float(execution_time_ms)
        )
        
    except Exception as e:
        logger.error(f"통합 평가 API 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")


@router.post("/evals")
def evals(body: EvalIn):
    """평가 메트릭 반환 (mock, 하위 호환성 유지)"""
    # mock metrics for wiring
    return {
        "ocr_conf": 0.90,
        "text_ratio": 0.12,
        "clip_score": 0.33,
        "iou_forbidden": 0.0,
        "gate_pass": True
    }



"""Overlay 라우터"""
########################################################
# Overlay API with DB Integration
# - 텍스트 오버레이 적용
# - DB에 결과 저장 (overlay_layouts)
# - job 상태 업데이트
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-28
# author: LEEYH205
# description: Overlay logic with DB integration
# version: 1.1.0
# status: production
# tags: overlay
# dependencies: fastapi, pydantic, PIL, sqlalchemy
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter, HTTPException, Depends
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
import json
import os
import random
import numpy as np
from typing import Tuple
from models import OverlayIn, OverlayOut
from utils import abs_from_url, save_asset, parse_hex_rgba
from database import get_db, Job, JobInput, ImageAsset, PlannerProposal, OverlayLayout, VLMTrace, JobVariant
from fonts import FONT_STYLE_MAP, FONT_NAME_MAP, FONT_SIZE_MAP
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/overlay", tags=["overlay"])


@router.post("", response_model=OverlayOut)
def overlay(body: OverlayIn, db: Session = Depends(get_db)):
    """
    이미지에 텍스트 오버레이 적용 (DB 연동)
    
    Args:
        body: OverlayIn 모델
            - job_id: 기존 job의 ID (업데이트할 job) - 필수
            - tenant_id: 테넌트 ID - 필수
            - variant_asset_url: 이미지 URL (Optional, job_inputs에서 가져올 수 있으면 생략 가능)
            - proposal_id: Planner proposal ID (Optional)
            - text: 오버레이할 텍스트
            - x_align, y_align: 정렬 방식
            - text_size: 텍스트 크기
            - overlay_color, text_color: 색상
            - margin: 마진
        
    Returns:
        OverlayOut:
            - job_id: str                  # 업데이트된 job 레코드 ID
            - overlay_id: Optional[str]    # 생성된 overlay_layout 레코드 ID
            - render: dict                 # 렌더링된 이미지 메타데이터
    """
    try:
        # Step 0: job_variants_id 및 job_id 검증
        try:
            job_variants_id = uuid.UUID(body.job_variants_id)
            job_id = uuid.UUID(body.job_id)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid UUID format: {str(e)}"
            )
        
        # job_variants 조회
        job_variant = db.query(JobVariant).filter(JobVariant.job_variants_id == job_variants_id).first()
        if not job_variant:
            logger.error(f"Job variant not found: job_variants_id={body.job_variants_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Job variant not found: {body.job_variants_id}"
            )
        
        # job 조회 및 검증
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            logger.error(f"Job not found: job_id={body.job_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Job not found: {body.job_id}"
            )
        
        # job_variant와 job의 job_id 일치 확인
        if job_variant.job_id != job_id:
            logger.error(f"Job variant job_id mismatch: job_variant.job_id={job_variant.job_id}, request.job_id={job_id}")
            raise HTTPException(
                status_code=400,
                detail=f"Job variant job_id mismatch"
            )
        
        if job.tenant_id != body.tenant_id:
            logger.error(f"Job tenant_id mismatch: job.tenant_id={job.tenant_id}, request.tenant_id={body.tenant_id}")
            raise HTTPException(
                status_code=400,
                detail=f"Job tenant_id mismatch"
            )
        
        # Step 0.5: job_variant 상태 확인 (current_step='planner', status='done'이어야 함)
        if job_variant.current_step != 'planner' or job_variant.status != 'done':
            logger.error(f"Job variant 상태가 overlay 실행 조건을 만족하지 않음: current_step={job_variant.current_step}, status={job_variant.status}")
            raise HTTPException(
                status_code=400,
                detail=f"Job variant 상태가 overlay 실행 조건을 만족하지 않습니다. current_step='planner', status='done'이어야 합니다. (현재: current_step='{job_variant.current_step}', status='{job_variant.status}')"
            )
        
        # Step 0.6: Overlay 시작 - job_variants 상태 업데이트 (current_step='overlay', status='running')
        db.execute(
            text("""
                UPDATE jobs_variants 
                SET status = 'running', 
                    current_step = 'overlay',
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_variants_id = :job_variants_id
            """),
            {"job_variants_id": job_variants_id}
        )
        db.flush()
        logger.info(f"Updated job_variant: {job_variants_id} - status=running, current_step=overlay")
        
        # Overlay 시작 시간 측정
        import time
        start_time = time.time()
        
        # Step 1: jobs_variants에서 이미지 URL 가져오기
        variant_asset_url = body.variant_asset_url
        if not variant_asset_url:
            image_asset_id = job_variant.img_asset_id
            if not image_asset_id:
                logger.error(f"Image asset ID not found in job_variant: job_variants_id={job_variants_id}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Image asset ID not found in job variant"
                )
            
            image_asset = db.query(ImageAsset).filter(ImageAsset.image_asset_id == image_asset_id).first()
            if not image_asset:
                logger.error(f"Image asset not found: image_asset_id={image_asset_id}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Image asset not found: {image_asset_id}"
                )
            
            variant_asset_url = image_asset.image_url
            logger.info(f"Found image asset from job_variant: {image_asset_id}, URL: {variant_asset_url}")
        
        # Step 2: 이미지 로드 및 오버레이 적용
        try:
            im = Image.open(abs_from_url(variant_asset_url)).convert("RGBA")
        except Exception as e:
            logger.error(f"이미지 로드 실패: {e}")
            raise HTTPException(status_code=400, detail=f"이미지를 로드할 수 없습니다: {str(e)}")
        
        w, h = im.size
        
        # proposal_id가 있으면 planner_proposals에서 정보 가져오기
        proposal_id_uuid = None
        x_ratio, y_ratio, width_ratio, height_ratio = None, None, None, None
        
        if body.proposal_id:
            try:
                proposal_id_uuid = uuid.UUID(body.proposal_id)
                proposal = db.query(PlannerProposal).filter(PlannerProposal.proposal_id == proposal_id_uuid).first()
                if proposal and proposal.layout:
                    layout = proposal.layout
                    if isinstance(layout, dict) and layout.get("proposals"):
                        proposals_list = layout["proposals"]
                        if proposals_list:
                            # 위치 다양성을 고려한 proposal 선택
                            best_proposal = _select_best_proposal_with_diversity(proposals_list, logger)
                            
                            if best_proposal and "xywh" in best_proposal:
                                xywh = best_proposal["xywh"]  # [x, y, width, height] 정규화된 좌표
                                x_ratio, y_ratio, width_ratio, height_ratio = xywh
                                x, y, pw, ph = (int(w * x_ratio), int(h * y_ratio), int(w * width_ratio), int(h * height_ratio))
                                print(f"[위치 선택] 최적 proposal 선택: x={x}, y={y}, w={pw}, h={ph}, source={best_proposal.get('source', 'N/A')}, score={best_proposal.get('score', 'N/A')}")
                                logger.info(f"Using best proposal layout: x={x}, y={y}, w={pw}, h={ph}, source={best_proposal.get('source')}, score={best_proposal.get('score')}")
                            else:
                                logger.warning(f"Best proposal has no xywh, using default layout")
                                proposal_id_uuid = None
                                x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
                        else:
                            logger.warning(f"Proposal layout has no proposals, using default layout")
                            proposal_id_uuid = None
                            x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
                    else:
                        logger.warning(f"Proposal layout is invalid, using default layout")
                        proposal_id_uuid = None
                        x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
                else:
                    logger.warning(f"Proposal not found or has no layout: proposal_id={body.proposal_id}, using default layout")
                    proposal_id_uuid = None
                    x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
            except ValueError:
                logger.warning(f"Invalid proposal_id format: {body.proposal_id}, using default layout")
                proposal_id_uuid = None
                x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
        else:
            # proposal_id가 없으면 job_id로 최신 proposal 찾기
            try:
                job_input = db.query(JobInput).filter(JobInput.job_id == job_id).first()
                if job_input and job_input.img_asset_id:
                    # 같은 image_asset_id를 가진 최신 proposal 찾기
                    latest_proposal = db.query(PlannerProposal).filter(
                        PlannerProposal.image_asset_id == job_input.img_asset_id
                    ).order_by(PlannerProposal.created_at.desc()).first()
                    
                    if latest_proposal and latest_proposal.layout:
                        layout = latest_proposal.layout
                        if isinstance(layout, dict) and layout.get("proposals"):
                            proposals_list = layout["proposals"]
                            if proposals_list:
                                # 위치 다양성을 고려한 proposal 선택
                                best_proposal = _select_best_proposal_with_diversity(proposals_list, logger)
                                
                                if best_proposal and "xywh" in best_proposal:
                                    xywh = best_proposal["xywh"]
                                    x_ratio, y_ratio, width_ratio, height_ratio = xywh
                                    x, y, pw, ph = (int(w * x_ratio), int(h * y_ratio), int(w * width_ratio), int(h * height_ratio))
                                    proposal_id_uuid = latest_proposal.proposal_id
                                    print(f"[위치 선택] job_id로 최신 proposal 자동 선택: x={x}, y={y}, w={pw}, h={ph}, source={best_proposal.get('source', 'N/A')}")
                                    logger.info(f"Auto-selected latest proposal from job_id: x={x}, y={y}, w={pw}, h={ph}, proposal_id={proposal_id_uuid}")
                                else:
                                    x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
                                    x_ratio, y_ratio, width_ratio, height_ratio = 0.1, 0.05, 0.8, 0.18
                            else:
                                x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
                                x_ratio, y_ratio, width_ratio, height_ratio = 0.1, 0.05, 0.8, 0.18
                        else:
                            x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
                            x_ratio, y_ratio, width_ratio, height_ratio = 0.1, 0.05, 0.8, 0.18
                    else:
                        x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
                        x_ratio, y_ratio, width_ratio, height_ratio = 0.1, 0.05, 0.8, 0.18
                else:
                    x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
                    x_ratio, y_ratio, width_ratio, height_ratio = 0.1, 0.05, 0.8, 0.18
            except Exception as e:
                logger.warning(f"Failed to auto-select proposal from job_id: {e}, using default layout")
                x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
                x_ratio, y_ratio, width_ratio, height_ratio = 0.1, 0.05, 0.8, 0.18
        
        # overlay rect (배경 색상)
        overlay_color_hex = body.overlay_color
        logger.info(f"[Overlay 배경] 요청 파라미터: {overlay_color_hex}")
        
        # LLaVA 추천이 있으면 overlay_color도 추천 받을 수 있도록 (향후 확장 가능)
        # 현재는 요청 파라미터만 사용
        if overlay_color_hex:
            logger.info(f"[Overlay 배경] 요청 파라미터 사용: {overlay_color_hex}")
        else:
            logger.info(f"[Overlay 배경] 배경 색상 없음 (투명)")
        
        ol_color = parse_hex_rgba(overlay_color_hex, (0, 0, 0, 0))
        if ol_color[3] > 0:
            logger.info(f"[Overlay 배경] 배경 적용: RGBA={ol_color}")
            over = Image.new("RGBA", (pw, ph), ol_color)
            im.alpha_composite(over, dest=(x, y))
        else:
            logger.info(f"[Overlay 배경] 배경 없음 (투명)")
        
        # draw text
        draw = ImageDraw.Draw(im)
        
        # 패딩 적용 (old/overlay.py의 _apply_padding 로직)
        padding_ratio = 0.08
        pad_x = int(pw * padding_ratio)
        pad_y = int(ph * padding_ratio)
        padded_bbox = (
            max(0, x + pad_x),
            max(0, y + pad_y),
            min(w, x + pw - pad_x),
            min(h, y + ph - pad_y)
        )
        
        # 사용 가능한 영역 계산
        available_width = padded_bbox[2] - padded_bbox[0]
        available_height = padded_bbox[3] - padded_bbox[1]
        
        # Step 2.5: LLaVA 폰트 추천 조회 (vlm_traces에서)
        font_recommendation = None
        print(f"[폰트 추천 조회] job_id={job_id}에서 LLaVA 폰트 추천 조회 시작")
        logger.info(f"[폰트 추천 조회] job_id={job_id}에서 LLaVA 폰트 추천 조회 시작")
        try:
            vlm_trace = db.query(VLMTrace).filter(
                VLMTrace.job_id == job_id,
                VLMTrace.provider == 'llava',
                VLMTrace.operation_type == 'analyze'
            ).first()
            
            if vlm_trace:
                print(f"[폰트 추천 조회] vlm_trace 발견: vlm_trace_id={vlm_trace.vlm_trace_id}, response 존재={vlm_trace.response is not None}")
                logger.info(f"[폰트 추천 조회] vlm_trace 발견: vlm_trace_id={vlm_trace.vlm_trace_id}, response 존재={vlm_trace.response is not None}")
                if vlm_trace.response:
                    print(f"[폰트 추천 조회] response 타입: {type(vlm_trace.response)}, response 키: {list(vlm_trace.response.keys()) if isinstance(vlm_trace.response, dict) else 'N/A'}")
                    logger.info(f"[폰트 추천 조회] response 타입: {type(vlm_trace.response)}, response 키: {list(vlm_trace.response.keys()) if isinstance(vlm_trace.response, dict) else 'N/A'}")
                    font_recommendation = vlm_trace.response.get('font_recommendation')
                    if font_recommendation:
                        print(f"[폰트 추천 조회] ✓ 폰트 추천 발견: {font_recommendation}")
                        logger.info(f"[폰트 추천 조회] ✓ 폰트 추천 발견: {font_recommendation}")
                    else:
                        print(f"[폰트 추천 조회] ⚠ response에 'font_recommendation' 키가 없습니다. response 내용: {vlm_trace.response}")
                        logger.warning(f"[폰트 추천 조회] ⚠ response에 'font_recommendation' 키가 없습니다. response 내용: {vlm_trace.response}")
                else:
                    print(f"[폰트 추천 조회] ⚠ vlm_trace.response가 None입니다")
                    logger.warning(f"[폰트 추천 조회] ⚠ vlm_trace.response가 None입니다")
            else:
                print(f"[폰트 추천 조회] ⚠ vlm_trace를 찾을 수 없습니다 (job_id={job_id}, provider='llava', operation_type='analyze')")
                logger.warning(f"[폰트 추천 조회] ⚠ vlm_trace를 찾을 수 없습니다 (job_id={job_id}, provider='llava', operation_type='analyze')")
        except Exception as e:
            print(f"[폰트 추천 조회] ❌ vlm_traces 조회 중 오류 발생: {e}")
            logger.error(f"[폰트 추천 조회] ❌ vlm_traces 조회 중 오류 발생: {e}", exc_info=True)
        
        # 폰트 매핑은 fonts.py에서 import하여 사용
        
        # 한글 텍스트 감지
        import re
        has_korean = False
        if body.text:
            korean_pattern = re.compile(r'[가-힣]')
            has_korean = bool(korean_pattern.search(body.text))
        
        # 폰트 경로 선택: LLaVA 추천 폰트를 직접 사용 (우선순위 없음)
        font_style = None
        font_name = None
        
        # 요청 파라미터에서 font_name 확인
        if body.font_name:
            font_name = body.font_name
            logger.info(f"[폰트 추천] 요청 파라미터에서 font_name 지정: {font_name}")
        elif font_recommendation:
            # LLaVA 추천 폰트 사용 (우선순위 없음, 추천하는 폰트를 직접 사용)
            font_name = font_recommendation.get('font_name')
            font_style = font_recommendation.get('font_style')
            logger.info(f"[폰트 추천] LLaVA 추천: font_name={font_name}, font_style={font_style}")
            
            # 한글 텍스트인데 font_name이 없으면 경고 및 기본 한글 폰트 사용
            if has_korean and not font_name:
                logger.warning(f"[폰트 추천] ⚠️ 한글 텍스트인데 LLaVA가 font_name을 추천하지 않음. 기본 한글 폰트 사용: 'Gmarket Sans'")
                font_name = 'Gmarket Sans'
                font_style = 'sans-serif'
        else:
            # LLaVA 추천이 없을 때
            if has_korean:
                logger.warning(f"[폰트 추천] ⚠️ 한글 텍스트인데 LLaVA 추천이 없음. 기본 한글 폰트 사용: 'Gmarket Sans'")
                font_name = 'Gmarket Sans'
                font_style = 'sans-serif'
            else:
                logger.info(f"[폰트 추천] LLaVA 추천 없음, 기본값 사용")
        
        # LLaVA가 추천한 폰트 이름을 직접 사용 (우선순위 없음)
        font_paths = None
        if font_name:
            font_name_lower = font_name.lower().strip()
            # 정확한 매칭 시도
            if font_name_lower in FONT_NAME_MAP:
                recommended_path = FONT_NAME_MAP[font_name_lower]
                font_paths = [recommended_path]
                logger.info(f"[폰트 추천] ✓ LLaVA 추천 폰트 이름 사용: {font_name} -> {recommended_path}")
            else:
                # 부분 매칭 시도
                matched_path = None
                for name_key, path in FONT_NAME_MAP.items():
                    if name_key in font_name_lower or font_name_lower in name_key:
                        matched_path = path
                        break
                
                if matched_path:
                    font_paths = [matched_path]
                    logger.info(f"[폰트 추천] ✓ LLaVA 추천 폰트 이름 부분 매칭: {font_name} -> {matched_path}")
                else:
                    logger.warning(f"[폰트 추천] ⚠ LLaVA 추천 폰트 이름을 찾을 수 없음: {font_name}, font_style 기반으로 폴백")
        
        # font_name이 없거나 매칭 실패 시 font_style 기반으로 선택 (fallback, 우선순위 없음)
        if not font_paths:
            if font_style and font_style in FONT_STYLE_MAP:
                # font_style 기반으로 선택하되, 리스트 순서는 fallback용 (우선순위 아님)
                font_paths = FONT_STYLE_MAP[font_style]
                logger.info(f"[폰트 추천] LLaVA 추천 font_style 사용 (fallback): {font_style}, 폰트 경로 후보: {len(font_paths)}개")
            else:
                # 기본 폰트 경로 (sans-serif, fallback)
                font_paths = FONT_STYLE_MAP["sans-serif"]
                logger.info(f"[폰트 추천] 기본값 사용 (fallback): sans-serif, 폰트 경로 후보: {len(font_paths)}개")
        
        # 폰트 크기 범위 설정 (이전 코드처럼 넓은 범위 사용)
        # 이전 코드: min=28, max=96 (68px 범위)
        # LLaVA 추천은 가이드로만 사용 (교집합 대신)
        min_font_size = 28  # 이전 코드와 동일
        max_font_size = 96  # 이전 코드와 동일
        print(f"[폰트 크기 동적 조정] 이전 코드 방식: min={min_font_size}px, max={max_font_size}px (넓은 범위)")
        logger.info(f"[폰트 크기] 초기 범위 (이전 코드 방식): min={min_font_size}, max={max_font_size}")
        
        # LLaVA 추천 폰트 크기 카테고리 (가이드로만 사용, 범위 제한하지 않음)
        if font_recommendation and font_recommendation.get('font_size_category'):
            size_category = font_recommendation.get('font_size_category')
            print(f"[폰트 크기 동적 조정] LLaVA 추천 카테고리 (참고용): {size_category}")
            logger.info(f"[폰트 크기] LLaVA 추천 카테고리 (참고용): {size_category}")
            if size_category in FONT_SIZE_MAP:
                size_range = FONT_SIZE_MAP[size_category]
                print(f"[폰트 크기 동적 조정] LLaVA 추천 범위 (참고): {size_range[0]}-{size_range[1]}px")
                logger.info(f"[폰트 크기] LLaVA 추천 범위 (참고): {size_range}")
                # LLaVA 추천은 가이드로만 사용, 범위는 제한하지 않음
                # _fit_text 함수에서 넓은 범위(28-96px) 내에서 최적 크기 선택
            else:
                print(f"[폰트 크기 동적 조정] ⚠ 알 수 없는 카테고리: {size_category}, 기본 범위 사용")
                logger.warning(f"[폰트 크기] ⚠ 알 수 없는 카테고리: {size_category}, 기본 범위 사용")
        else:
            print(f"[폰트 크기 동적 조정] LLaVA 추천 없음, 기본 범위 사용")
            logger.info(f"[폰트 크기] LLaVA 추천 없음, 기본 범위 사용")
        
        # 사용자 지정 크기가 있으면 우선 적용 (하지만 넓은 범위 내에서)
        if body.text_size and body.text_size > 0:
            # 사용자가 지정한 크기를 최대값으로 사용하되, 넓은 범위(28-96px) 내에서만
            old_max = max_font_size
            max_font_size = max(min_font_size, min(max_font_size, body.text_size))
            print(f"[폰트 크기 동적 조정] 사용자 지정 크기 적용: {old_max}px → {max_font_size}px (요청값: {body.text_size}px)")
            logger.info(f"[폰트 크기] 사용자 지정 크기 적용: {old_max} → {max_font_size} (요청값: {body.text_size})")
        
        print(f"[폰트 크기 동적 조정] 최종 범위: {min_font_size}-{max_font_size}px (사용 가능 높이: {available_height}px)")
        logger.info(f"[폰트 크기] 최종 범위: min={min_font_size}, max={max_font_size}, available_height={available_height}")
        
        # 텍스트를 영역에 맞게 조정 (old/overlay.py의 _fit_text 로직)
        print(f"[폰트 적용] 텍스트 피팅 시작: 범위=[{min_font_size}, {max_font_size}]px, 영역={available_width}x{available_height}px")
        logger.info(f"[폰트 적용] 텍스트 피팅 시작: font_paths={font_paths}, size_range=[{min_font_size}, {max_font_size}]")
        font, wrapped_text = _fit_text(
            draw, body.text, padded_bbox, font_paths, min_font_size, max_font_size
        )
        final_font_size = font.size if hasattr(font, 'size') else 'N/A'
        print(f"[폰트 적용] ✓ 텍스트 피팅 완료: 최종 폰트 크기={final_font_size}px, 경로={getattr(font, 'path', '기본 폰트')}, 줄 수={len(wrapped_text.split(chr(10))) if wrapped_text else 0}")
        logger.info(f"[폰트 적용] ✓ 텍스트 피팅 완료: font_size={final_font_size}, font_path={getattr(font, 'path', 'N/A')}, wrapped_lines={len(wrapped_text.split(chr(10))) if wrapped_text else 0}")
        
        # 텍스트 색상 (우선순위: 요청 파라미터 > LLaVA 추천 > 기본값)
        text_color_hex = body.text_color
        logger.info(f"[폰트 색상] 요청 파라미터: {text_color_hex}")
        if not text_color_hex or text_color_hex == "ffffffff":  # 기본값인 경우
            logger.info(f"[폰트 색상] 기본값이므로 LLaVA 추천 확인")
            if font_recommendation and font_recommendation.get('font_color_hex'):
                recommended_color = font_recommendation.get('font_color_hex')
                text_color_hex = recommended_color
                logger.info(f"[폰트 색상] ✓ LLaVA 추천 적용: {text_color_hex}")
            else:
                logger.info(f"[폰트 색상] LLaVA 추천 없음, 기본값 유지: {text_color_hex}")
        else:
            logger.info(f"[폰트 색상] 요청 파라미터 사용 (우선순위 1): {text_color_hex}")
        
        tc = parse_hex_rgba(text_color_hex, (255, 255, 255, 255))
        logger.info(f"[폰트 색상] 최종 적용 색상 (RGBA): {tc}")
        
        # 텍스트 위치 계산 (중앙 정렬)
        x_center = (padded_bbox[0] + padded_bbox[2]) / 2
        y_center = (padded_bbox[1] + padded_bbox[3]) / 2
        
        # 최종 적용 값 요약 로그
        print(f"\n{'='*60}")
        print(f"[폰트 추천 최종 적용 요약]")
        print(f"  - LLaVA 추천 폰트 이름: {font_name or 'N/A'}")
        print(f"  - 폰트 스타일: {font_style or '기본값 (sans-serif)'}")
        print(f"  - 폰트 크기: {font.size if hasattr(font, 'size') else 'N/A'}px (범위: {min_font_size}-{max_font_size}, 영역 높이: {ph}px)")
        print(f"  - 폰트 경로: {getattr(font, 'path', '기본 폰트')}")
        print(f"  - 텍스트 색상: {text_color_hex} (RGBA: {tc})")
        print(f"  - Overlay 배경 색상: {overlay_color_hex or '투명'} (RGBA: {ol_color})")
        print(f"  - 영역 크기: {pw}x{ph}px (이미지: {w}x{h}px)")
        print(f"  - 사용 가능한 텍스트 영역: {available_width}x{available_height}px")
        print(f"  - LLaVA 추천 사용 여부: {'예' if font_recommendation else '아니오'}")
        if font_recommendation:
            print(f"  - LLaVA 추천 내용:")
            print(f"    * Font Name: {font_recommendation.get('font_name', 'N/A')}")
            print(f"    * Font Style: {font_recommendation.get('font_style', 'N/A')}")
            print(f"    * Font Size Category: {font_recommendation.get('font_size_category', 'N/A')}")
            print(f"    * Font Color: {font_recommendation.get('font_color_hex', 'N/A')}")
            print(f"    * Reasoning: {font_recommendation.get('reasoning', 'N/A')[:100]}...")
        print(f"{'='*60}\n")
        logger.info(f"[폰트 추천 최종 적용 요약]")
        logger.info(f"  - LLaVA 추천 폰트 이름: {font_name or 'N/A'}")
        logger.info(f"  - 폰트 스타일: {font_style or '기본값 (sans-serif)'}")
        logger.info(f"  - 폰트 크기: {font.size if hasattr(font, 'size') else 'N/A'}px (범위: {min_font_size}-{max_font_size}, 영역 높이: {ph}px)")
        logger.info(f"  - 폰트 경로: {getattr(font, 'path', '기본 폰트')}")
        logger.info(f"  - 텍스트 색상: {text_color_hex} (RGBA: {tc})")
        logger.info(f"  - Overlay 배경 색상: {overlay_color_hex or '투명'} (RGBA: {ol_color})")
        logger.info(f"  - 영역 크기: {pw}x{ph}px (이미지: {w}x{h}px)")
        logger.info(f"  - 사용 가능한 텍스트 영역: {available_width}x{available_height}px")
        logger.info(f"  - LLaVA 추천 사용 여부: {'예' if font_recommendation else '아니오'}")
        if font_recommendation:
            logger.info(f"  - LLaVA 추천 내용: {font_recommendation}")
        
        # multiline_text로 그리기 (old/overlay.py 방식)
        draw.multiline_text(
            (x_center, y_center),
            wrapped_text,
            font=font,
            fill=tc,
            anchor="mm",  # 중앙 정렬
            align="center",
            spacing=6,  # 줄 간격
        )
        
        # Step 3: 오버레이된 이미지 저장
        meta = save_asset(body.tenant_id, "final", im, ".png")
        
        # Overlay 완료 시간 측정
        latency_ms = (time.time() - start_time) * 1000
        
        # 최종 결과물 경로 로그 출력
        result_url = meta.get("url", "N/A")
        try:
            if result_url != "N/A" and result_url.startswith("/assets/"):
                from config import ASSETS_DIR
                result_path = os.path.join(ASSETS_DIR, result_url[len("/assets/"):])
            else:
                result_path = "N/A"
        except Exception as e:
            logger.warning(f"절대 경로 변환 실패: {e}")
            result_path = "N/A"
        result_filename = os.path.basename(result_path) if result_path != "N/A" else os.path.basename(result_url) if result_url != "N/A" else "N/A"
        print(f"\n{'='*60}")
        print(f"[최종 결과물 저장 완료]")
        print(f"  - Asset ID: {meta.get('asset_id', 'N/A')}")
        print(f"  - URL: {result_url}")
        print(f"  - 절대 경로: {result_path}")
        print(f"  - 파일명: {result_filename}")
        print(f"  - 이미지 크기: {meta.get('width', 'N/A')}x{meta.get('height', 'N/A')}")
        print(f"  - Latency: {latency_ms:.2f}ms")
        print(f"{'='*60}\n")
        logger.info(f"[최종 결과물 저장 완료] Asset ID: {meta.get('asset_id')}, URL: {result_url}, Path: {result_path}, Size: {meta.get('width')}x{meta.get('height')}, Latency: {latency_ms:.2f}ms")
        
        # Step 4: overlay_layouts 테이블에 결과 저장
        overlay_id = None
        try:
            overlay_id_uuid = uuid.uuid4()
            
            # layout JSONB 데이터 구성
            layout_data = {
                "text": body.text,
                "x_align": body.x_align,
                "y_align": body.y_align,
                "text_size": body.text_size,
                "overlay_color": body.overlay_color,
                "text_color": body.text_color,
                "margin": body.margin,
                "render": meta
            }
            
            # overlay_layouts에 저장 (raw SQL 사용, pk는 SERIAL로 자동 생성)
            db.execute(
                text("""
                    INSERT INTO overlay_layouts (
                        overlay_id, proposal_id, layout, x_ratio, y_ratio,
                        width_ratio, height_ratio, text_margin, latency_ms,
                        created_at, updated_at
                    ) VALUES (
                        :overlay_id, :proposal_id, CAST(:layout AS jsonb), :x_ratio, :y_ratio,
                        :width_ratio, :height_ratio, :text_margin, :latency_ms,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                """),
                {
                    "overlay_id": overlay_id_uuid,
                    "proposal_id": proposal_id_uuid,
                    "layout": json.dumps(layout_data),
                    "x_ratio": x_ratio if x_ratio is not None else 0.1,
                    "y_ratio": y_ratio if y_ratio is not None else 0.05,
                    "width_ratio": width_ratio if width_ratio is not None else 0.8,
                    "height_ratio": height_ratio if height_ratio is not None else 0.18,
                    "text_margin": body.margin,
                    "latency_ms": latency_ms
                }
            )
            db.commit()
            overlay_id = str(overlay_id_uuid)
            logger.info(f"Overlay layout saved to DB: overlay_id={overlay_id}, proposal_id={body.proposal_id}, latency_ms={latency_ms:.2f}")
        except Exception as e:
            logger.error(f"Failed to save overlay layout to DB: {e}")
            db.rollback()
            # DB 저장 실패해도 결과는 반환
            logger.warning(f"Overlay layout DB save failed but continuing: {e}")
        
        # Step 5: Overlay 완료 - job 상태 업데이트 (status='done')
        try:
            db.execute(
                text("""
                    UPDATE jobs_variants 
                    SET status = 'done', 
                        current_step = 'overlay',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_variants_id = :job_variants_id
                """),
                {"job_variants_id": job_variants_id}
            )
            db.commit()
            logger.info(f"Job variant 상태 업데이트: job_variants_id={job_variants_id}, status='done'")
        except Exception as e:
            logger.error(f"Job 상태 업데이트 실패: {e}")
            db.rollback()
            # 상태 업데이트 실패해도 결과는 반환
            logger.warning(f"Job 상태 업데이트 실패했지만 결과는 반환합니다: {e}")
        
        return OverlayOut(
            job_id=body.job_id,
            overlay_id=overlay_id,
            render=meta
        )
        
    except HTTPException:
        # HTTPException 발생 시 job 상태를 failed로 업데이트
        try:
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if job:
                db.execute(
                    text("""
                        UPDATE jobs_variants 
                        SET status = 'failed', 
                            updated_at = CURRENT_TIMESTAMP
                        WHERE job_variants_id = :job_variants_id
                    """),
                    {"job_variants_id": job_variants_id}
                )
                db.commit()
                logger.info(f"Job variant 상태 업데이트: job_variants_id={job_variants_id}, status='failed' (오류 발생)")
        except Exception as e:
            logger.error(f"Job 상태 업데이트 실패 (오류 처리 중): {e}")
            db.rollback()
        raise
    except Exception as e:
        # 기타 예외 발생 시 job 상태를 failed로 업데이트
        try:
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if job:
                db.execute(
                    text("""
                        UPDATE jobs_variants 
                        SET status = 'failed', 
                            updated_at = CURRENT_TIMESTAMP
                        WHERE job_variants_id = :job_variants_id
                    """),
                    {"job_variants_id": job_variants_id}
                )
                db.commit()
                logger.info(f"Job variant 상태 업데이트: job_variants_id={job_variants_id}, status='failed' (예외 발생)")
        except Exception as update_error:
            logger.error(f"Job 상태 업데이트 실패 (예외 처리 중): {update_error}")
            db.rollback()
        logger.error(f"Overlay API 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    bbox: Tuple[int, int, int, int],
    font_paths: list,
    min_font_size: int,
    max_font_size: int,
) -> Tuple[ImageFont.FreeTypeFont, str]:
    """
    텍스트를 bbox에 맞게 조정 (old/overlay.py의 _fit_text 로직)
    
    Args:
        draw: ImageDraw 객체
        text: 원본 텍스트
        bbox: (x0, y0, x1, y1) 형식의 박스
        font_paths: 폰트 경로 후보 리스트
        min_font_size: 최소 폰트 크기
        max_font_size: 최대 폰트 크기
    
    Returns:
        (font, wrapped_text): 최적의 폰트와 줄바꿈된 텍스트
    """
    max_width = bbox[2] - bbox[0]
    max_height = bbox[3] - bbox[1]
    
    # 큰 폰트부터 작은 폰트까지 시도
    logger.warning(f"Fitting text in bbox: max_width={max_width}, max_height={max_height}, font_size_range=[{min_font_size}, {max_font_size}]")
    
    for size in range(max_font_size, min_font_size - 1, -2):
        font = _load_font(font_paths, size)
        wrapped = _wrap_text(draw, text, font, max_width)
        
        # multiline_textbbox로 정확한 크기 계산
        try:
            bbox_text = draw.multiline_textbbox(
                (0, 0),
                wrapped,
                font=font,
                spacing=6,
                align="center",
            )
            text_width = bbox_text[2] - bbox_text[0]
            text_height = bbox_text[3] - bbox_text[1]
            
            logger.warning(f"Font size {size}: text_width={text_width}, text_height={text_height}, wrapped_lines={len(wrapped.split(chr(10)))}")
            
            if text_width <= max_width and text_height <= max_height:
                logger.warning(f"✓ Text fitted with font size {size}: width={text_width}/{max_width}, height={text_height}/{max_height}")
                return font, wrapped
        except AttributeError:
            # multiline_textbbox가 없는 경우 fallback
            try:
                # 각 줄의 크기를 개별적으로 계산
                lines = wrapped.split("\n")
                text_width = 0
                text_height = 0
                for line in lines:
                    try:
                        line_bbox = draw.textbbox((0, 0), line, font=font)
                        line_w = line_bbox[2] - line_bbox[0]
                        line_h = line_bbox[3] - line_bbox[1]
                    except AttributeError:
                        try:
                            line_w, line_h = draw.textsize(line, font=font)
                        except:
                            line_w = len(line) * size // 2
                            line_h = size
                    text_width = max(text_width, line_w)
                    text_height += line_h
                text_height += 6 * (len(lines) - 1)  # spacing
                
                if text_width <= max_width and text_height <= max_height:
                    logger.info(f"Text fitted with font size {size} (fallback): width={text_width}/{max_width}, height={text_height}/{max_height}")
                    return font, wrapped
            except Exception as e:
                logger.warning(f"Error calculating text size for font {size}: {e}")
                continue
    
    # 최소 폰트 크기로 강제 적용
    logger.warning(
        f"텍스트를 박스에 맞추지 못했습니다. 최소 폰트 크기 {min_font_size}로 강제 적용합니다."
    )
    font = _load_font(font_paths, min_font_size)
    wrapped = _wrap_text(draw, text, font, max_width)
    return font, wrapped


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> str:
    """
    텍스트를 단어 단위로 나누어서 max_width에 맞게 줄바꿈 (old/overlay.py의 _wrap_text 로직)
    
    Args:
        draw: ImageDraw 객체
        text: 원본 텍스트
        font: 폰트 객체
        max_width: 최대 너비
    
    Returns:
        줄바꿈된 텍스트
    """
    words = text.split()
    if not words:
        return text
    
    lines: list = []
    current: list = []
    
    for word in words:
        test_line = " ".join(current + [word]) if current else word
        
        # 텍스트 너비 계산
        try:
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
        except AttributeError:
            try:
                width, _ = draw.textsize(test_line, font=font)
            except:
                # 최후의 수단: 대략적인 계산
                width = len(test_line) * font.size // 2
        
        if width <= max_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    
    if current:
        lines.append(" ".join(current))
    
    return "\n".join(lines)


def _load_font(font_paths: list, size: int) -> ImageFont.FreeTypeFont:
    """
    여러 경로에서 폰트 로드 시도 (old/overlay.py의 _load_font 로직)
    
    Args:
        font_paths: 폰트 경로 후보 리스트
        size: 폰트 크기
    
    Returns:
        ImageFont 객체
    """
    for path in font_paths:
        try:
            font = ImageFont.truetype(path, size)
            logger.debug(f"Font loaded: {path} (size={size})")
            return font
        except Exception as exc:
            logger.debug(f"Failed to load font {path}: {exc}")
            continue
    
    logger.warning(f"사용 가능한 폰트를 찾지 못했습니다. 기본 폰트를 사용합니다. font_paths={font_paths}")
    return ImageFont.load_default()


def _select_best_proposal_with_diversity(proposals_list: list, logger) -> dict:
    """
    Score 기반 동적 그룹 선택 + softmax 샘플링으로 다양성을 확보한 proposal 선택
    
    Args:
        proposals_list: proposal 리스트
        logger: 로거 객체
    
    Returns:
        선택된 proposal 딕셔너리
    """
    print(f"[위치 선택 함수] 진입: proposals_list 개수={len(proposals_list) if proposals_list else 0}")
    logger.info(f"[위치 선택 함수] 진입: proposals_list 개수={len(proposals_list) if proposals_list else 0}")
    
    if not proposals_list:
        print(f"[위치 선택 함수] proposals_list가 비어있음")
        logger.warning(f"[위치 선택 함수] proposals_list가 비어있음")
        return None
    
    if len(proposals_list) == 1:
        print(f"[위치 선택 함수] proposal이 1개만 있음: source={proposals_list[0].get('source')}")
        logger.info(f"[위치 선택 함수] proposal이 1개만 있음: source={proposals_list[0].get('source')}")
        return proposals_list[0]
    
    # source를 기반으로 위치 그룹 분류
    def _get_position_group(source: str) -> str:
        """source에서 위치 그룹 추출"""
        if not source:
            return "unknown"
        source_lower = source.lower()
        if "top" in source_lower:
            return "top"
        elif "bottom" in source_lower:
            return "bottom"
        elif "left" in source_lower:
            return "left"
        elif "right" in source_lower:
            return "right"
        elif "center" in source_lower or "middle" in source_lower:
            return "center"
        elif "max_size" in source_lower:
            return "max_size"
        else:
            return "other"
    
    # 위치 그룹별로 proposal 분류
    position_groups = {}
    for prop in proposals_list:
        source = prop.get("source", "")
        group = _get_position_group(source)
        if group not in position_groups:
            position_groups[group] = []
        position_groups[group].append(prop)
    
    print(f"[위치 선택 함수] 위치 그룹 분류 결과: {list(position_groups.keys())}, 각 그룹별 개수: {[(k, len(v)) for k, v in position_groups.items()]}")
    logger.info(f"[위치 선택 함수] 위치 그룹 분류 결과: {list(position_groups.keys())}, 각 그룹별 개수: {[(k, len(v)) for k, v in position_groups.items()]}")
    
    # 각 그룹에서 최고 점수 proposal 선택 및 그룹 점수 계산
    group_best = {}
    group_scores = {}
    
    for group, props in position_groups.items():
        # score가 있는 proposal만 필터링
        scored_props = [p for p in props if p.get("score") is not None]
        if scored_props:
            best = max(scored_props, key=lambda p: p.get("score", 0))
            group_best[group] = best
            # 그룹 점수: 최고 점수 proposal의 score 사용
            group_scores[group] = best.get("score", 0.0)
        elif props:
            # score가 없으면 첫 번째 사용하고 기본 점수 부여
            group_best[group] = props[0]
            group_scores[group] = 0.5  # 기본 점수
        else:
            continue
    
    if not group_best:
        # 모든 proposal에 score가 없으면 첫 번째 사용
        logger.warning(f"[위치 선택] 모든 proposal에 score가 없음, 첫 번째 사용")
        return proposals_list[0]
    
    # Softmax 샘플링을 위한 점수 정규화
    # temperature 파라미터: 낮을수록 더 확실한 선택, 높을수록 더 다양성 확보
    temperature = 1.0  # 기본값 (조정 가능)
    
    groups = list(group_best.keys())
    scores = [group_scores[g] for g in groups]
    
    # Softmax 계산
    # 안정성을 위해 최대값을 빼서 계산 (overflow 방지)
    scores_array = np.array(scores)
    scores_normalized = scores_array - np.max(scores_array)  # overflow 방지
    exp_scores = np.exp(scores_normalized / temperature)
    probabilities = exp_scores / np.sum(exp_scores)
    
    print(f"[위치 선택 함수] 그룹별 점수: {dict(zip(groups, scores))}")
    print(f"[위치 선택 함수] 그룹별 선택 확률: {dict(zip(groups, probabilities))}")
    logger.info(f"[위치 선택 함수] 그룹별 점수: {dict(zip(groups, scores))}")
    logger.info(f"[위치 선택 함수] 그룹별 선택 확률: {dict(zip(groups, probabilities))}")
    
    # 확률 분포에 따라 그룹 샘플링
    selected_group = np.random.choice(groups, p=probabilities)
    selected = group_best[selected_group]
    
    logger.info(f"[위치 선택] Softmax 샘플링으로 그룹 '{selected_group}' 선택: source={selected.get('source')}, score={selected.get('score')}, xywh={selected.get('xywh')}, 확률={probabilities[groups.index(selected_group)]:.3f}")
    print(f"[위치 선택] Softmax 샘플링으로 그룹 '{selected_group}' 선택: source={selected.get('source')}, score={selected.get('score')}, xywh={selected.get('xywh')}, 확률={probabilities[groups.index(selected_group)]:.3f}")
    
    return selected


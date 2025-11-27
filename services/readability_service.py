
"""가독성 서비스"""
########################################################
# 가독성 평가 서비스
# - WCAG 2.1 대비 비율 계산
# - 텍스트와 배경 색상 대비 확인
########################################################
# created_at: 2025-11-26
# updated_at: 2025-11-26
# author: LEEYH205
# description: Readability service for contrast evaluation
# version: 1.0.0
# status: production
# tags: readability, contrast, wcag
# dependencies: PIL, numpy
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import logging
from typing import Dict, Any, Optional, Tuple
from PIL import Image
import numpy as np
from utils import parse_hex_rgba

logger = logging.getLogger(__name__)


def calculate_relative_luminance(r: int, g: int, b: int) -> float:
    """
    상대 휘도 계산 (WCAG 2.1)
    
    Args:
        r, g, b: RGB 값 (0-255)
    
    Returns:
        상대 휘도 (0.0-1.0)
    """
    def normalize(val: float) -> float:
        """색상 값을 정규화하고 감마 보정"""
        val = val / 255.0
        if val <= 0.03928:
            return val / 12.92
        else:
            return ((val + 0.055) / 1.055) ** 2.4
    
    r_norm = normalize(float(r))
    g_norm = normalize(float(g))
    b_norm = normalize(float(b))
    
    # WCAG 2.1 공식
    return 0.2126 * r_norm + 0.7152 * g_norm + 0.0722 * b_norm


def calculate_contrast_ratio(
    color1: Tuple[int, int, int],
    color2: Tuple[int, int, int]
) -> float:
    """
    대비 비율 계산 (WCAG 2.1)
    
    Args:
        color1, color2: RGB 튜플 (0-255)
    
    Returns:
        대비 비율 (1.0-21.0)
    """
    l1 = calculate_relative_luminance(*color1)
    l2 = calculate_relative_luminance(*color2)
    
    lighter = max(l1, l2)
    darker = min(l1, l2)
    
    if darker == 0:
        return 21.0  # 최대 대비
    
    return (lighter + 0.05) / (darker + 0.05)


def sample_background_color(
    image: Image.Image,
    text_region: Tuple[int, int, int, int]
) -> Tuple[int, int, int]:
    """
    텍스트 영역의 실제 배경 색상 샘플링
    
    Args:
        image: PIL Image 객체
        text_region: 텍스트 영역 (x, y, width, height)
    
    Returns:
        RGB 튜플 (0-255)
    """
    x, y, width, height = text_region
    img_w, img_h = image.size
    
    # 영역이 이미지 범위를 벗어나지 않도록 조정
    x = max(0, min(x, img_w - 1))
    y = max(0, min(y, img_h - 1))
    width = max(1, min(width, img_w - x))
    height = max(1, min(height, img_h - y))
    
    # 영역 자르기
    region = image.crop((x, y, x + width, y + height))
    
    # RGB로 변환
    if region.mode != "RGB":
        region = region.convert("RGB")
    
    # numpy 배열로 변환
    img_array = np.array(region)
    
    # 평균 색상 계산 (중앙 부분만 샘플링하여 텍스트 영향 최소화)
    center_x = width // 2
    center_y = height // 2
    sample_size = min(20, width // 4, height // 4)  # 샘플 크기
    
    x1 = max(0, center_x - sample_size // 2)
    y1 = max(0, center_y - sample_size // 2)
    x2 = min(width, center_x + sample_size // 2)
    y2 = min(height, center_y + sample_size // 2)
    
    sample = img_array[y1:y2, x1:x2]
    
    # 평균 RGB 값 계산
    avg_r = int(np.mean(sample[:, :, 0]))
    avg_g = int(np.mean(sample[:, :, 1]))
    avg_b = int(np.mean(sample[:, :, 2]))
    
    return (avg_r, avg_g, avg_b)


def evaluate_readability(
    text_color: str,  # hex color
    background_color: Optional[str] = None,  # hex color (overlay 배경)
    image: Optional[Image.Image] = None,  # 실제 이미지
    text_region: Optional[Tuple[int, int, int, int]] = None,  # 텍스트 영역
    text_size: Optional[int] = None  # 픽셀 단위
) -> Dict[str, Any]:
    """
    가독성 평가
    
    Args:
        text_color: 텍스트 색상 (hex, 예: "FFFFFF")
        background_color: 오버레이 배경 색상 (hex, 예: "000000") - Optional
        image: 실제 이미지 (Optional, 실제 배경 색상 샘플링용)
        text_region: 텍스트 영역 (x, y, width, height) - Optional, 실제 배경 색상 샘플링용
        text_size: 텍스트 크기 (픽셀) - None이면 일반 텍스트로 간주
    
    Returns:
        {
            "contrast_ratio": float,  # 대비 비율
            "wcag_aa_compliant": bool,  # WCAG AA 기준 충족
            "wcag_aaa_compliant": bool,  # WCAG AAA 기준 충족
            "readability_score": float,  # 가독성 점수 (0.0-1.0)
            "is_large_text": bool,  # 큰 텍스트 여부
            "text_color_rgb": Tuple[int, int, int],
            "background_color_rgb": Tuple[int, int, int]
        }
    """
    # 텍스트 색상 파싱
    text_rgba = parse_hex_rgba(text_color, (255, 255, 255, 255))
    text_rgb = text_rgba[:3]
    
    # 배경 색상 결정 (우선순위: 실제 이미지 샘플링 > overlay 배경 색상)
    background_rgb = None
    
    if image is not None and text_region is not None:
        # 실제 이미지에서 배경 색상 샘플링
        try:
            background_rgb = sample_background_color(image, text_region)
            logger.info(f"실제 이미지에서 배경 색상 샘플링: RGB={background_rgb}")
        except Exception as e:
            logger.warning(f"배경 색상 샘플링 실패: {e}, overlay 배경 색상 사용")
    
    if background_rgb is None and background_color:
        # overlay 배경 색상 사용
        bg_rgba = parse_hex_rgba(background_color, (0, 0, 0, 0))
        background_rgb = bg_rgba[:3]
        logger.info(f"Overlay 배경 색상 사용: RGB={background_rgb}")
    
    if background_rgb is None:
        # 기본값: 검은색
        background_rgb = (0, 0, 0)
        logger.warning("배경 색상을 찾을 수 없어 기본값(검은색) 사용")
    
    # 대비 비율 계산
    contrast_ratio = calculate_contrast_ratio(text_rgb, background_rgb)
    
    # 큰 텍스트 여부 판단
    # WCAG 기준: 18pt 이상 또는 14pt bold 이상
    is_large_text = False
    if text_size:
        # 픽셀을 포인트로 변환 (일반적으로 1pt = 1.33px)
        text_size_pt = text_size / 1.33
        is_large_text = text_size_pt >= 18
    
    # WCAG 기준 확인
    # AA 기준: 일반 텍스트 4.5:1, 큰 텍스트 3:1
    # AAA 기준: 일반 텍스트 7:1, 큰 텍스트 4.5:1
    wcag_aa_threshold = 3.0 if is_large_text else 4.5
    wcag_aaa_threshold = 4.5 if is_large_text else 7.0
    
    wcag_aa_compliant = contrast_ratio >= wcag_aa_threshold
    wcag_aaa_compliant = contrast_ratio >= wcag_aaa_threshold
    
    # 가독성 점수 계산 (0.0-1.0)
    # 대비 비율이 높을수록 높은 점수
    # 최소 기준(AA)을 만족하면 0.5, AAA를 만족하면 1.0
    if wcag_aaa_compliant:
        readability_score = 1.0
    elif wcag_aa_compliant:
        # AA와 AAA 사이의 점수 (0.5-1.0)
        ratio_range = wcag_aaa_threshold - wcag_aa_threshold
        if ratio_range > 0:
            score_range = contrast_ratio - wcag_aa_threshold
            readability_score = 0.5 + min(0.5, (score_range / ratio_range) * 0.5)
        else:
            readability_score = 0.5
    else:
        # AA 미만의 점수 (0.0-0.5)
        if wcag_aa_threshold > 0:
            readability_score = min(0.5, (contrast_ratio / wcag_aa_threshold) * 0.5)
        else:
            readability_score = 0.0
    
    logger.info(f"가독성 평가 완료: contrast_ratio={contrast_ratio:.2f}, AA={wcag_aa_compliant}, AAA={wcag_aaa_compliant}, score={readability_score:.3f}")
    
    return {
        "contrast_ratio": float(contrast_ratio),
        "wcag_aa_compliant": wcag_aa_compliant,
        "wcag_aaa_compliant": wcag_aaa_compliant,
        "readability_score": float(readability_score),
        "is_large_text": is_large_text,
        "text_color_rgb": text_rgb,
        "background_color_rgb": background_rgb
    }


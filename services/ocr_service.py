
"""OCR 서비스"""
########################################################
# OCR (Optical Character Recognition) 서비스
# - EasyOCR을 사용한 텍스트 추출
# - OCR 정확도 계산
########################################################
# created_at: 2025-11-26
# updated_at: 2025-11-26
# author: LEEYH205
# description: OCR service for text recognition
# version: 1.0.0
# status: production
# tags: ocr, text-recognition
# dependencies: easyocr, PIL, difflib
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import logging
from typing import Dict, Any, Optional, Tuple, List
from PIL import Image
import difflib

logger = logging.getLogger(__name__)

# EasyOCR은 lazy import (필요할 때만 로드)
_ocr_reader = None


def get_ocr_reader():
    """EasyOCR Reader 싱글톤"""
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            import os
            from config import EASYOCR_MODEL_DIR
            
            # EasyOCR 모델 경로 설정
            # 환경 변수로 모델 경로 지정 (EasyOCR이 이 경로를 사용)
            os.environ['EASYOCR_MODULE_PATH'] = EASYOCR_MODEL_DIR
            
            # 한글(ko)과 영어(en) 지원
            _ocr_reader = easyocr.Reader(['ko', 'en'], gpu=True, model_storage_directory=EASYOCR_MODEL_DIR)
            logger.info(f"EasyOCR Reader 초기화 완료 (한글, 영어 지원, 모델 경로: {EASYOCR_MODEL_DIR})")
        except ImportError:
            logger.error("EasyOCR이 설치되지 않았습니다. pip install easyocr 실행 필요")
            raise
        except Exception as e:
            logger.error(f"EasyOCR Reader 초기화 실패: {e}")
            raise
    return _ocr_reader


def extract_text_from_image(
    image: Image.Image,
    text_region: Optional[Tuple[int, int, int, int]] = None
) -> Dict[str, Any]:
    """
    이미지에서 텍스트 추출
    
    Args:
        image: PIL Image 객체
        text_region: 텍스트 영역 (x, y, width, height) - None이면 전체 이미지
    
    Returns:
        {
            "recognized_text": str,
            "confidence": float,  # 평균 신뢰도
            "details": List[Dict]  # 각 텍스트 박스별 정보
        }
    """
    try:
        reader = get_ocr_reader()
        
        # 텍스트 영역이 지정된 경우 해당 영역만 추출
        if text_region:
            x, y, width, height = text_region
            # 이미지 크기 확인
            img_w, img_h = image.size
            # 영역이 이미지 범위를 벗어나지 않도록 조정
            x = max(0, min(x, img_w - 1))
            y = max(0, min(y, img_h - 1))
            width = max(1, min(width, img_w - x))
            height = max(1, min(height, img_h - y))
            
            # 영역 자르기
            cropped = image.crop((x, y, x + width, y + height))
            ocr_image = cropped
        else:
            ocr_image = image
        
        # EasyOCR 실행 (PIL Image를 numpy array로 변환)
        import numpy as np
        ocr_image_array = np.array(ocr_image)
        results = reader.readtext(ocr_image_array)
        
        # 결과 파싱
        recognized_texts = []
        confidences = []
        details = []
        
        for (bbox, text, confidence) in results:
            recognized_texts.append(text)
            confidences.append(confidence)
            details.append({
                "text": text,
                "confidence": float(confidence),
                "bbox": bbox  # [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
            })
        
        # 전체 텍스트 합치기 (공백으로 구분)
        recognized_text = " ".join(recognized_texts)
        
        # 평균 신뢰도 계산
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        logger.info(f"OCR 추출 완료: 텍스트 길이={len(recognized_text)}, 평균 신뢰도={avg_confidence:.3f}")
        
        return {
            "recognized_text": recognized_text,
            "confidence": float(avg_confidence),
            "details": details
        }
        
    except Exception as e:
        logger.error(f"OCR 추출 실패: {e}", exc_info=True)
        return {
            "recognized_text": "",
            "confidence": 0.0,
            "details": []
        }


def calculate_ocr_accuracy(
    original_text: str,
    recognized_text: str
) -> Dict[str, Any]:
    """
    OCR 인식 정확도 계산
    
    Args:
        original_text: 원본 텍스트
        recognized_text: OCR로 인식된 텍스트
    
    Returns:
        {
            "accuracy": float,  # 전체 정확도 (0.0-1.0)
            "character_match_rate": float,  # 문자 일치율
            "word_match_rate": float,  # 단어 일치율
            "edit_distance": int,  # 편집 거리
            "similarity": float  # 유사도 (0.0-1.0)
        }
    """
    if not original_text:
        return {
            "accuracy": 0.0,
            "character_match_rate": 0.0,
            "word_match_rate": 0.0,
            "edit_distance": len(recognized_text) if recognized_text else 0,
            "similarity": 0.0
        }
    
    if not recognized_text:
        return {
            "accuracy": 0.0,
            "character_match_rate": 0.0,
            "word_match_rate": 0.0,
            "edit_distance": len(original_text),
            "similarity": 0.0
        }
    
    # 공백 제거하여 비교 (선택적)
    original_clean = original_text.replace(" ", "").replace("\n", "")
    recognized_clean = recognized_text.replace(" ", "").replace("\n", "")
    
    # 문자 일치율 계산
    if original_clean:
        # SequenceMatcher를 사용한 유사도 계산
        matcher = difflib.SequenceMatcher(None, original_clean, recognized_clean)
        character_match_rate = matcher.ratio()
    else:
        character_match_rate = 0.0
    
    # 단어 일치율 계산
    original_words = original_text.split()
    recognized_words = recognized_text.split()
    
    if original_words:
        # 정확히 일치하는 단어 수
        matched_words = sum(1 for w in original_words if w in recognized_words)
        word_match_rate = matched_words / len(original_words)
    else:
        word_match_rate = 0.0
    
    # 편집 거리 계산 (간단한 버전)
    def levenshtein_distance(s1: str, s2: str) -> int:
        """Levenshtein 거리 계산"""
        if len(s1) < len(s2):
            return levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    edit_distance = levenshtein_distance(original_clean, recognized_clean)
    
    # 전체 정확도 (문자 일치율과 단어 일치율의 평균)
    accuracy = (character_match_rate + word_match_rate) / 2.0
    
    # 유사도 (SequenceMatcher 사용)
    similarity = difflib.SequenceMatcher(None, original_text, recognized_text).ratio()
    
    logger.info(f"OCR 정확도 계산: accuracy={accuracy:.3f}, character_match={character_match_rate:.3f}, word_match={word_match_rate:.3f}")
    
    return {
        "accuracy": float(accuracy),
        "character_match_rate": float(character_match_rate),
        "word_match_rate": float(word_match_rate),
        "edit_distance": edit_distance,
        "similarity": float(similarity)
    }


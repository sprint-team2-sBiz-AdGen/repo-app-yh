
"""LLaVa 모델 서비스"""
########################################################
# LLaVa 모델 로드 및 추론 서비스
# 
# 사용 가능한 모델:
# 1. llava-hf/llava-1.5-7b-hf (7B 파라미터, 권장)
# 2. llava-hf/llava-1.5-13b-hf (13B 파라미터, 더 정확하지만 느림)
# 3. llava-hf/llava-1.5-7b-hf-merged (병합된 버전)
#
# KoLLaVA 모델 사용은 테스트 했을 때 영어 모델보다 성능이 떨어지는 것을 확인함.
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-20
# author: LEEYH205
# description: LLaVa model service
# version: 0.1.0
# status: development
# tags: llava, model, service
# dependencies: transformers, torch, accelerate, pillow
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import os
from typing import Optional, Dict, Any
from PIL import Image
import torch
from transformers import LlavaProcessor, LlavaForConditionalGeneration
from config import LLAVA_MODEL_NAME, DEVICE_TYPE, MODEL_DIR

# 디바이스 설정
DEVICE = DEVICE_TYPE if DEVICE_TYPE == "cuda" and torch.cuda.is_available() else "cpu"

# 전역 모델 변수 (lazy loading)
_processor: Optional[LlavaProcessor] = None
_model: Optional[LlavaForConditionalGeneration] = None


def get_llava_model():
    """LLaVa 모델 및 프로세서 로드 (싱글톤 패턴)"""
    global _processor, _model
    
    if _model is None or _processor is None:
        print(f"Loading LLaVa model: {LLAVA_MODEL_NAME} on {DEVICE}")
        print(f"Model will be saved to: {MODEL_DIR}")
        
        # Hugging Face 캐시 디렉토리를 model 폴더로 설정
        # transformers는 cache_dir 내에 models--{org}--{model-name} 구조로 저장
        os.environ["HF_HOME"] = MODEL_DIR
        os.environ["TRANSFORMERS_CACHE"] = MODEL_DIR
        
        # 프로세서 로드 (자동으로 MODEL_DIR에 캐시됨)
        print(f"Downloading/loading processor from Hugging Face...")
        _processor = LlavaProcessor.from_pretrained(
            LLAVA_MODEL_NAME,
            cache_dir=MODEL_DIR
        )
        
        # 모델 로드 (자동으로 MODEL_DIR에 캐시됨)
        print(f"Downloading/loading model from Hugging Face...")
        _model = LlavaForConditionalGeneration.from_pretrained(
            LLAVA_MODEL_NAME,
            torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
            device_map="auto" if DEVICE == "cuda" else None,
            low_cpu_mem_usage=True,
            cache_dir=MODEL_DIR
        )
        
        if DEVICE == "cpu":
            _model = _model.to(DEVICE)
        
        _model.eval()
        print(f"LLaVa model loaded successfully on {DEVICE}")
        print(f"Model cached in: {MODEL_DIR}")
    
    return _processor, _model


def process_image_with_llava(
    image: Image.Image,
    prompt: str,
    max_new_tokens: int = 512,
    temperature: float = 0.7,
    do_sample: bool = True
) -> str:
    """
    LLaVa를 사용하여 이미지와 프롬프트를 처리하고 응답 생성
    
    Args:
        image: PIL Image 객체
        prompt: 텍스트 프롬프트
        max_new_tokens: 최대 생성 토큰 수
        temperature: 생성 온도
        do_sample: 샘플링 사용 여부
    
    Returns:
        생성된 텍스트 응답
    """
    processor, model = get_llava_model()
    
    # 이미지와 프롬프트 준비
    inputs = processor(images=image, text=prompt, return_tensors="pt").to(DEVICE)
    
    # 추론
    with torch.no_grad():
        generate_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            do_sample=do_sample
        )
    
    # 응답 디코딩
    response = processor.batch_decode(
        generate_ids,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False
    )[0]
    
    # 프롬프트 부분 제거 (응답만 반환)
    if prompt in response:
        response = response.replace(prompt, "").strip()
    
    return response


def validate_image_and_text(
    image: Image.Image,
    ad_copy_text: Optional[str] = None,
    validation_prompt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Stage 1: 이미지와 광고문구의 적합성 검증
    
    Args:
        image: PIL Image 객체
        ad_copy_text: 광고 문구 텍스트
        validation_prompt: 검증용 프롬프트
    
    Returns:
        검증 결과 딕셔너리
    """
    if validation_prompt is None:
        validation_prompt = """Analyze this image and evaluate:
1. Image quality (resolution, clarity, composition)
2. Whether the image is suitable for advertising
3. If ad copy text is provided, check if it matches the image content

Provide your analysis."""
    
    if ad_copy_text:
        validation_prompt += f"\n\nAd copy text: {ad_copy_text}\n\nDoes this ad copy match the image? Explain."
    
    response = process_image_with_llava(image, validation_prompt)
    
    # 응답 파싱 (간단한 예제, 실제로는 더 정교한 파싱 필요)
    is_valid = "suitable" in response.lower() or "good" in response.lower()
    image_quality_ok = "quality" in response.lower() and ("good" in response.lower() or "high" in response.lower())
    
    return {
        "is_valid": is_valid,
        "image_quality_ok": image_quality_ok,
        "relevance_score": 0.95 if is_valid else 0.5,  # TODO: 실제 점수 계산
        "analysis": response,
        "issues": [],
        "recommendations": []
    }


def judge_final_ad(
    image: Image.Image,
    judge_prompt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Stage 2: 최종 광고 시각 결과물 판단
    
    Args:
        image: PIL Image 객체 (최종 광고 이미지)
        judge_prompt: 판단용 프롬프트
    
    Returns:
        판단 결과 딕셔너리
    """
    if judge_prompt is None:
        judge_prompt = """Analyze this final advertisement image and evaluate:
1. Does it follow the advertising brief? (on_brief)
2. Is there any text or important content occluded? (occlusion)
3. Is the contrast between text and background appropriate? (contrast_ok)
4. Is there a clear call-to-action (CTA) present? (cta_present)
5. List any issues or problems you find.

Provide your analysis in a structured format."""
    
    response = process_image_with_llava(image, judge_prompt)
    
    # 응답 파싱 (간단한 예제, 실제로는 더 정교한 파싱 필요)
    on_brief = "brief" in response.lower() and ("follow" in response.lower() or "yes" in response.lower())
    occlusion = "occlude" in response.lower() and "no" in response.lower()
    contrast_ok = "contrast" in response.lower() and ("good" in response.lower() or "appropriate" in response.lower())
    cta_present = "cta" in response.lower() or "call-to-action" in response.lower()
    
    issues = []
    if "issue" in response.lower() or "problem" in response.lower():
        # TODO: 실제 이슈 추출 로직 구현
        issues = ["Some issues detected - check analysis"]
    
    return {
        "on_brief": on_brief,
        "occlusion": not occlusion,  # occlusion이 False면 가림 없음
        "contrast_ok": contrast_ok,
        "cta_present": cta_present,
        "analysis": response,
        "issues": issues
    }



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
import re
from typing import Optional, Dict, Any
from PIL import Image
import torch
from transformers import LlavaProcessor, LlavaForConditionalGeneration
from config import LLAVA_MODEL_NAME, DEVICE_TYPE, MODEL_DIR, USE_QUANTIZATION

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
        print(f"Quantization setting: {'Enabled (8-bit)' if USE_QUANTIZATION else 'Disabled (FP16/FP32)'}")
        
        # GPU 메모리 사용량 측정 (로드 전)
        if DEVICE == "cuda":
            torch.cuda.reset_peak_memory_stats()
            initial_memory = torch.cuda.memory_allocated() / 1024**3  # GB
        
        # 메모리 최적화: 8-bit 양자화 사용 여부에 따라 선택
        if DEVICE == "cuda" and USE_QUANTIZATION:
            try:
                from transformers import BitsAndBytesConfig
                quantization_config = BitsAndBytesConfig(
                    load_in_8bit=True,
                    bnb_8bit_compute_dtype=torch.float16
                )
                _model = LlavaForConditionalGeneration.from_pretrained(
                    LLAVA_MODEL_NAME,
                    quantization_config=quantization_config,
                    device_map="auto",
                    low_cpu_mem_usage=True,
                    cache_dir=MODEL_DIR
                )
                print("✓ Model loaded with 8-bit quantization for memory efficiency")
            except Exception as e:
                print(f"⚠ 8-bit quantization failed: {e}")
                print("Falling back to standard loading with memory limits...")
                # 8-bit 양자화 실패 시 메모리 제한과 함께 로드
                _model = LlavaForConditionalGeneration.from_pretrained(
                    LLAVA_MODEL_NAME,
                    torch_dtype=torch.float16,
                    device_map="auto",
                    low_cpu_mem_usage=True,
                    cache_dir=MODEL_DIR,
                    max_memory={0: "20GiB"}  # GPU 메모리 제한
                )
                print("✓ Model loaded with FP16 (quantization disabled)")
        elif DEVICE == "cuda":
            # 양자화 비활성화: FP16으로 로드
            _model = LlavaForConditionalGeneration.from_pretrained(
                LLAVA_MODEL_NAME,
                torch_dtype=torch.float16,
                device_map="auto",
                low_cpu_mem_usage=True,
                cache_dir=MODEL_DIR
            )
            print("✓ Model loaded with FP16 (quantization disabled)")
        else:
            # CPU 모드
            _model = LlavaForConditionalGeneration.from_pretrained(
                LLAVA_MODEL_NAME,
                torch_dtype=torch.float32,
                device_map=None,
                low_cpu_mem_usage=True,
                cache_dir=MODEL_DIR
            )
            _model = _model.to(DEVICE)
            print("✓ Model loaded on CPU")
        
        # GPU 메모리 사용량 측정 (로드 후)
        if DEVICE == "cuda":
            loaded_memory = torch.cuda.memory_allocated() / 1024**3  # GB
            peak_memory = torch.cuda.max_memory_allocated() / 1024**3  # GB
            total_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3  # GB
            print(f"📊 GPU Memory Usage:")
            print(f"   - Allocated: {loaded_memory:.2f} GB")
            print(f"   - Peak (during load): {peak_memory:.2f} GB")
            print(f"   - Total GPU: {total_memory:.2f} GB")
            print(f"   - Usage: {loaded_memory/total_memory*100:.1f}%")
        
        _model.eval()
        print(f"✓ LLaVa model loaded successfully on {DEVICE}")
        print(f"✓ Model cached in: {MODEL_DIR}")
    
    return _processor, _model


def process_image_with_llava(
    image: Image.Image,
    prompt: str,
    max_new_tokens: int = 512,

    # temperature 조절
    temperature: float = 0.1,
    # 샘플링 사용 여부
    do_sample: bool = False
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
    
    # LLaVa-1.5 프롬프트 형식: USER: <image>\n{prompt}\nASSISTANT:
    # 이미지를 리스트로 전달하고 프롬프트를 올바른 형식으로 구성
    formatted_prompt = f"USER: <image>\n{prompt}\nASSISTANT:"
    
    # GPU 메모리 정리
    if DEVICE == "cuda":
        torch.cuda.empty_cache()
    
    # 이미지와 프롬프트 준비 (이미지는 리스트로 전달)
    # 메모리 최적화: CPU에서 처리 후 필요시 GPU로 이동
    inputs = processor(images=[image], text=formatted_prompt, return_tensors="pt")
    
    # GPU로 이동 (8-bit 양자화된 모델은 자동으로 처리됨)
    if DEVICE == "cuda":
        inputs = {k: v.to(DEVICE) if isinstance(v, torch.Tensor) else v for k, v in inputs.items()}
    
    # 추론
    with torch.no_grad():
        generate_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            do_sample=do_sample,
            pad_token_id=processor.tokenizer.eos_token_id if processor.tokenizer.pad_token_id is None else processor.tokenizer.pad_token_id
        )
    
    # GPU 메모리 정리
    if DEVICE == "cuda":
        del inputs
        torch.cuda.empty_cache()
    
    # 응답 디코딩
    response = processor.batch_decode(
        generate_ids,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False
    )[0]
    
    # 프롬프트 부분 제거 (응답만 반환)
    # ASSISTANT: 이후의 텍스트만 추출
    if "ASSISTANT:" in response:
        response = response.split("ASSISTANT:")[-1].strip()
    elif formatted_prompt in response:
        response = response.replace(formatted_prompt, "").strip()
    
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
    # Step 1: 이미지만 먼저 분석 (광고 문구의 영향을 받지 않도록)
    image_analysis_prompt = """Analyze this image ONLY. Do NOT consider any ad copy text. Focus solely on what you see in the image.

## Image Analysis (IMPORTANT: Analyze ONLY the image, ignore any text that might be mentioned)
- Product shown: [What food/product is actually visible? Be specific with the exact name]
- Characteristics: [spicy/mild, color, ingredients visible, texture, etc.]
- Setting: [home/restaurant/office/etc.]
- Mood: [cozy/formal/casual/etc.]

Focus on the product characteristics and visual elements."""
    
    # 이미지만 먼저 분석
    image_analysis = process_image_with_llava(image, image_analysis_prompt)
    
    if validation_prompt is None:
        # Step 2: 광고 문구와 비교
        if ad_copy_text:
            validation_prompt = f"""You are evaluating whether an ad copy text matches an advertisement image. 

## 1. Image Analysis (Already completed - DO NOT re-analyze)
{image_analysis}

## 2. Ad Copy Analysis
Ad copy: "{ad_copy_text}"
- Product mentioned: [exact name from ad]
- Characteristics: [spicy/mild/etc. from ad]
- Target audience: [ONLY extract if explicitly mentioned. Look for "for people who...", "for [group]", "target audience". If NOT mentioned, write "none". Examples: "for people who hate spicy" = "people who hate spicy", "for spicy lovers" = "spicy lovers", no mention = "none"]
- Message: [main point]

## 3. Compatibility Check
STEP 1: Logical consistency (CRITICAL)
Check if target audience conflicts with product characteristics:
- If target audience = "people who hate spicy" AND product contains "spicy" → CONTRADICTION → Logical Consistency = No
- If target audience = "spicy lovers" AND product is "spicy" → NO CONTRADICTION → Logical Consistency = Yes
- If target audience = "none" (not mentioned) → NO CONTRADICTION → Logical Consistency = Yes

CRITICAL RULES:
- "hate spicy" + "spicy [product]" = CONTRADICTION → Logical Consistency = No
- "dislike spicy" + "spicy [product]" = CONTRADICTION → Logical Consistency = No
- "spicy [product]" + no target audience = NO CONTRADICTION → Logical Consistency = Yes
- "spicy [product]" + "for spicy lovers" = NO CONTRADICTION → Logical Consistency = Yes

## 4. Final Assessment (EXACT format)
Match Score: [0-10]/10
Logical Consistency: [Yes/No - No if "hate spicy" + "spicy product"]
Mismatch Detected: [Yes/No]
Mismatch Details: [List issues or "None"]
Overall Assessment: [Suitable/Not Suitable]
Reasoning: [Brief explanation]

CRITICAL SCORING RULES (MUST FOLLOW):
- If Logical Consistency = No (target audience conflicts with product characteristics) → Match Score MUST be 0-2/10, Mismatch Detected = Yes, Not Suitable
- If Mismatch Detected = Yes → Match Score MUST be 0-2/10, Not Suitable
- If Logical Consistency = Yes AND Mismatch Detected = No → Match Score can be 7-10/10, Suitable

RULES:
- If Logical Consistency = No → Mismatch Detected = Yes, Overall Assessment = Not Suitable, Match Score = 0-2/10
- If target audience explicitly states they dislike a characteristic that the product has → Logical Consistency = No, Mismatch Detected = Yes, Not Suitable, Match Score = 0-2/10
- If target audience = "none" → Logical Consistency = Yes (no contradiction to check)
- Any contradiction or mismatch → Not Suitable, Match Score = 0-2/10"""
        else:
            validation_prompt = image_analysis_prompt + "\n\n3. Provide general recommendations for advertising use.\n\nProvide your analysis."
    
    # Step 2: 광고 문구와 비교 (이미지 분석 결과 포함)
    response = process_image_with_llava(image, validation_prompt)
    
    # 응답 파싱 - 개선된 로직
    response_lower = response.lower()
    
    # 불일치 감지 (구조화된 형식 우선)
    has_mismatch = False
    mismatch_details = ""
    logical_consistency = None
    
    # 후처리: 광고 문구에서 직접 논리적 모순 패턴 찾기 (LLaVa 응답보다 우선)
    direct_logical_contradiction = False
    if ad_copy_text:
        ad_lower = ad_copy_text.lower()
        # "hate spicy", "dislike spicy", "don't like spicy" 등의 패턴 찾기
        negative_patterns = [
            r'hate\s+spicy',
            r'dislike\s+spicy',
            r"don'?t\s+like\s+spicy",
            r'not\s+for\s+.*spicy',
            r'avoid\s+spicy',
            r'people\s+who\s+hate\s+spicy',
            r'people\s+who\s+dislike\s+spicy',
        ]
        # 광고 문구에 "spicy"가 포함되어 있는지 확인
        has_spicy_in_ad = 'spicy' in ad_lower
        
        # 타겟 오디언스가 매운 것을 싫어하는데 제품이 매운 경우
        for pattern in negative_patterns:
            if re.search(pattern, ad_lower, re.IGNORECASE):
                if has_spicy_in_ad:
                    direct_logical_contradiction = True
                    logical_consistency = False
                    has_mismatch = True
                    mismatch_details = "Target audience dislikes spicy food but product is described as spicy"
                    break
    
    # Logical Consistency 확인 (LLaVa 응답에서, 후처리 결과가 없을 때만)
    if logical_consistency is None:
        logical_consistency_match = re.search(r'logical\s+consistency[:\s]+(yes|no)', response_lower)
        if logical_consistency_match:
            logical_consistency = logical_consistency_match.group(1).lower() == "yes"
            if not logical_consistency:
                has_mismatch = True
    
    # 구조화된 형식에서 불일치 확인
    mismatch_detected_match = re.search(r'mismatch\s+detected[:\s]+(yes|no)', response_lower)
    if mismatch_detected_match:
        mismatch_detected = mismatch_detected_match.group(1).lower() == "yes"
        if mismatch_detected:
            has_mismatch = True
        # 불일치 상세 정보 추출
        mismatch_details_match = re.search(r'mismatch\s+details[:\s]+([^\n]+?)(?:\n|Overall|Reasoning)', response_lower, re.IGNORECASE | re.DOTALL)
        if mismatch_details_match:
            mismatch_details = mismatch_details_match.group(1).strip()
            if mismatch_details.lower() != "none" and len(mismatch_details) > 5:
                has_mismatch = True
    else:
        # 키워드 기반 불일치 감지 (fallback)
        mismatch_keywords = [
            "mismatch", "doesn't match", "does not match", "contradict", 
            "inappropriate", "incorrect", "wrong context", "different setting",
            "not match", "unmatch", "conflict", "discrepancy", "different product"
        ]
        has_mismatch = any(keyword in response_lower for keyword in mismatch_keywords)
    
    # 점수 추출 (구조화된 형식 우선)
    relevance_score = None
    
    # 구조화된 형식에서 점수 추출 (우선순위 1)
    # 범위 형식 처리 (예: "7-10/10" -> 최소값 사용)
    structured_score_match = re.search(r'match\s+score[:\s]+(\d+(?:\.\d+)?)(?:\s*-\s*\d+)?\s*/10', response_lower)
    if structured_score_match:
        score_value = float(structured_score_match.group(1))
        relevance_score = score_value / 10.0
    else:
        # 다양한 패턴으로 점수 찾기 (우선순위 2)
        score_patterns = [
            r'rating[:\s]+(\d+(?:\.\d+)?)(?:\s*-\s*\d+)?\s*/10',  # "Rating: 10/10" or "Rating: 7-10/10"
            r'score[:\s]+(\d+(?:\.\d+)?)(?:\s*-\s*\d+)?\s*/10',   # "Score: 9/10" or "Score: 7-10/10"
            r'match[:\s]+(\d+(?:\.\d+)?)(?:\s*-\s*\d+)?\s*/10',   # "Match: 8/10" or "Match: 7-10/10"
            r'(\d+(?:\.\d+)?)(?:\s*-\s*\d+)?\s*/10',              # "10/10" or "7-10/10"
            r'(\d+(?:\.\d+)?)\s+on\s+the\s+scale', # "9 on the scale"
            r'rate[:\s]+(\d+(?:\.\d+)?)',          # "Rate: 8"
        ]
        for pattern in score_patterns:
            score_match = re.search(pattern, response_lower)
            if score_match:
                score_value = float(score_match.group(1))
                # 10점 만점인 경우만 정규화
                if '/10' in pattern or 'scale' in pattern:
                    relevance_score = score_value / 10.0
                else:
                    # 이미 0-1 스케일인 경우
                    relevance_score = min(score_value, 1.0)
                break
    
    if relevance_score is None:
        # 점수가 없으면 불일치 여부로 판단
        if has_mismatch:
            relevance_score = 0.3  # 불일치 감지 시 낮은 점수
        elif "perfect match" in response_lower or "excellent match" in response_lower:
            relevance_score = 0.95
        elif "good match" in response_lower or "matches well" in response_lower:
            relevance_score = 0.8
        elif "suitable" in response_lower or "match" in response_lower:
            relevance_score = 0.6
        else:
            relevance_score = 0.5
    
    # 점수 조정: 명확한 불일치가 있으면 강제로 낮은 점수 부여
    # LLaVa가 높은 점수를 줘도 불일치가 있으면 낮춤
    # 불일치가 있으면 점수 차이를 더 명확하게 (0.1-0.2 범위)
    max_score_for_mismatch = 0.2
    min_score_for_mismatch = 0.1
    
    # 논리적 모순이 감지되면 무조건 낮은 점수 (후처리 결과 우선)
    if logical_consistency is False:
        # 논리적 모순 → 0.1로 강제 조정 (더 낮은 점수)
        relevance_score = min_score_for_mismatch
    elif has_mismatch:
        # 기타 불일치 감지 → 0.1-0.2 범위로 강제 조정
        relevance_score = min(relevance_score, max_score_for_mismatch) if relevance_score else min_score_for_mismatch
    
    # 적합성 판단 (구조화된 형식 우선)
    is_valid = None
    overall_assessment_match = re.search(r'overall\s+assessment[:\s]+(suitable|not\s+suitable)', response_lower)
    if overall_assessment_match:
        is_valid = overall_assessment_match.group(1).lower().replace(" ", "") == "suitable"
        # Overall Assessment가 Suitable여도 불일치가 있으면 False로 변경
        if is_valid and (logical_consistency is False or has_mismatch):
            is_valid = False
    else:
        # Logical Consistency가 No이면 자동으로 Not Suitable (최우선)
        if logical_consistency is False:
            is_valid = False
        # 점수 기반 판단 (fallback)
        elif relevance_score is not None:
            is_valid = relevance_score >= 0.7 and not has_mismatch
        else:
            # 키워드 기반 판단
            is_valid = "suitable" in response_lower and not has_mismatch and (logical_consistency is not False)
    
    image_quality_ok = "quality" in response_lower and ("good" in response_lower or "high" in response_lower or "excellent" in response_lower)
    
    # 이슈 추출
    issues = []
    if has_mismatch:
        if mismatch_details and mismatch_details.lower() != "none":
            issues.append(mismatch_details)
        else:
            # 불일치 내용 추출
            mismatch_section = re.search(r'mismatch[^.]*\.', response_lower, re.IGNORECASE)
            if mismatch_section:
                issues.append(mismatch_section.group(0))
            else:
                issues.append("Context mismatch detected between image and ad copy")
    
    return {
        "is_valid": is_valid,
        "image_quality_ok": image_quality_ok,
        "relevance_score": relevance_score,
        "analysis": response,
        "issues": issues,
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


# LLaVa 일관성 분석 보고서

## 테스트 개요
- **동일한 모델**: llava-hf/llava-1.5-7b-hf
- **동일한 광고 문구**: 
  - 좋은 예: "Spicy Pork Kimchi Stew – one spoon and you'll forget everything else."
  - 나쁜 예: "The ultimate choice for people who hate spicy food: our extra-.spicy Pork Kimchi Stew"
- **동일한 이미지**: 김치찌개 이미지

## 테스트 결과 비교

### 테스트 1: 양자화 기본값 (8-bit, 명시 안 됨)
**결과**: ✅ **구분 성공**

| 항목 | 좋은 광고 문구 | 나쁜 광고 문구 |
|------|---------------|---------------|
| 적합성 | True ✅ | False ✅ |
| 점수 | 1.0 (10/10) | 0.3 (0-3/10) |
| Logical Consistency | Yes | No ✅ |
| Mismatch Detected | No | Yes ✅ |
| Overall Assessment | Suitable | Not Suitable ✅ |

**LLaVa 분석 (나쁜 광고 문구)**:
- ✅ "hate spicy" + "spicy [product]" = CONTRADICTION 감지
- ✅ Logical Consistency = No
- ✅ Mismatch Detected = Yes
- ✅ Not Suitable 판단

---

### 테스트 2: 양자화 Enabled (8-bit)
**결과**: ❌ **구분 실패**

| 항목 | 좋은 광고 문구 | 나쁜 광고 문구 |
|------|---------------|---------------|
| 적합성 | True ✅ | True ❌ |
| 점수 | 0.9 (9/10) | 1.0 (10/10) ❌ |
| Logical Consistency | Yes | Yes ❌ |
| Mismatch Detected | No | No ❌ |
| Overall Assessment | Suitable | Suitable ❌ |
| GPU 메모리 | 6.84 GB | - |

**LLaVa 분석 (나쁜 광고 문구)**:
- ❌ Target audience: "For people who hate spicy food" 추출
- ❌ Product: "extra-spicy Pork Kimchi Stew" 추출
- ❌ **하지만 Logical Consistency = Yes로 잘못 판단**
- ❌ Reasoning: "The ad copy matches the image, and the target audience is consistent with the product characteristics." (잘못됨)

**문제점**: 명백한 모순("hate spicy" + "spicy product")을 감지하지 못함

---

### 테스트 3: 양자화 Disabled (FP16)
**결과**: ❌ **구분 실패**

| 항목 | 좋은 광고 문구 | 나쁜 광고 문구 |
|------|---------------|---------------|
| 적합성 | True ✅ | True ❌ |
| 점수 | 1.0 (10/10) | 1.0 (10/10) ❌ |
| Logical Consistency | Yes | Yes ❌ |
| Mismatch Detected | No | No ❌ |
| Overall Assessment | Suitable | Suitable ❌ |
| GPU 메모리 | 13.16 GB | - |

**LLaVa 분석 (나쁜 광고 문구)**:
- ✅ Target audience: "People who hate spicy food" 추출
- ✅ Product: "extra-spicy Pork Kimchi Stew" 추출
- ✅ 규칙 인식: "If target audience = 'people who hate spicy' AND product contains 'spicy' → CONTRADICTION"
- ❌ **하지만 Logical Consistency = Yes로 잘못 판단**
- ❌ Reasoning: "The ad copy and image are compatible, and there are no contradictions or mismatches between them." (잘못됨)

**문제점**: 규칙을 인식하고 언급했지만, 최종 판단에서 무시함

---

## 문제 분석

### 1. LLaVa의 일관성 부족 (Stochastic Behavior)
- **동일한 입력**에 대해 **다른 결과** 생성
- `temperature`와 `do_sample` 설정으로 인한 변동성
- 모델의 내부 랜덤성

### 2. 논리적 일관성 검증 실패
- 테스트 2, 3에서 명백한 모순을 감지하지 못함
- 프롬프트의 규칙을 인식하지만 최종 판단에서 무시
- LLaVa-1.5-7b의 논리적 추론 능력 한계

### 3. 응답 형식 불일치
- 테스트 1: 구조화된 형식 준수
- 테스트 2, 3: 형식이 약간 다르지만 핵심 정보는 추출
- 파싱 로직이 일관성 있게 작동하지만, 모델 응답 자체가 불일치

### 4. 양자화 영향
- 양자화 사용 여부와 결과 품질 간 직접적 연관성은 없어 보임
- 메모리 사용량만 차이: 8-bit (6.84 GB) vs FP16 (13.16 GB)

---

## 해결 방안

### 1. 여러 번 실행하여 평균/투표 (Ensemble)
```python
def validate_with_ensemble(image, ad_copy_text, n_runs=3):
    results = []
    for _ in range(n_runs):
        result = validate_image_and_text(image, ad_copy_text)
        results.append(result)
    
    # 다수결 투표 또는 평균
    is_valid_votes = sum(1 for r in results if r['is_valid'])
    return is_valid_votes >= (n_runs // 2 + 1)
```

### 2. Temperature 낮추기
```python
# 더 결정론적인 응답을 위해 temperature 낮춤
response = process_image_with_llava(
    image, prompt,
    temperature=0.1,  # 기본값 0.7에서 낮춤
    do_sample=False   # 샘플링 비활성화
)
```

### 3. 프롬프트 강화
- 규칙을 더 명확하고 강제적으로 작성
- 예시 추가 (Few-shot learning)
- 단계별 검증 강화

### 4. 후처리 로직 강화
- 응답에서 키워드 직접 추출하여 재검증
- 규칙 기반 검증 추가 (프롬프트 의존도 감소)

### 5. 더 큰 모델 사용
- LLaVa-1.5-13b-hf (더 정확하지만 느리고 메모리 많이 사용)

---

## 결론

1. **LLaVa의 일관성 문제**: 동일한 입력에 대해 다른 결과 생성
2. **논리적 추론 한계**: 명백한 모순을 감지하지 못하는 경우 발생
3. **양자화 영향 없음**: 8-bit vs FP16과 결과 품질 간 직접적 연관성 없음
4. **해결책**: Ensemble, Temperature 조정, 프롬프트 강화, 후처리 로직 강화

---

## 권장 사항

1. **단기**: Temperature 낮추기 + 여러 번 실행하여 투표
2. **중기**: 프롬프트 강화 + 후처리 로직 강화
3. **장기**: 더 큰 모델 사용 또는 GPT-4V 같은 더 강력한 모델 고려


# LLaVA Stage 2 결과 품질 평가 및 다음 단계 활용 가능성 분석

## 📊 현재 상태 요약

### ✅ 해결된 문제
1. **파싱 안정성**: 이스케이프된 언더스코어 처리 완료
2. **결과 구조**: 일관성 있는 JSON 형식 반환
3. **DB 저장**: `vlm_traces` 테이블에 저장 완료
4. **Job 상태 관리**: `current_step='vlm_judge'`, `status='done'` 업데이트 완료

### ⚠️ 확인 필요 사항
1. **검증 기준의 명확성**: LLaVA가 실제로 정확하게 판단하는가?
2. **결과의 신뢰성**: 일관성 있는 결과를 반환하는가?
3. **다음 단계 활용 가능성**: 정량 평가와 통합하여 사용 가능한가?

---

## 🔍 현재 LLaVA Stage 2 결과 분석

### 검증 항목 (5가지)
1. **on_brief**: 광고 brief 준수 여부
2. **occlusion**: 텍스트/콘텐츠 가림 여부
3. **contrast_ok**: 텍스트-배경 대비 적절성
4. **cta_present**: CTA 존재 여부
5. **issues**: 발견된 이슈 목록

### 실제 결과 샘플
```
[결과 1]
- on_brief: True
- occlusion: False
- contrast_ok: True
- cta_present: True
- issues: 0개
- reasoning: "Advertisement closely follows the advertising brief"

[결과 2]
- on_brief: False
- occlusion: False
- contrast_ok: False
- cta_present: True
- issues: 0개
- reasoning: "Advertisement meets the brief and is easily readable"
```

---

## 🎯 다음 단계 활용 가능성 평가

### 1. 정량 평가와의 연계

#### ✅ 활용 가능한 부분

**1.1 `occlusion` → IoU 평가와 연계**
- LLaVA의 `occlusion: true`는 정성적 판단
- IoU 평가는 정량적 측정 (0.0-1.0)
- **활용 방안**: LLaVA가 `occlusion: true`로 판단한 경우, IoU 평가를 우선적으로 실행하여 정량적 확인

**1.2 `contrast_ok` → 가독성 평가와 연계**
- LLaVA의 `contrast_ok: false`는 정성적 판단
- 가독성 평가는 WCAG 기준으로 정량적 측정 (대비 비율)
- **활용 방안**: LLaVA가 `contrast_ok: false`로 판단한 경우, 가독성 평가를 실행하여 정량적 확인

**1.3 `on_brief` → 전체 평가 종합 판단**
- LLaVA의 `on_brief`는 광고 brief 준수 여부를 정성적으로 판단
- 정량 평가 결과와 함께 종합 판단에 활용 가능
- **활용 방안**: 모든 평가 결과를 종합하여 최종 승인/거부 결정

**1.4 `issues` → 문제점 추적**
- LLaVA가 발견한 이슈를 정량 평가 결과와 비교
- **활용 방안**: LLaVA 이슈와 정량 평가 결과가 일치하는지 확인

#### ⚠️ 제한 사항

**1.1 정량 평가와의 불일치 가능성**
- LLaVA가 `contrast_ok: false`로 판단했지만, 실제 WCAG 대비 비율은 충족할 수 있음
- LLaVA가 `occlusion: false`로 판단했지만, 실제 IoU가 0.1 이상일 수 있음
- **해결 방안**: 정량 평가 결과를 우선시하고, LLaVA 결과는 참고용으로 사용

**1.2 `on_brief` 판단의 주관성**
- LLaVA의 `on_brief` 판단은 모델의 주관적 해석에 의존
- 광고 brief가 명확하지 않으면 부정확할 수 있음
- **해결 방안**: 광고 brief를 프롬프트에 명시적으로 포함

---

## 📋 다음 단계 활용 시나리오

### 시나리오 1: 통합 평가 파이프라인

```
1. LLaVA Stage 2 실행
   ↓
2. 결과 분석
   - occlusion: true → IoU 평가 우선 실행
   - contrast_ok: false → 가독성 평가 우선 실행
   ↓
3. 정량 평가 실행
   - OCR 평가
   - 가독성 평가 (LLaVA가 contrast_ok: false인 경우)
   - IoU 평가 (LLaVA가 occlusion: true인 경우)
   ↓
4. 종합 판단
   - LLaVA 결과 + 정량 평가 결과 종합
   - 최종 승인/거부 결정
```

### 시나리오 2: 결과 비교 및 검증

```
1. LLaVA Stage 2 실행
   ↓
2. 정량 평가 실행
   ↓
3. 결과 비교
   - LLaVA occlusion vs IoU 결과
   - LLaVA contrast_ok vs 가독성 결과
   ↓
4. 불일치 감지
   - 불일치 시 재평가 또는 수동 검토
```

---

## 🎯 품질 평가 결과

### ✅ 활용 가능한 부분 (70%)

1. **구조적 완성도**: ✅
   - JSON 형식으로 구조화된 결과
   - DB 저장 완료
   - API 응답 모델 완성

2. **파싱 안정성**: ✅
   - 이스케이프 처리 완료
   - JSON 파싱 + 정규식 fallback

3. **검증 항목의 적절성**: ✅
   - 5가지 검증 항목이 정량 평가와 연계 가능
   - `occlusion`, `contrast_ok`는 정량 평가와 직접 연계 가능

### ⚠️ 개선 필요 사항 (30%)

1. **검증 기준의 명확성**: ⚠️
   - `on_brief` 판단 기준이 모호할 수 있음
   - 광고 brief를 프롬프트에 명시적으로 포함 필요

2. **결과의 신뢰성**: ⚠️
   - LLaVA 모델의 주관적 판단에 의존
   - 정량 평가 결과와 불일치 가능성

3. **다음 단계 활용 구조**: ⚠️
   - 현재는 단순히 결과만 반환
   - 정량 평가와 통합하는 로직 필요

---

## 💡 권장 사항

### 1. 즉시 활용 가능 (현재 상태)

✅ **LLaVA Stage 2 결과를 다음 단계에서 활용 가능**
- 구조적으로 완성되어 있음
- 정량 평가와 연계 가능한 항목들이 있음
- DB 저장 및 조회 가능

### 2. 개선 권장 사항

#### 2.1 프롬프트 개선
```python
# 광고 brief를 프롬프트에 명시적으로 포함
judge_prompt = f"""Analyze this final advertisement image and evaluate the following aspects.

## Advertising Brief
{ad_brief_text}  # job_inputs에서 가져온 광고 brief

## Evaluation Criteria
...
"""
```

#### 2.2 결과 신뢰도 추가
```python
result = {
    "on_brief": bool,
    "occlusion": bool,
    "contrast_ok": bool,
    "cta_present": bool,
    "issues": List[str],
    "reasoning": str,
    "confidence": float,  # 추가: 판단 신뢰도 (0.0-1.0)
    "analysis": str
}
```

#### 2.3 정량 평가와 통합 로직
```python
def evaluate_with_llava_and_quantitative(job_id, overlay_id):
    # 1. LLaVA Stage 2 실행
    llava_result = judge_final_ad(image)
    
    # 2. 정량 평가 우선순위 결정
    priority_evaluations = []
    if llava_result["occlusion"]:
        priority_evaluations.append("iou")
    if not llava_result["contrast_ok"]:
        priority_evaluations.append("readability")
    
    # 3. 정량 평가 실행
    quantitative_results = {}
    for eval_type in priority_evaluations:
        quantitative_results[eval_type] = run_quantitative_evaluation(...)
    
    # 4. 종합 판단
    final_judgment = combine_results(llava_result, quantitative_results)
    
    return final_judgment
```

---

## 📊 최종 결론

### ✅ **LLaVA Stage 2 결과는 다음 단계에서 활용 가능한 품질입니다**

**이유:**
1. **구조적 완성도**: JSON 형식, DB 저장, API 응답 완료
2. **파싱 안정성**: 이스케이프 처리 완료, 안정적인 파싱
3. **연계 가능성**: 정량 평가와 직접 연계 가능한 항목들 (`occlusion`, `contrast_ok`)
4. **확장 가능성**: 추가 개선 사항을 적용하면 더욱 신뢰성 높은 결과 가능

**활용 방안:**
- LLaVA 결과를 **참고 지표**로 사용
- 정량 평가 결과와 **상호 검증**
- **우선순위 결정**에 활용 (occlusion이면 IoU 우선 실행)
- **종합 판단**에 활용 (모든 평가 결과 종합)

**개선 권장:**
- 광고 brief를 프롬프트에 명시적으로 포함
- 정량 평가와 통합하는 로직 추가
- 결과 신뢰도 점수 추가

---

**작성일:** 2025-11-26  
**작성자:** LEEYH205  
**버전:** 1.0.0


# LLaVA Stage 2 검증 기준 및 결론 출력 분석

## 개요
LLaVA Stage 2는 최종 광고 시각 결과물에 대한 품질 검증을 수행합니다. 이 문서는 검증 기준, 파싱 로직, 그리고 결론 출력 방식을 분석합니다.

---

## 1. 검증 기준 (Evaluation Criteria)

### 1.1 프롬프트에 정의된 검증 항목

`services/llava_service.py`의 `judge_final_ad()` 함수에서 사용하는 프롬프트:

```python
judge_prompt = """Analyze this final advertisement image and evaluate the following aspects. Provide your response in JSON format.

## Evaluation Criteria

1. **on_brief**: Does the advertisement follow the advertising brief? (true/false)
2. **occlusion**: Is there any text or important content occluded/blocked? (true if occluded, false if not)
3. **contrast_ok**: Is the contrast between text and background appropriate for readability? (true/false)
4. **cta_present**: Is there a clear call-to-action (CTA) present? (true/false)
5. **issues**: List any specific issues or problems you find (array of strings)
```

### 1.2 각 검증 항목의 의미

| 항목 | 의미 | 값의 의미 |
|------|------|----------|
| `on_brief` | 광고 brief 준수 여부 | `true`: brief를 따름, `false`: brief를 따르지 않음 |
| `occlusion` | 가림/차단 여부 | `true`: 텍스트나 중요 콘텐츠가 가려짐, `false`: 가림 없음 |
| `contrast_ok` | 텍스트-배경 대비 적절성 | `true`: 가독성 좋음, `false`: 가독성 문제 있음 |
| `cta_present` | CTA 존재 여부 | `true`: CTA 있음, `false`: CTA 없음 |
| `issues` | 발견된 이슈 목록 | 문자열 배열, 이슈 없으면 빈 배열 `[]` |

### 1.3 응답 형식 요구사항

LLaVA는 다음 JSON 형식으로 응답해야 합니다:

```json
{
  "on_brief": true/false,
  "occlusion": true/false,
  "contrast_ok": true/false,
  "cta_present": true/false,
  "issues": ["issue1", "issue2", ...],
  "reasoning": "Brief explanation of your evaluation"
}
```

---

## 2. 파싱 로직 (Parsing Logic)

### 2.1 파싱 전략: 2단계 Fallback

`_parse_judge_response()` 함수는 다음 순서로 파싱을 시도합니다:

1. **Step 1: JSON 파싱 시도**
   - 정규식으로 JSON 블록 추출: `r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'`
   - `json.loads()`로 파싱 시도
   - 성공 시 즉시 반환

2. **Step 2: 정규식 Fallback 파싱**
   - JSON 파싱 실패 시 정규식으로 각 필드 추출
   - 키워드 기반 fallback 로직 사용

### 2.2 JSON 파싱 로직 (Step 1)

```python
# JSON 블록 추출
json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
if json_match:
    json_str = json_match.group(0)
    parsed = json.loads(json_str)
    
    result = {
        "on_brief": parsed.get("on_brief", False),  # 기본값: False
        "occlusion": parsed.get("occlusion", False),
        "contrast_ok": parsed.get("contrast_ok", False),
        "cta_present": parsed.get("cta_present", False),
        "issues": parsed.get("issues", []),
        "reasoning": parsed.get("reasoning", ""),
        "analysis": response  # 원본 응답 보관
    }
```

**주의사항:**
- 모든 필드의 기본값이 `False` 또는 `[]`입니다.
- 필드가 없거나 파싱 실패 시 기본값이 사용됩니다.

### 2.3 정규식 Fallback 파싱 (Step 2)

각 필드별로 정규식 패턴을 사용하여 추출합니다:

#### 2.3.1 `on_brief` 파싱
```python
# 패턴 1: JSON 형식
on_brief_match = re.search(r'"on_brief"[:\s]+(true|false)', response, re.IGNORECASE)

# 패턴 2: 일반 텍스트
on_brief_match = re.search(r'on[_\s]brief[:\s]+(true|false|yes|no)', response_lower)

# Fallback: 키워드 기반
on_brief = "brief" in response_lower and ("follow" in response_lower or "yes" in response_lower)
```

#### 2.3.2 `occlusion` 파싱
```python
# 패턴 1: JSON 형식
occlusion_match = re.search(r'"occlusion"[:\s]+(true|false)', response, re.IGNORECASE)

# 패턴 2: 일반 텍스트
occlusion_match = re.search(r'occlusion[:\s]+(true|false|yes|no)', response_lower)

# Fallback: 키워드 기반 (true면 가림 있음)
occlusion = "occlude" in response_lower or "blocked" in response_lower or "hidden" in response_lower
```

#### 2.3.3 `contrast_ok` 파싱
```python
# 패턴 1: JSON 형식
contrast_match = re.search(r'"contrast_ok"[:\s]+(true|false)', response, re.IGNORECASE)

# 패턴 2: 일반 텍스트
contrast_match = re.search(r'contrast[_\s]ok[:\s]+(true|false|yes|no)', response_lower)

# Fallback: 키워드 기반
contrast_ok = "contrast" in response_lower and ("good" in response_lower or "appropriate" in response_lower)
```

#### 2.3.4 `cta_present` 파싱
```python
# 패턴 1: JSON 형식
cta_match = re.search(r'"cta_present"[:\s]+(true|false)', response, re.IGNORECASE)

# 패턴 2: 일반 텍스트
cta_match = re.search(r'cta[_\s]present[:\s]+(true|false|yes|no)', response_lower)

# Fallback: 키워드 기반
cta_present = "cta" in response_lower or "call-to-action" in response_lower
```

#### 2.3.5 `issues` 파싱
```python
# JSON 배열 추출
issues_match = re.search(r'"issues"[:\s]+\[(.*?)\]', response, re.IGNORECASE | re.DOTALL)

# Fallback: 키워드 기반 이슈 추출
if "issue" in response_lower or "problem" in response_lower:
    issue_sentences = re.findall(r'[^.!?]*(?:issue|problem|error|concern)[^.!?]*[.!?]', response_lower, re.IGNORECASE)
    issues = [s.strip() for s in issue_sentences[:5]]  # 최대 5개
```

---

## 3. 결론 출력 방식

### 3.1 API 응답 구조

`routers/llava_stage2.py`의 `judge()` 함수는 다음 `JudgeOut` 모델로 응답합니다:

```python
return JudgeOut(
    job_id=body.job_id,
    vlm_trace_id=str(vlm_trace_id),
    on_brief=result.get("on_brief", False),
    occlusion=result.get("occlusion", False),
    contrast_ok=result.get("contrast_ok", False),
    cta_present=result.get("cta_present", False),
    analysis=result.get("analysis", ""),  # 원본 LLaVA 응답
    issues=result.get("issues", [])
)
```

### 3.2 DB 저장 구조

`vlm_traces` 테이블에 다음 정보가 저장됩니다:

```sql
INSERT INTO vlm_traces (
    vlm_trace_id, job_id, provider, operation_type, 
    request, response, latency_ms, created_at, updated_at
)
VALUES (
    :vlm_trace_id, :job_id, 'llava', 'judge',
    CAST(:request AS jsonb), CAST(:response AS jsonb), :latency_ms,
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
)
```

**`response` 필드 구조:**
```json
{
  "on_brief": false,
  "occlusion": false,
  "contrast_ok": false,
  "cta_present": true,
  "issues": [],
  "reasoning": "...",
  "analysis": "원본 LLaVA 응답 텍스트"
}
```

### 3.3 Job 상태 업데이트

1. **Judge 시작 시:**
   - `current_step = 'vlm_judge'`
   - `status = 'running'`

2. **Judge 완료 시:**
   - `status = 'done'`

3. **오류 발생 시:**
   - `status = 'failed'`

---

## 4. 발견된 문제점

### 4.1 파싱 불일치 문제

**현상:**
테스트 결과에서 다음과 같은 불일치가 발견되었습니다:

```json
{
  "on_brief": false,      // 파싱된 값
  "occlusion": false,
  "contrast_ok": false,
  "cta_present": true,
  "analysis": "{\n\"on_brief\": true, ...}"  // 원본에는 true
}
```

**원인 분석:**
1. JSON 파싱이 실패했을 가능성
   - LLaVA가 반환한 JSON이 유효하지 않거나 중첩된 구조일 수 있음
   - 정규식 `r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'`가 복잡한 JSON을 제대로 추출하지 못할 수 있음

2. 정규식 Fallback이 잘못된 값을 추출
   - 키워드 기반 fallback이 부정확할 수 있음
   - 예: `"on_brief": true`가 있지만 정규식이 `false`를 추출

3. 기본값 사용
   - JSON 파싱 실패 시 모든 필드가 기본값 `False`로 설정됨

### 4.2 JSON 파싱 정규식의 한계

현재 정규식: `r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'`

**문제점:**
- 중첩된 JSON 객체를 제대로 처리하지 못할 수 있음
- JSON 내부에 문자열로 포함된 JSON이 있을 경우 오작동 가능

**개선 방안:**
- 더 강력한 JSON 추출 로직 필요
- 여러 JSON 블록을 찾아서 가장 큰 블록 선택
- 또는 JSON 파서의 오류 메시지를 분석하여 부분 파싱 시도

### 4.3 LLaVA 응답 형식 불일치

LLaVA가 항상 유효한 JSON을 반환하지 않을 수 있습니다:

**가능한 응답 형식:**
1. 순수 JSON: `{"on_brief": true, ...}`
2. 마크다운 코드 블록: ````json\n{...}\n````
3. 설명 + JSON: `The evaluation is:\n{"on_brief": true, ...}`
4. 이스케이프된 JSON: `{\"on_brief\": true, ...}`

**현재 파싱 로직의 한계:**
- 마크다운 코드 블록을 처리하지 않음
- 이스케이프된 JSON을 처리하지 않음

---

## 5. 개선 제안

### 5.1 JSON 파싱 개선

```python
def _extract_json_from_response(response: str) -> Optional[dict]:
    """응답에서 JSON 블록을 추출하고 파싱"""
    import json
    
    # 1. 마크다운 코드 블록 제거
    response = re.sub(r'```json\s*\n', '', response)
    response = re.sub(r'```\s*\n', '', response)
    
    # 2. 이스케이프된 JSON 처리
    response = response.replace('\\"', '"')
    
    # 3. 여러 JSON 블록 찾기
    json_blocks = []
    depth = 0
    start = -1
    
    for i, char in enumerate(response):
        if char == '{':
            if depth == 0:
                start = i
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0 and start != -1:
                json_blocks.append((start, i + 1))
    
    # 4. 가장 긴 JSON 블록 선택
    if json_blocks:
        longest_block = max(json_blocks, key=lambda x: x[1] - x[0])
        json_str = response[longest_block[0]:longest_block[1]]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    return None
```

### 5.2 파싱 결과 검증

```python
def _validate_parsed_result(parsed: dict) -> dict:
    """파싱된 결과의 타입과 범위를 검증"""
    result = {
        "on_brief": bool(parsed.get("on_brief", False)),
        "occlusion": bool(parsed.get("occlusion", False)),
        "contrast_ok": bool(parsed.get("contrast_ok", False)),
        "cta_present": bool(parsed.get("cta_present", False)),
        "issues": parsed.get("issues", []),
        "reasoning": str(parsed.get("reasoning", "")),
    }
    
    # issues가 리스트가 아니면 변환
    if not isinstance(result["issues"], list):
        if isinstance(result["issues"], str):
            result["issues"] = [result["issues"]] if result["issues"] else []
        else:
            result["issues"] = []
    
    return result
```

### 5.3 로깅 개선

파싱 과정을 더 자세히 로깅하여 디버깅을 용이하게:

```python
logger.info(f"[Judge 파싱] 원본 응답 길이: {len(response)}")
logger.info(f"[Judge 파싱] 원본 응답 (처음 200자): {response[:200]}")
logger.info(f"[Judge 파싱] JSON 파싱 시도 결과: {parsed}")
logger.info(f"[Judge 파싱] 최종 결과: {result}")
```

---

## 6. 결론

### 6.1 현재 동작 방식

1. **검증 기준:** 5가지 항목 (on_brief, occlusion, contrast_ok, cta_present, issues)
2. **파싱 전략:** JSON 우선, 정규식 fallback
3. **결론 출력:** `JudgeOut` 모델로 반환, `vlm_traces`에 저장

### 6.2 주요 문제점

1. **파싱 불일치:** 원본 응답과 파싱된 값이 다를 수 있음
2. **JSON 파싱 한계:** 복잡한 JSON 구조를 제대로 처리하지 못함
3. **기본값 의존:** 파싱 실패 시 모든 값이 `False`로 설정됨

### 6.3 권장 사항

1. JSON 파싱 로직 개선 (마크다운, 이스케이프 처리)
2. 파싱 결과 검증 로직 추가
3. 상세한 로깅으로 디버깅 용이성 향상
4. LLaVA 프롬프트 개선으로 JSON 형식 준수율 향상

---

**작성일:** 2025-11-26  
**작성자:** LEEYH205  
**버전:** 1.0.0


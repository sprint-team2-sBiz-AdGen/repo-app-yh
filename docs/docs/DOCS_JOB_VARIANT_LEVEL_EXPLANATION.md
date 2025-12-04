# Job 레벨 vs Variant 레벨 설명

## 📋 개요

파이프라인 단계는 **Variant 레벨**과 **Job 레벨** 두 가지로 구분됩니다.

---

## 🔄 Variant 레벨 (is_job_level: False 또는 없음)

### 의미
- **각 variant별로 독립적으로 실행**되는 단계
- Job에 3개의 variant가 있으면, 각 variant마다 별도로 실행됨

### 실행 방식
```
Job ID: job-123
  ├─ Variant 1 → vlm_analyze 실행 → yolo_detect 실행 → ... → iou_eval 실행
  ├─ Variant 2 → vlm_analyze 실행 → yolo_detect 실행 → ... → iou_eval 실행
  └─ Variant 3 → vlm_analyze 실행 → yolo_detect 실행 → ... → iou_eval 실행
```

### 특징
- **필수 파라미터**: `job_variants_id` (각 variant를 구분하기 위해 필요)
- **결과물**: Variant 개수만큼 생성 (예: 3개 variant면 3개의 결과)
- **상태 관리**: `jobs_variants` 테이블에서 각 variant별로 상태 추적
- **트리거**: `_process_job_variant_state_change()` → `trigger_next_pipeline_stage_for_variant()`

### Variant 레벨 단계 목록
- `vlm_analyze` (LLaVA Stage 1)
- `yolo_detect`
- `planner`
- `overlay`
- `vlm_judge` (LLaVA Stage 2)
- `ocr_eval`
- `readability_eval`
- `iou_eval`

### 예시
```python
# Variant 레벨 단계 (is_job_level 없음 = 기본값 False)
('vlm_analyze', 'done'): {
    'next_step': 'yolo_detect',
    'api_endpoint': '/api/yh/yolo/detect',
    'method': 'POST',
    'needs_overlay_id': False
    # is_job_level이 없으면 기본적으로 variant 레벨
}
```

---

## 📦 Job 레벨 (is_job_level: True)

### 의미
- **Job당 1번만 실행**되는 단계
- 모든 variants가 완료된 후 Job 전체에 대해 1번만 실행됨

### 실행 방식
```
Job ID: job-123
  ├─ Variant 1 → ... → iou_eval 완료
  ├─ Variant 2 → ... → iou_eval 완료
  └─ Variant 3 → ... → iou_eval 완료
      ↓ (모든 variants 완료 후)
  └─ [Job 레벨] ad_copy_gen_kor 실행 (1번만)
      ↓
  └─ [Job 레벨] instagram_feed_gen 실행 (1번만)
```

### 특징
- **필수 파라미터**: `job_id` (job_variants_id 불필요)
- **결과물**: Job당 1개만 생성 (예: 피드글 1개)
- **상태 관리**: `jobs` 테이블에서 Job 전체 상태 추적
- **트리거**: `_process_job_state_change()` → `trigger_next_pipeline_stage()`
- **실행 조건**: 모든 variants가 이전 단계 완료되어야 함

### Job 레벨 단계 목록
- `ad_copy_gen_kor` (영어 → 한국어 변환)
- `instagram_feed_gen` (인스타그램 피드 생성)

### 예시
```python
# Job 레벨 단계 (is_job_level: True)
('iou_eval', 'done'): {
    'next_step': 'ad_copy_gen_kor',
    'api_endpoint': '/api/yh/gpt/eng-to-kor',
    'method': 'POST',
    'is_job_level': True,  # Job 레벨 단계
    'needs_overlay_id': False
}
```

---

## 🔍 차이점 비교표

| 구분 | Variant 레벨 | Job 레벨 |
|------|-------------|----------|
| **is_job_level** | `False` 또는 없음 | `True` |
| **실행 횟수** | Variant 개수만큼 (예: 3번) | Job당 1번 |
| **필수 파라미터** | `job_variants_id` | `job_id` |
| **결과물 개수** | Variant 개수만큼 | 1개 |
| **상태 테이블** | `jobs_variants` | `jobs` |
| **트리거 함수** | `trigger_next_pipeline_stage_for_variant()` | `trigger_next_pipeline_stage()` |
| **실행 조건** | 각 variant가 이전 단계 완료 | 모든 variants가 이전 단계 완료 |

---

## 💡 실제 예시

### 예시 1: Variant 레벨 단계 (vlm_analyze)

**상황**: Job에 3개의 variant가 있음

**실행**:
1. Variant 1: `vlm_analyze` API 호출 (`job_variants_id=variant-1`)
2. Variant 2: `vlm_analyze` API 호출 (`job_variants_id=variant-2`)
3. Variant 3: `vlm_analyze` API 호출 (`job_variants_id=variant-3`)

**결과**: 3개의 `vlm_traces` 레코드 생성

---

### 예시 2: Job 레벨 단계 (instagram_feed_gen)

**상황**: Job에 3개의 variant가 있고, 모두 `iou_eval` 완료

**실행**:
1. 모든 variants가 `iou_eval (done)` 완료 확인
2. `ad_copy_gen_kor` 실행 (`job_id=job-123`, `job_variants_id` 없음)
3. `instagram_feed_gen` 실행 (`job_id=job-123`, `job_variants_id` 없음)

**결과**: 1개의 `instagram_feeds` 레코드 생성

---

## 🔧 코드에서의 처리

### Variant 레벨 단계 처리
```python
# job_state_listener.py
async def _process_job_variant_state_change(...):
    # Variant 상태 변화 감지
    await trigger_next_pipeline_stage_for_variant(
        job_variants_id=job_variants_id,  # 필수
        job_id=job_id,
        ...
    )
```

### Job 레벨 단계 처리
```python
# job_state_listener.py
async def _process_job_state_change(...):
    # Job 상태 변화 감지
    await trigger_next_pipeline_stage(
        job_id=job_id,  # 필수
        ...
    )
    
    # is_job_level 체크
    if not stage_info.get('is_job_level', False):
        return  # Variant 레벨 단계는 스킵
```

---

## ⚠️ 주의사항

### 1. vlm_judge의 422 에러 원인
- **문제**: `vlm_judge`는 Variant 레벨 단계인데, Job 레벨 트리거에서 호출됨
- **원인**: `trigger_next_pipeline_stage()`에서 `is_job_level` 체크 없이 모든 단계를 호출
- **해결**: `is_job_level`이 `False`인 경우 Job 레벨 트리거에서 스킵

### 2. API 엔드포인트 파라미터
- **Variant 레벨 API**: `job_variants_id` 필수
- **Job 레벨 API**: `job_id`만 필요 (job_variants_id 불필요)

---

## 📝 요약

- **Variant 레벨**: 각 variant별로 독립 실행 → 결과물 여러 개
- **Job 레벨**: Job당 1번 실행 → 결과물 1개
- **is_job_level: True**: Job 레벨 단계
- **is_job_level: False 또는 없음**: Variant 레벨 단계


# Job Running 상태에서 뒤처진 Variants 자동 재시작 분석

## 🔍 문제 상황

### 현재 문제
- **Job 테이블**: `status = 'running'`, `current_step = 'iou_eval'` (step_order: 8)
- **Variant 2**: `status = 'done'`, `current_step = 'vlm_analyze'` (step_order: 1)
- **결과**: Job은 진행 중이지만 Variant 2는 7단계 뒤처져 있음

### 발생 원인
1. Variant가 특정 단계에서 멈춤 (트리거 미발동 또는 API 호출 실패)
2. 다른 Variants는 계속 진행되어 Job의 `current_step`이 업데이트됨
3. 멈춘 Variant는 자동으로 재시작되지 않음

---

## 📊 현재 로직 분석

### 1. Job 상태 변화 처리 (`_process_job_state_change`)
```python
async def _process_job_state_change(
    self, 
    job_id: str, 
    current_step: Optional[str], 
    status: str,
    tenant_id: str
):
    """Job 상태 변화 처리 및 다음 단계 트리거 (기존 jobs 테이블용)"""
    # 현재는 job_id 기반으로만 작동
    # variants를 확인하지 않음
```

**문제점**:
- Job 상태가 변경될 때 뒤처진 variants를 확인하지 않음
- `job_id` 기반 파이프라인 트리거만 실행 (variant 기반 아님)

### 2. 멈춘 Variant 재시도 로직 (현재)
```python
# _process_job_variant_state_change 내부
# 5분 이상 업데이트되지 않은 done 상태 variant 확인
stuck_variants = await conn.fetch("""
    SELECT jv1.job_variants_id, jv1.current_step, jv1.updated_at
    FROM jobs_variants jv1
    WHERE jv1.job_id = $1
      AND jv1.status = 'done'
      AND jv1.current_step != 'iou_eval'
      AND jv1.updated_at < NOW() - INTERVAL '5 minutes'
      AND EXISTS (
          SELECT 1
          FROM jobs_variants jv2
          WHERE jv2.job_id = jv1.job_id
            AND jv2.current_step > jv1.current_step
            AND jv2.status = 'done'
      )
""", job_id)
```

**문제점**:
- Variant 상태 변화 시에만 작동
- Job 상태가 변경될 때는 작동하지 않음
- 5분 대기 시간 필요

---

## ✅ 해결 방안

### 방안 1: Job 상태 변화 시 뒤처진 Variants 확인 (추천)

**원칙**:
- Job이 `running` 상태로 변경되고 `current_step`이 yh 파트 단계인 경우
- 해당 job의 모든 variants 확인
- Job의 `current_step`보다 뒤처진 variants 찾기
- 각 variant의 다음 단계 자동 트리거

**구현 위치**: `services/job_state_listener.py`의 `_process_job_state_change` 함수

**단계 순서 정의**:
```python
STEP_ORDER = {
    'img_gen': 0,
    'vlm_analyze': 1,
    'yolo_detect': 2,
    'planner': 3,
    'overlay': 4,
    'vlm_judge': 5,
    'ocr_eval': 6,
    'readability_eval': 7,
    'iou_eval': 8
}
```

**로직**:
1. Job이 `running` 상태이고 yh 파트 단계인지 확인
2. 해당 job의 모든 variants 조회
3. Job의 `current_step`의 step_order 확인
4. 각 variant의 `current_step`의 step_order 확인
5. Variant의 step_order < Job의 step_order인 경우:
   - Variant가 `done` 상태이면 다음 단계 트리거
   - Variant가 `running` 또는 `queued` 상태이면 상태 확인 후 필요시 재시도

**장점**:
- ✅ Job 상태 변경 즉시 반응
- ✅ 5분 대기 시간 불필요
- ✅ 실시간 복구

**단점**:
- ⚠️ Job 상태 변경 시마다 variants 확인 (오버헤드)
- ⚠️ 순환 참조 가능성 (주의 필요)

---

### 방안 2: 주기적 백그라운드 태스크

**원칙**:
- 주기적으로 (예: 1분마다) running 상태인 job 확인
- 뒤처진 variants 찾아서 재시작

**장점**:
- ✅ 간단한 구현
- ✅ 순환 참조 위험 낮음

**단점**:
- ❌ 실시간 반응 불가 (최대 1분 지연)
- ❌ 불필요한 폴링 오버헤드

---

## 🎯 추천 구현: 방안 1 (Job 상태 변화 시 확인)

### 구현 세부사항

#### 1. `_process_job_state_change` 함수 수정

```python
async def _process_job_state_change(
    self, 
    job_id: str, 
    current_step: Optional[str], 
    status: str,
    tenant_id: str
):
    """Job 상태 변화 처리 및 뒤처진 variants 재시작"""
    
    # yh 파트 단계 정의
    YH_STEPS = ['vlm_analyze', 'yolo_detect', 'planner', 'overlay', 
                'vlm_judge', 'ocr_eval', 'readability_eval', 'iou_eval']
    
    # 단계 순서 정의
    STEP_ORDER = {
        'img_gen': 0,
        'vlm_analyze': 1,
        'yolo_detect': 2,
        'planner': 3,
        'overlay': 4,
        'vlm_judge': 5,
        'ocr_eval': 6,
        'readability_eval': 7,
        'iou_eval': 8
    }
    
    # Job이 running 상태이고 yh 파트 단계인 경우
    if status == 'running' and current_step in YH_STEPS:
        import asyncpg
        from config import DATABASE_URL
        from services.pipeline_trigger import trigger_next_pipeline_stage_for_variant
        
        job_step_order = STEP_ORDER.get(current_step, -1)
        if job_step_order < 0:
            return  # 알 수 없는 단계
        
        asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
        try:
            conn = await asyncpg.connect(asyncpg_url)
            try:
                # 해당 job의 모든 variants 조회
                variants = await conn.fetch("""
                    SELECT job_variants_id, current_step, status, img_asset_id
                    FROM jobs_variants
                    WHERE job_id = $1
                    ORDER BY creation_order
                """, uuid.UUID(job_id))
                
                # 뒤처진 variants 찾기
                for variant in variants:
                    variant_step = variant['current_step']
                    variant_status = variant['status']
                    variant_step_order = STEP_ORDER.get(variant_step, -1)
                    
                    # Variant가 Job보다 뒤처져 있는 경우
                    if variant_step_order < job_step_order:
                        logger.warning(
                            f"뒤처진 variant 감지: job_id={job_id}, "
                            f"job_step={current_step} (order: {job_step_order}), "
                            f"variant_step={variant_step} (order: {variant_step_order}), "
                            f"variant_status={variant_status}"
                        )
                        
                        # Variant가 done 상태이면 다음 단계 트리거
                        if variant_status == 'done':
                            await trigger_next_pipeline_stage_for_variant(
                                job_variants_id=str(variant['job_variants_id']),
                                job_id=job_id,
                                current_step=variant_step,
                                status='done',
                                tenant_id=tenant_id,
                                img_asset_id=str(variant['img_asset_id'])
                            )
                            logger.info(
                                f"뒤처진 variant 재시작: job_variants_id={variant['job_variants_id']}, "
                                f"current_step={variant_step}"
                            )
                        # Variant가 running 또는 queued 상태이면 상태 확인 후 필요시 재시도
                        elif variant_status in ['running', 'queued']:
                            # 오래 실행 중인 경우 재시도
                            # (추가 로직 필요)
                            pass
            finally:
                await conn.close()
        except Exception as e:
            logger.error(
                f"뒤처진 variant 재시작 오류: job_id={job_id}, error={e}",
                exc_info=True
            )
```

#### 2. 순환 참조 방지

**문제**: Job 상태 변경 → Variants 재시작 → Variant 상태 변경 → Job 상태 변경 (무한 루프)

**해결**:
- Variant 재시작 시 Job 상태를 변경하지 않도록 주의
- 재시작 플래그 사용 (같은 이벤트에서 중복 실행 방지)
- 최대 재시도 횟수 제한

---

## 📋 구현 체크리스트

### Phase 1: 기본 로직 구현
- [ ] `_process_job_state_change` 함수에 뒤처진 variants 확인 로직 추가
- [ ] 단계 순서 정의 (STEP_ORDER)
- [ ] yh 파트 단계 확인 로직

### Phase 2: Variant 재시작 로직
- [ ] 뒤처진 variant 감지
- [ ] done 상태 variant의 다음 단계 트리거
- [ ] running/queued 상태 variant 처리

### Phase 3: 순환 참조 방지
- [ ] 재시작 플래그 추가
- [ ] 최대 재시도 횟수 제한
- [ ] 로깅 및 모니터링

### Phase 4: 테스트
- [ ] 뒤처진 variant 재시작 테스트
- [ ] 순환 참조 방지 테스트
- [ ] 성능 테스트

---

## 🔄 동작 시나리오

### 시나리오 1: Job이 running으로 변경되고 variants가 뒤처진 경우

```
1. Job 상태 변경: status='running', current_step='iou_eval'
2. NOTIFY 이벤트 발행: job_state_changed
3. 리스너가 이벤트 수신
4. _process_job_state_change 호출
5. Job의 current_step 확인: 'iou_eval' (step_order: 8)
6. Variants 조회:
   - Variant 1: 'iou_eval' (done) - step_order: 8 ✅
   - Variant 2: 'vlm_analyze' (done) - step_order: 1 ⚠️ 뒤처짐
   - Variant 3: 'iou_eval' (done) - step_order: 8 ✅
7. Variant 2 재시작:
   - current_step='vlm_analyze', status='done'
   - 다음 단계: 'yolo_detect' 트리거
8. Variant 2가 yolo_detect로 진행 시작
```

### 시나리오 2: 순환 참조 방지

```
1. Job 상태 변경 → Variants 재시작
2. Variant 상태 변경 → Job 상태 변경 (트리거 발동)
3. 재시작 플래그 확인 → 이미 처리됨 → 스킵
```

---

## 📝 참고사항

### 주의사항
1. **순환 참조**: Job 상태 변경 → Variants 재시작 → Job 상태 변경 (무한 루프)
2. **성능**: Job 상태 변경 시마다 variants 조회 (오버헤드)
3. **타이밍**: Variant가 진행 중일 때 재시작하면 충돌 가능

### 개선 가능성
1. **재시작 조건 강화**: 
   - Variant가 일정 시간 이상 멈춰있는 경우만 재시작
   - Job의 current_step과 variant의 current_step 차이가 일정 이상인 경우만 재시작
2. **백오프 전략**: 
   - 재시도 간격 점진적 증가
   - 최대 재시도 횟수 제한

---

**작성일**: 2025-11-28  
**작성자**: LEEYH205  
**버전**: 1.0.0


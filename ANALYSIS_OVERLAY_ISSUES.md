# Overlay 파이프라인 문제 분석

## 📋 문제 요약

Job ID: `3204e6fe-8895-4a16-b723-18d19148f83a`

### 발견된 문제

1. **Overlay 위치 문제**: 텍스트 영역 너비가 15%로 너무 좁아서 글자가 밖으로 빠져나감
2. **Planner 자료 저장**: planner_proposals 테이블에 저장되지만 별도 이미지 asset으로는 저장되지 않음
3. **VLM Judge N/A**: quality_score/quality_assessment 키가 없어서 N/A로 표시됨
4. **OCR/Readability 평가**: 텍스트가 잘렸는데도 평가가 진행되어 부정확한 결과

---

## 🔍 상세 분석

### 1. Overlay 위치 문제

**현재 상태**:
- Variant 1, 2: `x=0.85, y=0.10, width=0.15, height=0.80` (오른쪽 끝, 너비 15%)
- Variant 3: `x=0.05, y=0.10, width=0.15, height=0.80` (왼쪽 끝, 너비 15%)
- 텍스트: "담백한 국물 한 그릇, 오늘 하루가 부드러워집니다." (28자)

**문제점**:
- 너비가 15%로 너무 좁아서 28자 텍스트가 들어가기 어려움
- 텍스트가 영역 밖으로 빠져나가거나 잘림
- Planner가 제안한 위치와 실제 Overlay 위치가 다를 수 있음

**원인 추정**:
- Planner가 제안한 위치가 좁은 영역이었거나
- Overlay 단계에서 위치 선택 로직에 문제가 있을 수 있음

---

### 2. Planner 자료 저장

**현재 상태** (업데이트됨):
- Planner Proposals: 3개 저장됨
- 저장 위치: `planner_proposals` 테이블 (JSONB 형식)
- 각 Proposal에는 `layout` JSONB에 제안 정보가 저장됨
- ✅ **해결됨**: Proposal box를 그린 이미지가 `image_assets` 테이블에 저장됨

**저장 내용**:
```json
{
  "proposals": [
    {
      "proposal_id": "...",
      "xywh": [0.0, 0.0, 1.0, 0.23],
      "source": "max_size_top_full",
      "score": 1.0
    }
  ],
  "avoid": [...],
  "min_overlay_width": 0.5,
  "min_overlay_height": 0.12,
  "proposal_image_asset_id": "...",  // 새로 추가됨
  "proposal_image_url": "/assets/yh/tenants/.../planner/..."  // 새로 추가됨
}
```

**설명**:
- ✅ Planner 자료는 `planner_proposals` 테이블에 정상 저장됨
- ✅ **해결됨**: Proposal box를 그린 이미지가 `image_assets` 테이블에 저장됨
  - 이미지 타입: `planner`
  - 저장 경로: `/assets/yh/tenants/{tenant_id}/planner/{year}/{month}/{day}/{asset_id}.png`
  - 각 Proposal box는 다른 색상으로 표시됨 (초록, 파랑, 노랑, 마젠타, 시안, 주황)
  - 금지 영역(AVOID)은 빨간색으로 표시됨
  - 각 Proposal에는 source와 score 정보가 라벨로 표시됨
- Planner는 위치 제안과 시각화 이미지를 모두 저장함

**확인 방법**:
```sql
-- Planner Proposals 조회
SELECT 
    pp.proposal_id,
    pp.image_asset_id,
    pp.layout->'proposals' as proposals,
    pp.layout->'proposal_image_asset_id' as proposal_image_asset_id,
    pp.layout->'proposal_image_url' as proposal_image_url,
    pp.created_at
FROM planner_proposals pp
INNER JOIN image_assets ia ON pp.image_asset_id = ia.image_asset_id
INNER JOIN job_inputs ji ON ia.image_asset_id = ji.img_asset_id
WHERE ji.job_id = '3204e6fe-8895-4a16-b723-18d19148f83a';

-- Proposal box 이미지 조회
SELECT 
    ia.image_asset_id,
    ia.image_type,
    ia.image_url,
    ia.width,
    ia.height,
    ia.tenant_id,
    ia.created_at
FROM image_assets ia
WHERE ia.image_type = 'planner'
  AND ia.tenant_id = 'overlay_test_tenant'
ORDER BY ia.created_at DESC;
```

**구현 내용**:
- `routers/planner.py`에 Proposal box 이미지 생성 및 저장 로직 추가
- 원본 이미지에 Proposal box를 그려서 시각화
- `save_asset()` 함수를 사용하여 이미지 저장
- `image_assets` 테이블에 `image_type='planner'`로 저장
- `planner_proposals.layout` JSONB에 `proposal_image_asset_id`와 `proposal_image_url` 추가

---

### 3. VLM Judge N/A 문제

**현재 상태**:
- VLM Judge 응답에 `quality_score`나 `quality_assessment` 키가 없음
- 대신 `analysis` 필드에 JSON 문자열이 들어있음

**응답 구조**:
```json
{
  "on_brief": true,
  "occlusion": false,
  "contrast_ok": true,
  "cta_present": false,
  "issues": [],
  "reasoning": "...",
  "analysis": "{\"on_brief\": true, \"occlusion\": false, ...}"  // JSON 문자열
}
```

**문제점**:
- `quality_score`와 `quality_assessment` 키가 최상위 레벨에 없음
- `analysis` 필드가 JSON 문자열로 저장되어 파싱이 필요함

**해결 방안**:
1. `analysis` 필드를 파싱하여 정보 추출
2. 또는 `judge_final_ad` 함수의 응답 구조를 확인하여 올바른 키 사용

**코드 확인 필요**:
- `services/llava_service.py`의 `judge_final_ad` 함수
- `routers/llava_stage2.py`의 응답 처리 로직

---

### 4. OCR/Readability 평가 문제

**현재 상태**:
- OCR 정확도: 75-78%
- Readability 점수: 28-29%
- 대비 비율: 2.59-2.62:1

**문제점**:
- 텍스트가 영역 밖으로 빠져나갔는데도 평가가 진행됨
- OCR은 잘린 텍스트를 인식하여 정확도가 낮게 나올 수 있음
- Readability는 텍스트 영역만 평가하므로, 잘린 텍스트에 대한 평가가 부정확할 수 있음

**원인**:
- Overlay 단계에서 텍스트 영역이 너무 좁아서 텍스트가 잘림
- OCR/Readability 평가는 잘린 이미지를 기준으로 평가하므로 부정확

**해결 방안**:
1. Overlay 단계에서 텍스트 영역 크기 검증 추가
2. 텍스트가 영역을 벗어나면 경고 또는 재계산
3. OCR 평가 시 텍스트 영역 검증 추가

---

## 🔧 해결 방안

### 1. Overlay 위치 문제 해결

**방안 A: Planner 제안 검증 강화**
- Planner가 제안한 위치의 너비가 최소값 이상인지 확인
- 너비가 너무 좁으면 다른 제안 선택 또는 경고

**방안 B: Overlay 단계에서 텍스트 피팅 검증**
- 텍스트가 영역에 맞지 않으면 경고 또는 재계산
- 최소 너비 요구사항 추가

**방안 C: 텍스트 길이 기반 최소 너비 계산**
- 텍스트 길이에 따라 최소 너비 자동 계산
- 예: 28자 텍스트 → 최소 30-40% 너비 필요

### 2. VLM Judge N/A 문제 해결

**방안 A: 응답 파싱 개선**
- `analysis` 필드를 파싱하여 정보 추출
- `quality_score`와 `quality_assessment`를 `analysis`에서 추출

**방안 B: 응답 구조 통일**
- `judge_final_ad` 함수의 응답 구조를 확인하여 올바른 키 사용
- 필요시 응답 구조 수정

### 3. OCR/Readability 평가 개선

**방안 A: 텍스트 영역 검증 추가**
- OCR 평가 전에 텍스트가 영역 내에 있는지 확인
- 영역을 벗어나면 경고 또는 평가 스킵

**방안 B: 평가 영역 자동 조정**
- 텍스트가 영역을 벗어나면 평가 영역 자동 확장
- 또는 텍스트 영역만 정확히 추출하여 평가

---

## 📊 현재 평가 결과 요약

### Variant 1
- **OCR**: 78.21% 정확도, 88.46% 유사도
- **Readability**: 28.76% 점수, 2.59:1 대비
- **IoU**: 0.00% (겹침 없음)
- **위치**: x=0.85, width=0.15 (너비 15%)

### Variant 2
- **OCR**: 78.21% 정확도, 88.46% 유사도
- **Readability**: 29.11% 점수, 2.62:1 대비
- **IoU**: 0.00% (겹침 없음)
- **위치**: x=0.85, width=0.15 (너비 15%)

### Variant 3
- **OCR**: 75.71% 정확도, 84.62% 유사도
- **Readability**: 28.76% 점수, 2.59:1 대비
- **IoU**: 0.00% (겹침 없음)
- **위치**: x=0.05, width=0.15 (너비 15%)

---

## 🎯 권장 사항

1. **✅ 완료**: Planner proposal box 이미지 저장 기능 추가
2. **즉시 조치**: Overlay 위치 문제 해결 (너비 15%는 너무 좁음)
3. **단기 개선**: VLM Judge 응답 파싱 개선
4. **장기 개선**: OCR/Readability 평가 시 텍스트 영역 검증 추가

---

## ✅ 해결된 사항

### Planner Proposal Box 이미지 저장 (2025-12-02)

**구현 내용**:
- Planner 단계에서 Proposal box를 그린 이미지를 자동 생성
- `image_assets` 테이블에 `image_type='planner'`로 저장
- `planner_proposals.layout` JSONB에 `proposal_image_asset_id`와 `proposal_image_url` 추가

**시각화 내용**:
- 각 Proposal box는 다른 색상으로 표시 (초록, 파랑, 노랑, 마젠타, 시안, 주황)
- 금지 영역(AVOID)은 빨간색 반투명 배경으로 표시
- 각 Proposal에는 source와 score 정보가 라벨로 표시

**사용 예시**:
```python
# Proposal box 이미지 조회
proposal_image = db.query(ImageAsset).filter(
    ImageAsset.image_type == 'planner',
    ImageAsset.tenant_id == tenant_id
).order_by(ImageAsset.created_at.desc()).first()

if proposal_image:
    print(f"Proposal box 이미지 URL: {proposal_image.image_url}")
    # 이미지 다운로드 또는 표시 가능
```

---

## 📝 추가 개선 사항

### 1. Overlay 위치 문제 해결 (우선순위: 높음)

**문제**: 텍스트 영역 너비가 15%로 너무 좁아서 텍스트가 잘림

**해결 방안**:
- Planner 제안 검증 강화: 최소 너비 요구사항 확인
- Overlay 단계에서 텍스트 피팅 검증 추가
- 텍스트 길이 기반 최소 너비 자동 계산

### 2. VLM Judge 응답 파싱 개선 (우선순위: 중간)

**문제**: `quality_score`와 `quality_assessment` 키가 없어서 N/A로 표시됨

**해결 방안**:
- `analysis` 필드를 파싱하여 정보 추출
- 응답 구조 통일 또는 파싱 로직 개선

### 3. OCR/Readability 평가 개선 (우선순위: 중간)

**문제**: 텍스트가 잘렸는데도 평가가 진행되어 부정확한 결과

**해결 방안**:
- 텍스트 영역 검증 추가
- 평가 영역 자동 조정 또는 경고 메시지

---

**작성일**: 2025-12-02  
**최종 업데이트**: 2025-12-02 (Planner proposal box 이미지 저장 기능 추가)  
**작성자**: LEEYH205


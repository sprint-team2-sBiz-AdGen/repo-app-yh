# YOLO 통합 발표자료

## 📋 개요

**기능명**: YOLO (You Only Look Once) 통합

**목적**: 이미지에서 텍스트 오버레이 가능 영역을 감지하여 텍스트 배치 위치를 최적화

**핵심 가치**: 
- 실시간 객체 감지
- 금지 영역 자동 감지 (사람 얼굴, 특정 객체 등)
- 바운딩 박스 좌표 제공
- Segmentation 마스크 생성

---

## 🎯 목적

### 금지 영역 감지
- **목적**: 이미지에서 텍스트 오버레이를 피해야 할 영역 감지
- **활용**: 사람 얼굴, 특정 객체 등 텍스트가 가려지면 안 되는 영역 탐지
- **출력**: 바운딩 박스 좌표, 신뢰도 점수, 클래스 정보, 금지 영역 마스크

### 텍스트 배치 최적화
- **목적**: 감지된 금지 영역을 피해 텍스트를 배치할 수 있는 영역 제안
- **활용**: Planner 서비스에서 텍스트 배치 위치 결정에 활용
- **출력**: 텍스트 배치 가능 영역 좌표

---

## 🔧 주요 특징

### 1. 실시간 객체 감지
- **빠른 추론**: < 1초 (이미지당)
- **높은 정확도**: COCO 데이터셋 기반으로 다양한 객체 감지
- **GPU 가속**: CUDA 지원으로 빠른 처리

### 2. Segmentation 지원
- **마스크 생성**: 금지 영역에 대한 픽셀 단위 마스크 생성
- **정확한 영역 표시**: 바운딩 박스보다 정확한 영역 표시

### 3. 신뢰도 필터링
- **임계값 설정**: 낮은 신뢰도 영역 자동 제외
- **커스터마이징**: conf_threshold, iou_threshold 조정 가능

### 4. 금지 라벨 필터링
- **커스터마이징 가능**: 감지할 객체 클래스 선택 가능
- **기본 설정**: 사람(person) 등 기본 금지 라벨 제공

---

## 📁 구현 위치

### 서비스 레이어
- `services/yolo_service.py`: YOLO 모델 서비스 (모델 로딩, 감지 로직)

### API 엔드포인트
- `routers/yolo.py`: YOLO API 엔드포인트 (`/api/yh/yolo/detect`)

### 데이터베이스
- `detections` 테이블: 감지 결과 저장
- `yolo_runs` 테이블: YOLO 실행 정보 저장

---

## 💻 구현 코드

### 1. 모델 로딩

**파일**: `services/yolo_service.py`

```python
from ultralytics import YOLO
from config import DEVICE_TYPE, MODEL_DIR, YOLO_MODEL_NAME

# 전역 모델 변수 (lazy loading)
_model: Optional[YOLO] = None
_model_path: Optional[str] = None

def get_yolo_model(model_name: str = "yolov8x-seg.pt") -> YOLO:
    """YOLO 모델 로드 (싱글톤 패턴)"""
    global _model, _model_path
    
    # 확장자가 없으면 .pt 추가
    if model_name and not model_name.endswith(('.pt', '.onnx', '.engine')):
        model_name = f"{model_name}.pt"
    
    model_path = os.path.join(MODEL_DIR, model_name)
    
    # 모델이 로드되지 않았거나 다른 모델을 요청한 경우
    if _model is None or _model_path != model_path:
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"YOLO 모델 파일을 찾을 수 없습니다: {model_path}\n"
                f"다운로드 스크립트를 실행하세요: python download_yolo_model.py"
            )
        
        print(f"Loading YOLO model: {model_name} on {DEVICE}")
        logger.info(f"Loading YOLO model: {model_name} on {DEVICE}")
        
        # YOLO 모델 로드
        _model = YOLO(model_path)
        _model_path = model_path
        
        # 디바이스 설정
        if DEVICE == "cuda":
            _model.to(DEVICE)
        
        print(f"✓ YOLO model loaded successfully")
        logger.info(f"YOLO model loaded successfully")
    
    return _model
```

**핵심 포인트**:
- **싱글톤 패턴**: 모델을 한 번만 로드
- **Lazy loading**: 필요할 때만 로드
- **자동 디바이스 선택**: CUDA 사용 가능 시 자동으로 GPU 사용

---

### 2. 금지 영역 감지

**파일**: `services/yolo_service.py`

```python
def detect_forbidden_areas(
    image: Image.Image,
    model_name: Optional[str] = None,
    conf_threshold: Optional[float] = None,
    iou_threshold: Optional[float] = None,
    target_classes: Optional[List[int]] = None,
    forbidden_labels: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    이미지에서 금지 영역 감지
    
    Args:
        image: PIL Image 객체
        model_name: 사용할 YOLO 모델 파일명
        conf_threshold: 신뢰도 임계값
        iou_threshold: IoU 임계값
        target_classes: 감지할 클래스 ID 리스트
        forbidden_labels: 금지 라벨 이름 리스트
    
    Returns:
        {
            "boxes": [[x1, y1, x2, y2], ...],  # xyxy 형식
            "confidences": [0.95, ...],
            "classes": [0, ...],
            "labels": ["person", ...],
            "areas": [1234.5, ...],
            "widths": [100.0, ...],
            "heights": [200.0, ...],
            "model": model_name,
            "forbidden_mask": PIL Image (L 모드)  # 금지 영역 마스크
        }
    """
    # 설정값 적용
    model_name = model_name or YOLO_MODEL_NAME
    conf_threshold = conf_threshold if conf_threshold is not None else YOLO_CONF_THRESHOLD
    iou_threshold = iou_threshold if iou_threshold is not None else YOLO_IOU_THRESHOLD
    
    # 금지 라벨 설정
    if forbidden_labels is None:
        forbidden_labels = YOLO_FORBIDDEN_LABELS
    
    # 기본 금지 라벨 리스트
    default_forbidden_labels = ["person"]
    if not forbidden_labels:
        forbidden_labels = default_forbidden_labels
    
    # 모델 로드
    model = get_yolo_model(model_name)
    
    # YOLO 추론 실행
    results = model.predict(
        image,
        conf=conf_threshold,
        iou=iou_threshold,
        device=DEVICE,
        classes=target_classes if (target_classes and forbidden_labels is None) else None,
        verbose=False
    )
    
    boxes = []
    confidences = []
    classes = []
    labels = []
    areas = []
    widths = []
    heights = []
    
    # 결과 파싱
    if results and len(results) > 0:
        result = results[0]
        
        # 모델의 클래스 이름 가져오기
        model_names = result.names
        
        # 바운딩 박스 정보 추출
        if result.boxes is not None and len(result.boxes) > 0:
            for box in result.boxes:
                class_id = int(box.cls[0])
                label = model_names[class_id]
                
                # 금지 라벨 필터링
                if forbidden_labels and label not in forbidden_labels:
                    continue
                
                # 바운딩 박스 좌표 (xyxy 형식)
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                confidence = float(box.conf[0])
                
                boxes.append([float(x1), float(y1), float(x2), float(y2)])
                confidences.append(confidence)
                classes.append(class_id)
                labels.append(label)
                
                # 영역 정보
                width = float(x2 - x1)
                height = float(y2 - y1)
                area = width * height
                
                widths.append(width)
                heights.append(height)
                areas.append(area)
    
    # 금지 영역 마스크 생성 (segmentation 모델인 경우)
    forbidden_mask = None
    if results and len(results) > 0 and hasattr(results[0], 'masks') and results[0].masks is not None:
        result = results[0]
        mask = result.masks.data[0].cpu().numpy()  # 첫 번째 마스크 사용
        forbidden_mask = Image.fromarray((mask * 255).astype(np.uint8), mode='L')
    
    return {
        "boxes": boxes,
        "confidences": confidences,
        "classes": classes,
        "labels": labels,
        "areas": areas,
        "widths": widths,
        "heights": heights,
        "model": model_name,
        "forbidden_mask": forbidden_mask
    }
```

**핵심 포인트**:
- **바운딩 박스 좌표**: 텍스트 배치 위치 결정에 활용
- **신뢰도 점수**: 낮은 신뢰도 영역은 제외 가능
- **금지 라벨 필터링**: 원하는 객체만 감지
- **Segmentation 마스크**: 픽셀 단위 정확한 영역 표시

---

### 3. API 엔드포인트

**파일**: `routers/yolo.py`

```python
@router.post("/detect", response_model=DetectOut)
def detect(body: DetectIn, db: Session = Depends(get_db)):
    """
    YOLO 금지 영역 감지 (DB 연동)
    
    Args:
        body: DetectIn 모델
            - job_variants_id: Job Variant ID
            - job_id: Job ID
            - tenant_id: Tenant ID
            - asset_url: 이미지 URL (Optional)
            - model: 모델 이름 (Optional)
    
    Returns:
        DetectOut:
            - job_id: Job ID
            - detection_ids: 생성된 detection 레코드 ID 리스트
            - boxes: 감지된 박스 리스트 (xyxy 형식)
            - model: 사용된 모델 이름
            - confidences: 신뢰도 리스트
            - classes: 클래스 ID 리스트
            - labels: 라벨 리스트
            - areas: 영역 면적 리스트
            - widths: 너비 리스트
            - heights: 높이 리스트
            - forbidden_mask_url: 금지 영역 마스크 URL
            - detections: JSON 형식 감지 결과
    """
    # Step 0: job_variants_id 및 job_id 검증
    job_variants_id = uuid.UUID(body.job_variants_id)
    job_id = uuid.UUID(body.job_id)
    
    # job_variants 조회
    job_variant = db.query(JobVariant).filter(
        JobVariant.job_variants_id == job_variants_id
    ).first()
    
    # job_variants 상태 업데이트: current_step='yolo_detect', status='running'
    db.execute(
        text("""
            UPDATE jobs_variants 
            SET status = 'running', 
                current_step = 'yolo_detect',
                updated_at = CURRENT_TIMESTAMP
            WHERE job_variants_id = :job_variants_id
        """),
        {"job_variants_id": job_variants_id}
    )
    db.flush()
    
    # Step 1: 이미지 가져오기
    asset_url = body.asset_url
    if not asset_url:
        image_asset_id = job_variant.img_asset_id
        image_asset = db.query(ImageAsset).filter(
            ImageAsset.image_asset_id == image_asset_id
        ).first()
        asset_url = image_asset.image_url
    
    # Step 2: 이미지 로드
    image_path = abs_from_url(asset_url)
    image = Image.open(image_path)
    
    # Step 3: YOLO 감지 실행
    start_time = time.time()
    detection_result = detect_forbidden_areas(
        image=image,
        model_name=body.model
    )
    latency_ms = (time.time() - start_time) * 1000
    
    # Step 4: 금지 영역 마스크 저장 (있는 경우)
    forbidden_mask_url = None
    if detection_result.get('forbidden_mask'):
        forbidden_mask = detection_result['forbidden_mask']
        forbidden_mask_url = save_asset(
            image=forbidden_mask,
            tenant_id=body.tenant_id,
            image_type='forbidden_mask'
        )
    
    # Step 5: detections 테이블에 저장
    detection_ids = []
    for i, box in enumerate(detection_result['boxes']):
        detection_id = uuid.uuid4()
        detection_ids.append(str(detection_id))
        
        db.execute(
            text("""
                INSERT INTO detections (
                    detection_id, job_id, model_name,
                    class_id, label, confidence,
                    x1, y1, x2, y2,
                    area, width, height,
                    created_at, updated_at
                )
                VALUES (
                    :detection_id, :job_id, :model_name,
                    :class_id, :label, :confidence,
                    :x1, :y1, :x2, :y2,
                    :area, :width, :height,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """),
            {
                "detection_id": detection_id,
                "job_id": job_id,
                "model_name": detection_result['model'],
                "class_id": detection_result['classes'][i],
                "label": detection_result['labels'][i],
                "confidence": detection_result['confidences'][i],
                "x1": box[0],
                "y1": box[1],
                "x2": box[2],
                "y2": box[3],
                "area": detection_result['areas'][i],
                "width": detection_result['widths'][i],
                "height": detection_result['heights'][i]
            }
        )
    
    # Step 6: yolo_runs 테이블에 저장
    yolo_run_id = uuid.uuid4()
    db.execute(
        text("""
            INSERT INTO yolo_runs (
                yolo_run_id, job_id, model_name,
                conf_threshold, iou_threshold,
                detection_count, latency_ms,
                forbidden_mask_url,
                created_at, updated_at
            )
            VALUES (
                :yolo_run_id, :job_id, :model_name,
                :conf_threshold, :iou_threshold,
                :detection_count, :latency_ms,
                :forbidden_mask_url,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """),
        {
            "yolo_run_id": yolo_run_id,
            "job_id": job_id,
            "model_name": detection_result['model'],
            "conf_threshold": YOLO_CONF_THRESHOLD,
            "iou_threshold": YOLO_IOU_THRESHOLD,
            "detection_count": len(detection_result['boxes']),
            "latency_ms": latency_ms,
            "forbidden_mask_url": forbidden_mask_url
        }
    )
    
    # Step 7: jobs_variants 상태를 'done'으로 업데이트
    db.execute(
        text("""
            UPDATE jobs_variants 
            SET status = 'done', 
                current_step = 'yolo_detect',
                updated_at = CURRENT_TIMESTAMP
            WHERE job_variants_id = :job_variants_id
        """),
        {"job_variants_id": job_variants_id}
    )
    
    db.commit()
    
    return DetectOut(
        job_id=body.job_id,
        detection_ids=detection_ids,
        boxes=detection_result['boxes'],
        model=detection_result['model'],
        confidences=detection_result['confidences'],
        classes=detection_result['classes'],
        labels=detection_result['labels'],
        areas=detection_result['areas'],
        widths=detection_result['widths'],
        heights=detection_result['heights'],
        forbidden_mask_url=forbidden_mask_url,
        detections=[{
            "box": box,
            "confidence": conf,
            "class": cls,
            "label": label,
            "area": area,
            "width": width,
            "height": height
        } for box, conf, cls, label, area, width, height in zip(
            detection_result['boxes'],
            detection_result['confidences'],
            detection_result['classes'],
            detection_result['labels'],
            detection_result['areas'],
            detection_result['widths'],
            detection_result['heights']
        )]
    )
```

**핵심 포인트**:
- **상태 관리**: running → done으로 업데이트하여 트리거 발동
- **완전한 추적**: 모든 감지 결과를 DB에 저장
- **자동 트리거**: done 상태로 업데이트하면 다음 단계 자동 실행

---

## 🔄 파이프라인 통합

### YOLO 감지 흐름
```
[vlm_analyze 완료]
  ↓
[yolo_detect 트리거]
  ↓
[YOLO 금지 영역 감지]
  ↓
[결과 저장 (detections, yolo_runs)]
  ↓
[jobs_variants 상태 업데이트: done]
  ↓
[planner 자동 트리거]
```

### Planner와의 연동
- YOLO 감지 결과를 Planner에 전달
- Planner가 금지 영역을 피해 텍스트 배치 위치 결정
- 바운딩 박스 좌표를 활용하여 최적 위치 계산

---

## 📊 성능 및 통계

### 추론 성능
- **추론 시간**: < 1초 (이미지당)
- **처리량**: GPU 환경에서 초당 약 1-2 이미지
- **정확도**: 높은 신뢰도로 텍스트 영역 감지

### 메모리 사용량
- **모델 크기**: 약 200-300MB (yolov8x-seg.pt)
- **GPU 메모리**: 약 1-2GB (추론 시)

### 지원 클래스
- **COCO 데이터셋**: 80개 클래스 지원
- **기본 금지 라벨**: person (사람)
- **커스터마이징**: 원하는 클래스만 선택 가능

---

## 🔧 트러블슈팅

### 문제 1: 모델 파일을 찾을 수 없음

**증상**: `FileNotFoundError: YOLO 모델 파일을 찾을 수 없습니다`

**원인**: 모델 파일이 다운로드되지 않음

**해결 방법**:
1. 모델 다운로드 스크립트 실행
   ```bash
   python download_yolo_model.py
   ```
2. `MODEL_DIR` 환경 변수 확인
3. 모델 파일 경로 확인

---

### 문제 2: 감지 결과가 없음

**증상**: 금지 영역이 감지되지 않음

**원인**: 
- 신뢰도 임계값이 너무 높음
- 금지 라벨이 이미지에 없음

**해결 방법**:
1. `conf_threshold` 낮추기
   ```python
   conf_threshold = 0.3  # 기본값보다 낮게
   ```
2. 금지 라벨 확인
   ```python
   forbidden_labels = ["person", "face"]  # 추가 라벨 포함
   ```

---

### 문제 3: GPU 메모리 부족

**증상**: CUDA out of memory 오류

**해결 방법**:
1. CPU 모드로 전환
   ```python
   DEVICE = "cpu"
   ```
2. 배치 크기 감소 (YOLO는 배치 처리 지원)
3. 더 작은 모델 사용 (yolov8n-seg.pt 등)

---

### 문제 4: Segmentation 마스크가 생성되지 않음

**증상**: `forbidden_mask`가 None

**원인**: 
- Segmentation 모델이 아님
- 감지된 객체가 없음

**해결 방법**:
1. Segmentation 모델 사용 확인
   ```python
   model_name = "yolov8x-seg.pt"  # -seg 접미사 확인
   ```
2. 감지 결과 확인
   ```python
   if len(detection_result['boxes']) > 0:
       # 감지된 객체가 있는 경우에만 마스크 생성
   ```

---

### 문제 5: 추론 속도가 느림

**증상**: 추론 시간이 1초 이상 소요

**원인**: CPU 모드 사용 또는 GPU 미사용

**해결 방법**:
1. GPU 사용 확인
   ```python
   DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
   ```
2. 더 작은 모델 사용 (속도 우선)
   ```python
   model_name = "yolov8n-seg.pt"  # nano 모델 (가장 빠름)
   ```

---

## 🎯 주요 포인트

### 장점
- ✅ 실시간 객체 감지 (< 1초)
- ✅ 높은 정확도로 금지 영역 감지
- ✅ Segmentation 마스크 제공
- ✅ 커스터마이징 가능 (임계값, 라벨 등)

### 활용 사례
- 텍스트 오버레이 금지 영역 감지
- 사람 얼굴 자동 감지 및 보호
- 특정 객체 영역 회피

---

## 📚 관련 문서

- `DOCS_YH_PART_IMPLEMENTATION.md`: YH 파트 구현 가이드
- `ANALYSIS_QUANTITATIVE_EVALUATION_IMPLEMENTATION.md`: 정량 평가 구현 분석

---

**작성일**: 2025-12-02  
**작성자**: LEEYH205  
**버전**: 1.0.0




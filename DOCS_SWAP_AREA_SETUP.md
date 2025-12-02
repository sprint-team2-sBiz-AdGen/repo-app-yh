# Swap Area 설정 가이드

## 📋 개요

**목적**: 메모리 부족 문제 해결을 위한 Swap Area 설정

**작성일**: 2025-12-02  
**작성자**: LEEYH205  
**버전**: 1.0.0

---

## 🎯 목적

LLaVA 모델과 같은 대용량 AI 모델을 실행할 때 메모리 부족 문제가 발생할 수 있습니다. Swap Area를 설정하여 디스크 공간을 메모리처럼 사용할 수 있도록 합니다.

**사용 시나리오**:
- LLaVA 모델 로딩 시 메모리 부족
- 여러 variants 동시 실행 시 메모리 부족
- GPU 메모리와 시스템 메모리 모두 부족한 경우

---

## 📁 관련 파일

### 설정 스크립트
- **위치**: `/home/leeyoungho/setup_swap.sh`
- **기능**: 32GB swap 파일 생성 및 설정

### Swap 파일
- **위치**: `/swapfile`
- **크기**: 32GB
- **상태**: 활성화됨

---

## 🔧 현재 설정 상태

### Swap 파일 정보
```
파일 경로: /swapfile
크기: 32GB
사용량: 약 4.6GB (현재)
사용 가능: 약 27GB
```

### 시스템 메모리 상태
```
총 메모리: 15GB
사용 중: 4.4GB
여유: 2.9GB
Swap: 31GB (4.6GB 사용 중)
```

### Swappiness 설정
```
현재 값: 10 (권장값)
설명: 메모리 사용률이 90% 이상일 때 swap 사용 시작
```

---

## 🚀 Swap Area 설정 방법

### 방법 1: 자동 스크립트 사용 (권장)

**스크립트 위치**: `/home/leeyoungho/setup_swap.sh`

```bash
# 스크립트 실행
bash /home/leeyoungho/setup_swap.sh
```

**스크립트 동작**:
1. 기존 swap 파일 확인 및 삭제 (선택)
2. 디스크 공간 확인 (최소 40GB 필요)
3. 32GB swap 파일 생성
4. 권한 설정 (600)
5. Swap 포맷
6. Swap 활성화
7. `/etc/fstab`에 추가 (부팅 시 자동 활성화)
8. Swappiness 설정 (10으로 설정)

---

### 방법 2: 수동 설정

#### 1. 디스크 공간 확인

```bash
df -h /
```

**요구사항**: 최소 40GB 여유 공간 필요

#### 2. Swap 파일 생성

```bash
# 32GB swap 파일 생성
sudo fallocate -l 32G /swapfile

# 또는 dd 명령어 사용 (fallocate가 없는 경우)
sudo dd if=/dev/zero of=/swapfile bs=1G count=32
```

#### 3. 권한 설정

```bash
# 보안을 위해 권한 제한
sudo chmod 600 /swapfile
```

#### 4. Swap 포맷

```bash
sudo mkswap /swapfile
```

#### 5. Swap 활성화

```bash
sudo swapon /swapfile
```

#### 6. 부팅 시 자동 활성화 설정

```bash
# /etc/fstab에 추가
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

#### 7. Swappiness 설정 (선택사항, 권장)

```bash
# 현재 값 확인
cat /proc/sys/vm/swappiness

# 임시 설정 (재부팅 시 초기화됨)
sudo sysctl vm.swappiness=10

# 영구 설정
echo "vm.swappiness=10" | sudo tee -a /etc/sysctl.conf
```

---

## 📊 Swap 설정 확인

### Swap 상태 확인

```bash
# Swap 사용량 확인
free -h

# Swap 파일 정보 확인
swapon --show

# 또는
cat /proc/swaps
```

**예상 출력**:
```
               total        used        free      shared  buff/cache   available
Mem:            15Gi       4.4Gi       2.9Gi        17Mi       8.3Gi        10Gi
Swap:           31Gi       4.6Gi        27Gi
```

### Swappiness 확인

```bash
cat /proc/sys/vm/swappiness
# 예상 출력: 10
```

### fstab 설정 확인

```bash
cat /etc/fstab | grep swap
# 예상 출력: /swapfile none swap sw 0 0
```

---

## ⚙️ Swappiness 설정 설명

### Swappiness란?

Swappiness는 시스템이 메모리 부족 시 swap을 얼마나 적극적으로 사용할지 결정하는 값입니다.

**값 범위**: 0-100

**의미**:
- **0**: swap을 거의 사용하지 않음 (메모리가 거의 다 찰 때만 사용)
- **10**: 권장값 (메모리 사용률 90% 이상일 때 swap 사용)
- **60**: 기본값 (메모리 사용률 40% 이상일 때 swap 사용)
- **100**: 매우 적극적으로 swap 사용

### 권장 설정

**AI 모델 실행 환경**: `10` (권장)

**이유**:
- 메모리가 충분할 때는 swap을 사용하지 않아 성능 유지
- 메모리 부족 시에만 swap 사용하여 OOM(Out of Memory) 방지
- Swap은 디스크 I/O이므로 느리지만, OOM보다는 나음

---

## 🔍 문제 해결

### 문제 1: Swap 파일 생성 실패

**증상**: `fallocate: cannot allocate memory` 오류

**원인**: 디스크 공간 부족

**해결 방법**:
1. 디스크 공간 확인
   ```bash
   df -h /
   ```
2. 불필요한 파일 삭제
3. 더 작은 swap 파일 생성 (예: 16GB)

---

### 문제 2: Swap이 활성화되지 않음

**증상**: `swapon: /swapfile: swapon failed: Invalid argument`

**원인**: Swap 파일이 제대로 포맷되지 않음

**해결 방법**:
```bash
# Swap 파일 재포맷
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

### 문제 3: 부팅 후 Swap이 비활성화됨

**증상**: 재부팅 후 swap이 사라짐

**원인**: `/etc/fstab`에 설정되지 않음

**해결 방법**:
```bash
# fstab에 추가
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 재부팅 후 확인
sudo reboot
swapon --show
```

---

### 문제 4: Swap 사용량이 너무 많음

**증상**: Swap 사용량이 계속 증가

**원인**: 
- 실제 메모리 부족
- Swappiness 값이 너무 높음

**해결 방법**:
1. 실제 메모리 사용량 확인
   ```bash
   free -h
   ps aux --sort=-%mem | head -10
   ```
2. Swappiness 값 낮추기
   ```bash
   sudo sysctl vm.swappiness=10
   ```
3. 메모리 사용량이 많은 프로세스 확인 및 종료

---

### 문제 5: Swap 파일 삭제

**Swap 비활성화 및 삭제**:

```bash
# Swap 비활성화
sudo swapoff /swapfile

# fstab에서 제거
sudo sed -i '/swapfile/d' /etc/fstab

# Swap 파일 삭제
sudo rm /swapfile
```

---

## 📈 성능 영향

### Swap 사용 시 성능

**장점**:
- OOM(Out of Memory) 오류 방지
- 더 많은 프로세스 동시 실행 가능
- 시스템 안정성 향상

**단점**:
- 디스크 I/O로 인한 성능 저하 (메모리보다 느림)
- 디스크 공간 사용

**권장사항**:
- Swap은 최후의 수단으로 사용
- 가능하면 실제 메모리를 늘리는 것이 좋음
- Swappiness를 낮게 설정하여 swap 사용 최소화

---

## 🎯 모범 사례

### 1. Swap 크기 결정

**권장 공식**:
- RAM < 2GB: Swap = RAM × 2
- RAM 2-8GB: Swap = RAM
- RAM > 8GB: Swap = 8-16GB (충분)

**현재 설정**: 32GB (충분함)

### 2. Swappiness 설정

**AI 모델 실행 환경**: `10` (권장)

**이유**: 
- 메모리가 충분할 때는 swap 사용 안 함
- 메모리 부족 시에만 swap 사용

### 3. 모니터링

**정기적으로 확인할 사항**:
```bash
# Swap 사용량 확인
free -h

# Swap I/O 확인
iostat -x 1

# 메모리 사용량이 많은 프로세스 확인
ps aux --sort=-%mem | head -10
```

---

## 📚 관련 문서

- `presentation/02-1_LLAVA_INTEGRATION.md`: LLaVA 통합 문서 (메모리 최적화 관련)
- `setup_swap.sh`: Swap 설정 스크립트

---

## 🔄 업데이트 이력

- **v1.0.0** (2025-12-02): 초기 문서 작성

---

**참고**: 
- Swap은 디스크 공간을 사용하므로 디스크 여유 공간을 확인하세요.
- Swap 사용 시 성능 저하가 발생할 수 있으므로, 가능하면 실제 메모리를 늘리는 것을 권장합니다.
- 현재 설정된 32GB swap은 충분한 크기입니다.


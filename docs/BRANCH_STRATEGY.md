# Git 브랜치 전략

## 브랜치 구조

### 주요 브랜치
- **main**: 프로덕션 배포용 브랜치 (안정 버전만 유지)
- **develop**: 개발 통합 브랜치 (모든 기능 개발의 기본 브랜치)

### 보조 브랜치
- **feature/***: 기능 개발 브랜치
  - 예: `feature/llava-integration`, `feature/overlay-layouts`
  - `develop` 브랜치에서 생성
  - 완료 후 `develop`로 병합

## 워크플로우

### 1. 새 기능 개발 시작
```bash
# develop 브랜치로 이동
git checkout develop
git pull origin develop

# 새 feature 브랜치 생성
git checkout -b feature/기능명

# 작업 후 커밋
git add .
git commit -m "feat: 기능 설명"
```

### 2. 기능 개발 완료 후 병합
```bash
# develop 브랜치로 이동
git checkout develop
git pull origin develop

# feature 브랜치 병합
git merge feature/기능명

# 원격 저장소에 푸시
git push origin develop

# feature 브랜치 삭제 (선택사항)
git branch -d feature/기능명
```

### 3. 프로덕션 배포
```bash
# main 브랜치로 이동
git checkout main
git pull origin main

# develop 브랜치 병합
git merge develop

# 태그 생성 (선택사항)
git tag -a v1.0.0 -m "Release version 1.0.0"

# 원격 저장소에 푸시
git push origin main
git push origin --tags
```

## 커밋 메시지 규칙

- `feat`: 새로운 기능 추가
- `fix`: 버그 수정
- `docs`: 문서 수정
- `style`: 코드 포맷팅, 세미콜론 누락 등
- `refactor`: 코드 리팩토링
- `test`: 테스트 코드 추가/수정
- `chore`: 빌드 업무 수정, 패키지 매니저 설정 등

예시:
```
feat: LLaVA 모델 통합 기능 추가
fix: overlay 레이아웃 렌더링 버그 수정
docs: README 업데이트
```

## 브랜치 네이밍 규칙

- **feature/**: `feature/기능명` (소문자, 하이픈 사용)
  - 예: `feature/llava-stage1`, `feature/model-download`
- **hotfix/**: 긴급 버그 수정 (main에서 직접 분기)
- **release/**: 릴리스 준비 (develop에서 분기)


# DART 기업공시정보 조회 웹 앱

FastAPI + 단일 HTML 페이지로 만든 DART 전자공시 조회 웹 앱입니다.

## 기능

- 회사명 검색 (부분일치, 상장사 우선)
- 기업개황 (대표자/주소/홈페이지/설립일 등)
- 공시 목록 (기간/유형 필터)
- 재무제표 (개별/연결, 사업/반기/분기)
- 최대주주 현황
- 임원 현황

## 실행 방법

### 1. DART API 키 발급
- https://opendart.fss.or.kr → 회원가입 → 인증키 신청 (무료, 일 20,000건)

### 2. 의존성 설치
```bash
cd dart-web-app
python -m venv venv
# Windows
.\venv\Scripts\activate
# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. API 키 환경변수 설정 후 실행

**Windows (PowerShell):**
```powershell
$env:DART_API_KEY="발급받은_40자리_키"
uvicorn app:app --reload --port 8000
```

**Windows (cmd):**
```cmd
set DART_API_KEY=발급받은_40자리_키
uvicorn app:app --reload --port 8000
```

**Mac/Linux:**
```bash
export DART_API_KEY=발급받은_40자리_키
uvicorn app:app --reload --port 8000
```

### 4. 브라우저 접속
http://localhost:8000

## 디렉토리 구조

```
dart-web-app/
├── app.py                 # FastAPI 서버 (DART API 프록시)
├── requirements.txt
├── static/
│   └── index.html         # SPA 형태의 단일 HTML 페이지
└── README.md
```

## 주의

- 비상장회사는 재무제표/최대주주/임원 정보가 제공되지 않을 수 있습니다.
- 재무제표는 정기보고서 제출 후 일정 시간 뒤에 반영됩니다.

## 자동 배포

이 리포지토리는 Vercel과 연결되어 있어 `main` 브랜치에 푸시 시 자동 재배포됩니다.
- Production: https://dart-disclosure.vercel.app

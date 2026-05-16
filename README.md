# 💰 재무 대시보드

Supabase + Streamlit Cloud 기반 개인 재무 트래킹 앱

---

## 🚀 배포 가이드 (총 4단계, 약 20분)

---

### STEP 1 — Supabase 프로젝트 생성

1. [supabase.com](https://supabase.com) → **Start your project** (무료)
2. GitHub 계정으로 로그인
3. **New project** 클릭
   - Name: `finance-dashboard` (아무거나)
   - Password: 강력한 비밀번호 설정
   - Region: **Northeast Asia (Seoul)** 선택
4. 프로젝트 생성까지 약 1분 대기

---

### STEP 2 — 테이블 생성 + 기존 데이터 마이그레이션

#### 2-1. 테이블 생성
1. Supabase 대시보드 → 왼쪽 메뉴 **SQL Editor**
2. `supabase_setup.sql` 파일 내용을 전체 복사 → 붙여넣기 → **Run**
3. 왼쪽 **Table Editor**에서 `finance_monthly` 테이블이 생성됐는지 확인

#### 2-2. API 키 확인
1. 왼쪽 메뉴 **Project Settings → API**
2. 아래 두 값을 메모해 두세요:
   - **Project URL**: `https://xxxx.supabase.co`
   - **anon public key**: `eyJhbG...` (긴 문자열)

#### 2-3. 기존 데이터 마이그레이션 (선택)
```bash
# 1. 구글 스프레드시트 → 파일 → 다운로드 → CSV (.csv) 저장
#    파일 이름을 data.csv 로 변경하여 이 폴더에 넣기

# 2. 패키지 설치
pip install supabase pandas

# 3. 마이그레이션 실행
python migrate.py
# → Supabase URL, anon key, CSV 파일 경로 입력하면 자동 업로드
```

---

### STEP 3 — GitHub에 코드 올리기

```bash
# 이 폴더에서 실행
git init
git add .
git commit -m "Initial commit: 재무 대시보드"

# GitHub에서 새 저장소(repository) 생성 후:
git remote add origin https://github.com/YOUR_USERNAME/finance-dashboard.git
git branch -M main
git push -u origin main
```

> ✅ `.gitignore` 덕분에 `secrets.toml`은 자동으로 제외됩니다 (API 키 안전)

---

### STEP 4 — Streamlit Cloud 배포

1. [share.streamlit.io](https://share.streamlit.io) → GitHub으로 로그인
2. **Create app** 클릭
3. 설정:
   - Repository: `YOUR_USERNAME/finance-dashboard`
   - Branch: `main`
   - Main file path: `app.py`
4. **Advanced settings** → **Secrets** 탭에 아래 내용 입력:

```toml
SUPABASE_URL = "https://xxxxxxxxxxxx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

5. **Deploy!** → 약 2분 후 앱 URL 발급 🎉

---

## 📁 파일 구조

```
finance-dashboard/
├── app.py                           # 메인 Streamlit 앱
├── migrate.py                       # 구글 시트 → Supabase 마이그레이션
├── supabase_setup.sql               # DB 테이블 생성 SQL
├── requirements.txt                 # Python 패키지
├── .gitignore                       # secrets.toml 제외
├── .streamlit/
│   └── secrets.toml.template        # 시크릿 템플릿 (실제 키 없음)
└── README.md
```

---

## 💡 이후 사용법

- **매월 말**: 앱 접속 → 📝 데이터 입력 → 원본 항목만 입력 → 저장
- 파생 지표(자산합계, 부채비율, YTD 등)는 자동 계산
- 📊 대시보드에서 차트 자동 업데이트

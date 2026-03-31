# Google Cloud에서 상시 실행 (저비용)

로컬 PC를 끄면 Streamlit 프로세스도 같이 종료됩니다. **항상 켜진 VM**에 올리면 24시간 접속·자동 새로고침이 유지됩니다.

## 비용이 낮은 선택 (권장 순)

### 1) Compute Engine `e2-micro` (가장 흔한 “저비용 상시”)

- 일부 계정/리전에서는 **월 744시간 무료(Always Free)** 로 1대 운영 가능합니다. (계정·리전 조건은 [공식 문서](https://cloud.google.com/free/docs/free-cloud-features#compute) 확인)
- 무료 조건이 아니어도 월 수천~1만 원대(리전·할인·사용량)로 작은 VM을 쓰는 경우가 많습니다.

**준비물**

- Google Cloud 프로젝트, 결제 계정 연결
- `gcloud` CLI (선택) 또는 웹 콘솔

**콘솔에서 VM 만들기 (요약)**

1. [Compute Engine → VM 인스턴스](https://console.cloud.google.com/compute/instances) → **인스턴스 만들기**
2. 머신 유형: **e2-micro** (또는 e2-small — 여유가 필요하면)
3. 부팅 디스크: **Ubuntu 22.04 LTS**, 디스크 10~20GB
4. 방화벽: **HTTP 트래픽 허용** 체크(또는 아래에서 8501 규칙 추가)
5. 생성 후 **SSH**로 접속

**VM에서 Docker로 실행 (권장)**

```bash
sudo apt-get update && sudo apt-get install -y docker.io git
sudo usermod -aG docker "$USER"
# 로그아웃 후 다시 SSH 접속 (docker 그룹 적용)

git clone https://github.com/hanseo8/ai-trading-dashboard-by-SHS.git
cd ai-trading-dashboard-by-SHS
docker build -t streamlit-dash .
```

**포트 8501 방화벽 (GCP + VM)**

- VPC 네트워크 → 방화벽 규칙 → **tcp:8501** 인바운드 허용 (소스: `0.0.0.0/0`는 편하지만 보안상 IP 제한 권장)
- 또는 **IAP 터널** / **리버스 프록시(Nginx)+HTTPS** 로 잠그는 것을 권장

**재부팅 후에도 자동 기동**

```bash
docker run -d --name streamlit-dash --restart=always -p 8501:8501 \
  -v "$(pwd)/data:/app/data" \
  streamlit-dash
```

> 컨테이너 안의 `portfolio*.json` 등을 유지하려면 위처럼 **볼륨 마운트**를 쓰고, 필요 시 `Dockerfile`에서 해당 경로를 쓰도록 앱을 조정하세요. (현재 이미지는 `WORKDIR /app` 기준으로 로컬과 동일 파일명 사용)

**브라우저 접속**

`http://<VM_외부_IP>:8501`

---

### 2) Cloud Run (요청 기반 — “진짜 24/7 고정”은 비용↑)

- Streamlit은 **WebSocket/장시간 연결**이 있어 Cloud Run에서 **최소 인스턴스 0**이면 세션이 끊기기 쉽습니다.
- **항상 켜두려면 최소 인스턴스 ≥ 1** → 월 고정비가 생깁니다.
- 그래서 **저비용 상시** 목적이면 보통 **Compute Engine 소형 VM**이 더 단순합니다.

---

## API 키 / Secrets

- **로컬**: `.streamlit/secrets.toml` 또는 환경변수
- **GCP VM**: `docker run -e BINANCE_API_KEY=... -e BINANCE_API_SECRET=...`  
  또는 VM에 `secrets.toml`을 두고 볼륨 마운트 (저장소에 **절대 커밋하지 말 것**)

---

## 확인 체크리스트

- [ ] VM 외부 IP로 `:8501` 접속되는지
- [ ] `--restart=always` 로 재부팅 후 컨테이너가 다시 뜨는지
- [ ] Streamlit **자동 새로고침**은 **브라우저 탭이 열려 있을 때** 스크립트가 주기적으로 rerun 되는 구조 — **PC를 끄고 브라우저만 닫아도**, 서버(VM)만 살아 있으면 **다른 기기에서 다시 접속**하면 됩니다.
- [ ] 실거래 사용 시: 방화벽·HTTPS·IP 제한·API 키 회전까지 보안 점검

---

## 문제 해결

- **접속 안 됨**: GCP 방화벽에서 8501 허용 여부, VM의 `docker ps`, `sudo ufw status`
- **메모리 부족**: `e2-micro`에서 빌드가 힘들면 로컬/Cloud Build로 이미지 빌드 후 Artifact Registry에 푸시하는 방식을 사용

이 저장소 루트의 `Dockerfile`로 이미지를 빌드하면 됩니다.

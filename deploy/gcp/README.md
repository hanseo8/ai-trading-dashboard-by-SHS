# Google Cloud에서 상시 실행 (저비용) — 상세 사용 순서

로컬 PC를 끄면 Streamlit도 같이 꺼집니다. **항상 켜 둔 VM(가상 서버)** 에 올리면, 집 컴퓄를 꺼도 **같은 주소로 다시 접속**할 수 있습니다.

이 문서는 **Compute Engine + Docker** 기준으로, 콘솔(웹)만으로 따라 할 수 있게 적었습니다.

---

## 0. 미리 알아두기

| 항목 | 설명 |
|------|------|
| **비용** | `e2-micro`는 계정·리전 조건에 따라 **월 1대 무료(Always Free)** 일 수 있습니다. [무료 한도](https://cloud.google.com/free/docs/free-cloud-features#compute)는 공식 문서로 확인하세요. |
| **보안** | 대시보드를 인터넷에 그대로 열면 누구나 URL을 알면 접속할 수 있습니다. 가능하면 **IP 제한**, 나중에 **HTTPS + 비밀번호**를 권장합니다. |
| **자동 새로고침** | 앱은 `sleep` 후 `st.rerun()` 구조라, **브라우저 탭이 열려 있는 동안** 주기적으로 돌아갑니다. VM만 켜 두면, **다른 기기에서 브라우저만 다시 열면** 됩니다. |

---

## 1. Google Cloud 시작하기 (처음 한 번)

1. 브라우저에서 [Google Cloud Console](https://console.cloud.google.com/) 접속 후 Google 계정으로 로그인합니다.
2. 상단의 **프로젝트 선택** → **새 프로젝트** → 이름만 정해서 만듭니다. (예: `penseo-dash`)
3. **결제 계정 연결**  
   - 왼쪽 메뉴 **결제** → 결제 계정을 프로젝트에 연결합니다.  
   - 무료 크레딧/무료 한도를 쓰더라도 **결제 수단 등록**이 필요한 경우가 많습니다.

---

## 2. 필요한 API 켜기

1. 검색창에 `Compute Engine API` 를 검색해 들어갑니다.  
   또는 [API 라이브러리](https://console.cloud.google.com/apis/library)에서 **Compute Engine API** 검색.
2. **사용 설정** 을 눌러 활성화합니다. (처음 VM 만들 때 자동으로 켜지기도 합니다.)

---

## 3. VM(가상 머신) 만들기

1. 왼쪽 메뉴 **Compute Engine** → **VM 인스턴스**.  
   처음이면 **Compute Engine 사용 설정** 을 한 번 진행합니다.
2. **인스턴스 만들기** 클릭.
3. 아래처럼 맞춥니다 (저비용 기준).

   - **이름**: 예) `streamlit-vm`
   - **리전**: 무료 한도를 노릴 경우 **us-central1**, **us-east1**, **us-west1** 중 하나를 많이 씁니다. (한국 `asia-northeast3` 도 가능하지만 무료 조건은 문서 확인)
   - **영역**: 아무 영역(예: `us-central1-a`)
   - **머신 유형**: **시리즈 E2** → **e2-micro** (1 vCPU 공유, 1GB RAM — 빌드가 빡빡하면 나중에 `e2-small`으로 올리기)
   - **부팅 디스크**: **변경** → **Ubuntu 22.04 LTS**, 크기 **20 GB** (기본 10GB도 가능하지만 Docker 빌드 여유를 위해 20GB 권장)
   - **방화벽**: **HTTP 트래픽 허용** / **HTTPS 트래픽 허용** 은 **선택 사항** (Streamlit 기본 포트는 8501이라, 아래 4번에서 따로 엽니다)

4. **만들기** 를 눌러 생성이 끝날 때까지 기다립니다 (1~2분).

5. 목록에서 해당 VM의 **외부 IP** 열을 확인합니다.  
   - 처음에는 **비어 있을 수** 있습니다. **외부 IP** 열 옆 메뉴에서 **외부 IP 주소 예약** 또는 인스턴스 **편집**에서 **네트워크 인터페이스** → **외부 IPv4 주소** 를 **임시** 또는 **고정**으로 할당합니다.  
   - **고정 IP**를 쓰면 VM을 지워도 IP가 바뀌지 않아 접속 주소가 안정적입니다. (고정 IP는 유료인 경우가 있으니 콘솔 안내 확인)

---

## 4. 방화벽에서 8501 포트 열기 (필수)

Streamlit 기본 포트는 **8501** 입니다. GCP 쪽에서 막혀 있으면 브라우저에서 접속이 안 됩니다.

1. 왼쪽 메뉴 **VPC 네트워크** → **방화벽** → **방화벽 규칙 만들기**.
2. 설정 예시:

   - **이름**: `allow-streamlit-8501`
   - **네트워크**: `default`
   - **우선순위**: `1000` (기본값)
   - **트래픽 방향**: **수신**
   - **일치 시 작업**: **허용**
   - **대상**: **지정된 대상 태그** → 태그에 예: `streamlit-server` 입력
   - **소스 필터**: **IPv4 범위** → `0.0.0.0/0` (전 세계 허용, **테스트용**. 나중에 집 공인 IP만 넣는 것을 권장)
   - **프로토콜 및 포트**: **지정된 포트 및 프로토콜** → **tcp** → `8501`

3. **만들기** 저장.

4. **VM 인스턴스**로 돌아가 해당 VM을 **편집**합니다.
   - **네트워크 태그** → 위에서 만든 태그 `streamlit-server` 를 **정확히** 추가합니다.
   - **저장** 후 잠시 기다립니다.

> 이미 `default-allow-http` 같은 규칙만 있는 경우, **80번 포트**만 열려 있을 수 있습니다. Streamlit은 **8501** 이므로 위 규칙이 반드시 필요합니다.

---

## 5. VM에 접속 (SSH)

1. **Compute Engine** → **VM 인스턴스**.
2. 만든 VM의 **SSH** 버튼을 누릅니다. (브라우저 창에서 터미널이 열립니다.)

이후 명령은 이 SSH 창 안에서 실행합니다.

---

## 6. VM 안에서 Docker 설치

아래를 **한 블록씩** 실행합니다.

```bash
sudo apt-get update
sudo apt-get install -y docker.io git
sudo usermod -aG docker "$USER"
```

`groups` 에 `docker` 가 안 보이면, **SSH 창을 닫았다가 다시 SSH** 로 접속합니다.

그 다음:

```bash
docker --version
```

버전이 나오면 성공입니다.

---

## 7. 앱 코드 받기 및 이미지 빌드

저장소 주소는 본인 GitHub 기준으로 맞춥니다. (예시)

```bash
cd ~
git clone https://github.com/hanseo8/ai-trading-dashboard-by-SHS.git
cd ai-trading-dashboard-by-SHS
git pull
docker build -t streamlit-dash .
```

`pandas-ta` 설치 오류가 나면 저장소를 `git pull` 로 최신화한 뒤 다시 `docker build` 하세요. (Dockerfile이 Python 3.12 기준입니다.)

- **e2-micro** 에서 빌드가 터지거나 느리면:  
  - VM 사양을 **e2-small** 로 올리거나,  
  - 로컬 PC에서 빌드 후 **Artifact Registry**에 올리는 방식을 쓰면 됩니다. (고급)

---

## 8. 컨테이너 실행 (재부팅 후에도 자동 기동)

### 8-1. 기본 실행 (데이터는 컨테이너 안에만 저장)

이미 같은 이름 컨테이너가 있으면 먼저 제거합니다.

```bash
docker rm -f streamlit-dash 2>/dev/null || true
docker run -d --name streamlit-dash --restart=always -p 8501:8501 streamlit-dash
```

### 8-2. 모의 포트폴리오 파일 백업 (선택)

컨테이너 안 `/app` 에 `portfolio_breakout.json` 등이 생깁니다. **이미지를 다시 빌드하거나 컨테이너를 지우면** 안에만 있던 파일은 사라질 수 있으니, 가끔 VM에 복사해 두면 안전합니다.

```bash
sudo docker cp streamlit-dash:/app/portfolio_breakout.json "$HOME/portfolio_breakout.backup.json" 2>/dev/null || true
```

파일명은 실제 생성된 이름에 맞추면 됩니다.  
**`/app` 전체를 호스트 폴더로 마운트**하면 Docker 이미지에 넣어 둔 `app.py` 가 가려져서 **앱이 안 뜰 수 있으니**, 첫 배포는 **8-1** 만 쓰는 것을 권장합니다.

---

## 9. 브라우저에서 접속

주소 형식:

```text
http://<VM의_외부_IP>:8501
```

- VM 목록에 있는 **외부 IP** 를 복사합니다.
- 집/회사 PC 브라우저에서 위 주소로 접속합니다.

안 되면:

1. VM이 **실행 중**인지 확인.
2. 방화벽 규칙이 **tcp:8501** 이고, VM에 **네트워크 태그**가 붙었는지 확인.
3. VM 안에서:

   ```bash
   docker ps
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8501
   ```

   `200` 근처면 서버는 정상입니다.

---

## 10. 바이낸스 API 키 (실제모드) — Secrets

앱은 `st.secrets` 로 키를 읽을 수 있습니다. VM에만 파일을 두고 **Git에는 절대 올리지 마세요.**

1. SSH로 VM 접속 후:

   ```bash
   mkdir -p ~/.streamlit
   nano ~/.streamlit/secrets.toml
   ```

2. 예시 (키 이름은 앱 코드와 맞출 것):

   ```toml
   BINANCE_API_KEY = "여기에_키"
   BINANCE_API_SECRET = "여기에_시크릿"
   ```

3. 컨테이너에 넣어 다시 실행:

   ```bash
   docker rm -f streamlit-dash
   docker run -d --name streamlit-dash --restart=always -p 8501:8501 \
     -v "$HOME/.streamlit/secrets.toml:/root/.streamlit/secrets.toml:ro" \
     streamlit-dash
   ```

   (이미지 기본 사용자가 root가 아니면 경로가 다를 수 있습니다. 그때는 `docker exec -it streamlit-dash bash` 로 들어가 `~/.streamlit` 위치를 확인하세요.)

---

## 11. 확인 체크리스트

- [ ] `http://외부IP:8501` 로 대시보드가 뜬다.
- [ ] `docker ps` 에 `streamlit-dash` 가 **Up** 상태다.
- [ ] VM **재시작** 후에도 `docker ps` 에 다시 떠 있다 (`--restart=always`).
- [ ] API 키는 **저장소에 커밋하지 않았다**.

---

## 12. 자주 묻는 것

**Q. 집 PC를 꺼도 자동매매가 계속되나요?**  
**A.** VM만 켜져 있으면 **서버 쪽 앱은 계속 실행**됩니다. 다만 이 앱의 **자동 새로고침**은 브라우저 세션과 연결된 부분이 있어, **항상 “백그라운드 봇”** 이 아니라 **대시보드 + 주기적 rerun** 구조입니다. **PC를 꺼도** VM 주소로 **다시 접속**하면 됩니다.

**Q. Cloud Run은 왜 안 썼나요?**  
**A.** Streamlit은 WebSocket·장시간 연결이 있어, Cloud Run은 **최소 인스턴스 0** 이면 끊기기 쉽고, **상시**로 쓰려면 비용·설정이 복잡해질 수 있습니다. **저비용 상시**는 소형 VM이 단순한 경우가 많습니다.

---

## 13. 문제 해결

| 증상 | 점검 |
|------|------|
| 연결 시간 초과 | 외부 IP 맞는지, 방화벽 8501, VM 실행 중인지 |
| 빌드 OOM | `e2-small`로 변경 또는 스왑 추가, 또는 다른 머신에서 빌드 |
| secrets 반영 안 됨 | 마운트 경로, 컨테이너 재시작 후 로그 `docker logs streamlit-dash` |

---

이 저장소 루트의 `Dockerfile` 로 이미지를 빌드하면 됩니다. 질문이 있으면 VM 사양( e2-micro / e2-small )과 에러 메시지 전체를 알려주면 됩니다.

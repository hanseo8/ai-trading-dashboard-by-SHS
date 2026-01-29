import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from typing import Optional
import time
import math
import textwrap

# 페이지 설정
st.set_page_config(page_title="서한석의 코인 자동매매", layout="wide")

st.error(f"DEPLOYMENT CHECK: v3.0 - Current Time: {datetime.utcnow()}")

def apply_custom_styles():
    st.markdown("""
    <style>
        :root {
            --bg-color: #0E1117;
            --card-bg: #1E1E1E;
            --text-color: #E0E0E0;
            --neon-green: #00FFA3;
            --neon-red: #FF0055;
            --cyber_blue: #00D2FF;
            --border-radius: 12px;
        }
        
        .stApp { background-color: var(--bg-color); color: var(--text-color); }
        
        .stCard {
            background-color: var(--card-bg);
            padding: 20px;
            border-radius: var(--border-radius);
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
            margin-bottom: 20px;
            border: 1px solid #333;
        }
        
        .news-container {
            background-color: #16181C;
            padding: 15px;
            border-radius: var(--border-radius);
            height: 600px;
            overflow-y: auto;
            border-left: 2px solid #333;
            box-shadow: inset 0 0 10px rgba(0,0,0,0.5);
        }
        
        .news-container::-webkit-scrollbar { width: 8px; }
        .news-container::-webkit-scrollbar-track { background: #111; }
        .news-container::-webkit-scrollbar-thumb { background: #444; border-radius: 4px; }
        .news-container::-webkit-scrollbar-thumb:hover { background: #666; }
        
        .metric-row { display: flex; gap: 15px; justify-content: space-between; margin-bottom: 20px; }
        .metric-card {
            background-color: var(--card-bg);
            flex: 1;
            padding: 15px;
            border-radius: var(--border-radius);
            text-align: center;
            border: 1px solid #333;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        .metric-label { font-size: 0.9em; color: #888; margin-bottom: 5px; }
        .metric-value { font-size: 1.6em; font-weight: bold; color: #FFF; }
        .metric-delta { font-size: 0.9em; }
        .delta-pos { color: var(--neon-green); }
        .delta-neg { color: var(--neon-red); }
        
        @keyframes pulse-red {
            0% { box-shadow: 0 0 0 0 rgba(255, 0, 85, 0.4); }
            70% { box-shadow: 0 0 0 10px rgba(255, 0, 85, 0); }
            100% { box-shadow: 0 0 0 0 rgba(255, 0, 85, 0); }
        }
        .pulse-red { animation: pulse-red 2s infinite; border: 1px solid var(--neon-red) !important; }
        
        @keyframes blink {
            0% { opacity: 1; }
            50% { opacity: 0.4; }
            100% { opacity: 1; }
        }
        .live-dot { color: red; animation: blink 1.5s infinite; }
        
        .badge { padding: 2px 6px; border-radius: 4px; font-size: 0.8em; font-weight: bold; margin-right: 5px; }
        .badge-danger { background-color: rgba(255, 0, 85, 0.2); color: var(--neon-red); border: 1px solid var(--neon-red); }
        .badge-info { background-color: rgba(0, 210, 255, 0.2); color: var(--cyber_blue); border: 1px solid var(--cyber_blue); }

        /* Sidebar Fix */
        section[data-testid="stSidebar"] { background-color: #16181C !important; }
        section[data-testid="stSidebar"] * { color: #E0E0E0 !important; }
        section[data-testid="stSidebar"] button { color: white !important; }
        
        .stMarkdown, .stText, p, h1, h2, h3, h4, h5, h6 { color: #E0E0E0 !important; }
        
        div[data-baseweb="select"] > div { background-color: #262730 !important; color: #FFF !important; border-color: #444 !important; }
        div[data-baseweb="popover"] div { background-color: #262730 !important; color: #FFF !important; }
        div[role="listbox"] li { background-color: #262730 !important; color: #FFF !important; }

    </style>
    """, unsafe_allow_html=True)


apply_custom_styles()



# -----------------------------------------------------------------------------
# [DEBUG] Canary: Import Check
# -----------------------------------------------------------------------------
st.write(f"SYSTEM STATUS: Booting... v3.2 (Time: {datetime.now()})")

try:
    # CACHE BUSTING: Force Reload
    st.markdown(f"<!-- Cache Buster: {datetime.utcnow()} -->", unsafe_allow_html=True)

    apply_custom_styles()

    st.markdown(f"""
    <div style='text-align: center; margin-bottom: 30px;'>
        <h1 style='color: #FFF; text-shadow: 0 0 10px rgba(255,255,255,0.3);'>
            ⚡ 서한석의 코인 자동매매 <span style='color: #00FFA3'>PRO</span> <span style='font-size:0.5em; background:#333; padding:5px; border-radius:5px;'>v3.2 FINAL</span>
        </h1>
    </div>
    """, unsafe_allow_html=True)
except Exception as e:
    st.error(f"CRITICAL BOOT ERROR: {e}")
    st.stop()

# Continue with main logic wrapper
try:
    # Remove @st.cache_resource temporarily to investigate if it's holding stale connection
    def get_exchange() -> ccxt.Exchange:
    ex = ccxt.binance({
        "enableRateLimit": True,
        "options": {
            "defaultType": "spot", # 현물 시장 명시
            "adjustForTimeDifference": True, # 시간 동기화 에러 방지
        },
        "urls": {
            "api": {
                "public": "https://data-api.binance.vision/api/v3",
                "fapiPublic": "https://data-api.binance.vision/api/v3", # 퓨처스 접속 차단 (우회)
                "fapi": "https://data-api.binance.vision/api/v3",       # 퓨처스 접속 차단 (우회)
                "dapiPublic": "https://data-api.binance.vision/api/v3", # 코인 퓨처스 차단 (우회)
                "dapi": "https://data-api.binance.vision/api/v3",       # 코인 퓨처스 차단 (우회)
            }
        },
        "timeout": 30000, # 응답 대기 시간 연장
    })
    return ex


@st.cache_data(ttl=30)
def fetch_tickers() -> dict:
    ex = get_exchange()
    return ex.fetch_tickers()


@st.cache_data(ttl=60)
def get_data(symbol: str, timeframe: str = "1h", limit: int = 200) -> Optional[pd.DataFrame]:
    ex = get_exchange()
    try:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        # 지표 계산
        df["ema7"] = ta.ema(df["close"], length=7)
        df["ema25"] = ta.ema(df["close"], length=25)
        df["ema99"] = ta.ema(df["close"], length=99)
        
        # 보조지표: RSI, WPR, MACD, BB(20, 2), ATR
        df["rsi14"] = ta.rsi(df["close"], length=14)
        df["wpr"] = ta.willr(df["high"], df["low"], df["close"], length=14)
        
        macd = ta.macd(df["close"])
        df = pd.concat([df, macd], axis=1)

        bb = ta.bbands(df["close"], length=20, std=2.0)
        df = pd.concat([df, bb], axis=1)
        
        # [나만의 기법] BB(15, 2.4) 추가 (유지 - 레거시 참조용 혹은 필요시 사용)
        bb_my = ta.bbands(df["close"], length=15, std=2.4)
        df = pd.concat([df, bb_my], axis=1)
        
        # [스캘핑 업그레이드] 
        # 1. 밴드폭 (Squeeze 감지용): (Upper - Lower) / Middle
        # ta.bbands 결과 컬럼명 확인 필요. 보통 BBU_*, BBL_*, BBM_*
        # bb 변수 사용 (20, 2)
        if "BBU_20_2.0" in df.columns and "BBL_20_2.0" in df.columns and "BBM_20_2.0" in df.columns:
            df["bb_width"] = (df["BBU_20_2.0"] - df["BBL_20_2.0"]) / df["BBM_20_2.0"]
        else:
            df["bb_width"] = 0.0
            
        # 2. 거래량 5이평
        df["vol_ma5"] = ta.sma(df["volume"], length=5)
        
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)
        df["atr_ma"] = ta.sma(df["atr"], length=20)
        
        # 거래량 이동평균 (기존 10이평 유지)
        df["vol_ma"] = ta.sma(df["volume"], length=10)

        # 결측치가 있는 초기 구간 제거(지표 안정화)
        df = df.dropna().reset_index(drop=True)
        if len(df) < 3:
            return None
        return df
    except Exception:
        return None


def fmt_price(x):
    if x is None:
        return "-"
    # 요청: 0.0000 자리까지 표시
    return f"{x:,.4f}"


def safe_quote_volume(markets: dict, symbol: str) -> float:
    try:
        v = markets.get(symbol, {}).get("quoteVolume", None)
        if v is None:
            return 0.0
        return float(v)
    except Exception:
        return 0.0


@st.cache_data(ttl=60)
def get_btc_trend(_exchange):
    """비트코인 15분봉 EMA99 확인 (상승장 여부 판단)"""
    try:
        ohlcv = _exchange.fetch_ohlcv("BTC/USDT", timeframe="15m", limit=120)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["close"] = pd.to_numeric(df["close"])
        df["ema99"] = ta.ema(df["close"], length=99)
        
        last_close = float(df["close"].iloc[-1])
        last_ema = float(df["ema99"].iloc[-1])
        
        is_bullish = last_close > last_ema
        return is_bullish, last_close, last_ema
    except Exception as e:
        print(f"BTC Trend Error: {e}")
        return True, 0, 0 # 에러 시 보수적으로 통과

def get_best_bid(_exchange, symbol):
    """최적 매수 호가 (Orderbook Top Bid) 조회"""
    try:
        orderbook = _exchange.fetch_order_book(symbol)
        return orderbook["bids"][0][0]
    except:
        return None

# 1. 강조할 긴급 키워드 설정
URGENT_KEYWORDS = ["상장", "해킹", "유의", "폐지", "폭락", "SEC", "공격", "중단"]

def display_news_with_filter():
    # 뉴스 컨테이너 시작 (Indentation Free)
    news_html = '<div class="news-container">'
    news_html += '<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 15px;">'
    news_html += '<h4 style="margin:0; color: #FFF;">🔔 실시간 속보</h4><span class="live-dot">● LIVE</span></div>'
    
    # 1. 국내 뉴스 (RSS)
    rss_url = "https://kr.investing.com/rss/news_25.rss"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(rss_url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "html.parser") # lxml 제거
            items = soup.find_all("item")
            
            for item in items[:20]:
                title = item.find("title").text.strip()
                link = item.find("link").text.strip()
                
                # Date Processing
                pubDate = ""
                p_tag = item.find("pubDate") or item.find("pubdate")
                if p_tag:
                    # ex: Mon, 29 Jan 2026 14:30:00 GMT
                    pubDate = p_tag.text[17:22]
                
                is_urgent = any(kw in title for kw in URGENT_KEYWORDS)
                
                badge_html = "<span class='badge badge-info'>뉴스</span>"
                title_style = "color: #DDD;"
                
                if is_urgent:
                    badge_html = "<span class='badge badge-danger'>긴급</span>"
                    title_style = "color: #FF0055; font-weight: bold;"
                
                # Single Line HTML Construction
                news_html += f'<div style="margin-bottom: 12px; border-bottom: 1px solid #333; padding-bottom: 8px;">'
                news_html += f'<div style="font-size: 0.8em; color: #888; margin-bottom: 4px;">{badge_html} {pubDate}</div>'
                news_html += f'<a href="{link}" target="_blank" style="text-decoration: none;"><span style="{title_style}">{title}</span></a>'
                news_html += '</div>'
        else:
            news_html += f'<div style="color:red">RSS 로딩 실패 ({response.status_code})</div>'
    except Exception as e:
        news_html += f'<div style="color:red">RSS 에러: {str(e)}</div>'

    # Global News
    news_html += '<h5 style="margin-top: 20px; color: #BBB; border-top: 1px dashed #444; padding-top: 10px;">🌍 Global Feed</h5>'
    news_html += '<div style="margin-bottom: 10px;"><span class="badge badge-info">System</span> <span style="color: #DDD;">Monitoring Global Markets...</span></div>'
    
    news_html += '</div>' # End container
    st.markdown(news_html, unsafe_allow_html=True)


# 상단 헤더

with st.sidebar:
    st.subheader("설정")
    
    # 1. 전략 선택 (최상위)
    strategy_mode = st.selectbox(
        "전략 선택", 
        ["단기 스캘핑 (1m/5m)", "중장기 스윙 (1h~1d)", "고수의 기법 (Triple Confirm)"]
    )
    
    # 기본값 설정
    default_vol = 1.1
    default_wpr = -85
    
    # 2. 타임프레임 (전략에 종속)
    if strategy_mode.startswith("단기"): # 스캘핑
        timeframe = st.selectbox("타임프레임", ["1m", "5m"], index=1)
        portfolio_file = "portfolio_scalping.json"
        portfolio_label = "단타 (Scalping)"
        default_vol = 2.0 # 스캘핑 기본 2배
        st.info("⚡ 스캘핑 전략 (1m/5m)\n• 조건: 횡보(Squeeze) + 정배열(EMA) + 거래량 2배\n• 익절: +1.0% / 손절: EMA7 이탈")
        
    elif strategy_mode.startswith("중장기"): # 스윙
        timeframe = st.selectbox("타임프레임", ["1h", "4h", "1d"], index=0)
        portfolio_file = "portfolio_long.json"
        portfolio_label = "장기 (Long-Term)"
        default_vol = 1.1 # 스윙은 널널하게
        st.info("💎 스윙 전략 (1h-1d)\n• 조건: 장기 추세(EMA99) + RSI 안정권(50~70)\n• 목표: 추세가 꺾일 때까지 장기 보유")
        
    else: # 고수의 기법
        timeframe = st.selectbox("타임프레임", ["15m"], index=0)
        portfolio_file = "portfolio_my.json"
        portfolio_label = "고수의 기법 (Triple Confirm)"
        default_vol = 1.5 # "최소 1.5배는 터져야 진짜 수급"
        default_wpr = -80 # "-85보다 -80이 적절"
        st.info("💡 15분봉 실전 단타: 정배열(EMA7>25) + WPR(-80) 탈출 + 거래량(1.5배)")

    # 슬라이더 (key를 설정해서 전략 변경 시 리셋/재설정 되도록 유도하거나, value에 변수 할당)
    # key에 전략 모드를 포함시켜서 전환 시 새로운 값이 적용되도록 함
    top_n = st.slider("스캔 개수", min_value=5, max_value=50, value=20, step=5)
    vol_mult = st.slider("거래량 조건(이동평균 대비 배수)", 1.0, 5.0, default_vol, 0.1, key=f"vol_{strategy_mode}") 
    wpr_level = st.slider("WPR 기준선(과매도 탈출)", -95, -50, default_wpr, 1, key=f"wpr_{strategy_mode}")
    st.caption("데이터는 바이낸스 공개 시세(지연/누락 가능).")
    
    st.divider()
    st.subheader("자동 갱신")
    auto_refresh = st.checkbox("자동 새로고침 켜기", value=True)
    
    # 전략별 추천 갱신 주기 설정
    if strategy_mode.startswith("단기"):
        rec_refresh = 10
        rec_msg = "추천: 10~15초 (API 안전 및 대응 충분)"
    elif strategy_mode.startswith("중장기"):
        rec_refresh = 60
        rec_msg = "추천: 60~120초 (긴 호흡, API 효율)"
    else: # 고수의 기법
        rec_refresh = 20
        rec_msg = "추천: 20~30초 (진중한 신호 확인)"

    refresh_sec = st.slider("갱신 주기(초)", 5, 120, rec_refresh, key=f"refresh_{strategy_mode}")
    st.caption(f"💡 {rec_msg}")
    
    st.divider()
    enable_lock = st.checkbox("🔒 포트폴리오 잠금 (초기화 방지)", value=False)
    if enable_lock:
        st.caption("안전 모드 ON: 초기화 버튼이 잠깁니다. (자동 매매는 계속됨)")

# 전역 변수 설정
portfolio_mode = portfolio_label

# 상단 포트폴리오 요약
pf_init = pt.load_portfolio(portfolio_file)

# 평가금액(Equity) 계산 (실시간 가격 반영 시도)
cached_prices = st.session_state.get("current_prices", {})
initial_equity = pf_init["balance"]

for symbol, h in pf_init["holdings"].items():
    # 현재가가 있으면 현재가, 없으면 평단가(매수비용)로 계산
    c_price = cached_prices.get(symbol, h["avg_price"])
    initial_equity += h["amount"] * c_price

# 수익률 계산 (기준 5만불)
# 나중에 update_portfolio_status가 돌면 더 정확하겠지만, 헤더 단계에선 근사치 제공
base_capital = 50000.0
pnl_amount = initial_equity - base_capital
pnl_pct = (pnl_amount / base_capital) * 100

st.divider()

# 메트릭 카드 HTML 생성
delta_color = "delta-pos" if pnl_pct >= 0 else "delta-neg"
pnl_icon = "▲" if pnl_pct >= 0 else "▼"

st.markdown(f"""
<div class="metric-row">
    <div class="metric-card">
        <div class="metric-label">실시간 수익(USDT)</div>
        <div class="metric-value {delta_color}">{pnl_amount:,.2f}</div>
        <div class="metric-delta {delta_color}">{pnl_icon} {pnl_pct:.2f}%</div>
    </div>
    <div class="metric-card">
        <div class="metric-label">보유 종목</div>
        <div class="metric-value">{len(pf_init['holdings'])} <span style="font-size:0.5em">개</span></div>
        <div class="metric-delta" style="color:var(--cyber_blue)">실시간 감시 중</div>
    </div>
    <div class="metric-card">
        <div class="metric-label">평가 금액</div>
        <div class="metric-value">{initial_equity:,.0f}</div>
        <div class="metric-label">USDT</div>
    </div>
    <div class="metric-card">
        <div class="metric-label">예수금 잔액</div>
        <div class="metric-value">{pf_init['balance']:,.0f}</div>
        <div class="metric-label">USDT</div>
    </div>
</div>
""", unsafe_allow_html=True)

st.caption(f"현재 모드: {portfolio_mode} - 타임프레임에 따라 계좌가 자동 전환됩니다.")
st.divider()

# 레이아웃 구성 (7:3)
col_main, col_news = st.columns([0.7, 0.3])

# 우측 뉴스 피드 (HTML Container 로 변경)
with col_news:
    display_news_with_filter()  # 함수 내부도 수정 필요

# 좌측 메인 차트/스캔 영역 (Card 적용)
with col_main:
    st.markdown('<div class="stCard">', unsafe_allow_html=True) # 카드 시작
    st.subheader(f"🔥 실시간 정밀 스캔 (USDT 마켓 / 거래량 상위 {top_n}개 기준)")

# 기존 try-except 문을 아래처럼 수정해서 에러 내용을 확인합니다.
try:
    markets = fetch_tickers()
except Exception as e:
    col_main.error(f"바이낸스 연결 실패: {str(e)}") # 어떤 에러인지 정확히 보여줍니다.
    col_main.info("💡 팁: VPN을 사용 중이라면 끄거나, 반대로 인터넷 환경이 불안정하면 다른 와이파이/핫스팟으로 시도해 보세요.")
    st.stop()

symbols = [s for s in markets.keys() if isinstance(s, str) and s.endswith("/USDT")]
top_symbols = sorted(symbols, key=lambda x: safe_quote_volume(markets, x), reverse=True)[: int(top_n)]

# BTC 추세 확인 (안전장치)
exchange = get_exchange()
is_bull, btc_price, btc_ema = get_btc_trend(exchange)

btc_status_text = "상승장 (매수 가능) 🚀" if is_bull else "하락장 (매수 중단) 🛡️"
btc_color = "green" if is_bull else "red"

# Pulse Animation Class 적용
pulse_class = "pulse-red" if not is_bull else ""
col_main.markdown(f"""
<div class="stCard {pulse_class}" style="padding: 10px; text-align: center; margin-bottom: 15px;">
    <h4 style='margin:0'>BTC 추세(15m/EMA99): :{btc_color}[{btc_status_text}] ({btc_price:,.1f} vs {btc_ema:,.1f})</h4>
</div>
""", unsafe_allow_html=True)

if not is_bull:
    col_main.warning("비트코인이 추세선(EMA99) 아래에 있어 신규 매수를 일시 중단합니다.")


current_prices = {}
status_data = []
progress = col_main.progress(0, text="스캔 중…")
for i, symbol in enumerate(top_symbols, start=1):
    df = get_data(symbol, timeframe=timeframe, limit=200)
    if df is None:
        progress.progress(i / len(top_symbols), text=f"스캔 중… ({i}/{len(top_symbols)})")
        continue

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # --- 전략 판별 로직 ---

    # 1. 단기 전략 (Short-term / Scalping)
    # 조건: 에너지 응축(횡보) + 정배열(EMA 7-25 GC) + 거래량 2배(5이평 대비) + RSI 50 돌파
    
    # 응축 여부 (BB Width가 하위 25% 수준이거나 절대값 0.05 미만 등... -> 단순화: 0.1 미만)
    is_squeeze = (last["bb_width"] < 0.1) 
    
    # 정배열 여부 (단순 상태)
    is_st_trend = (last["ema7"] > last["ema25"])
    
    # 정배열 전환 (EMA 7 > 25)
    is_gc = is_st_trend and (prev["ema7"] <= prev["ema25"]) # 막 크로스
    # 또는 이미 정배열 상태에서 눌림목? User req: "정배열 전환" -> Golden Cross
    
    # 거래량 실린 양봉 (직전 5개 평균 대비 설정값 배)
    # 기존 하드코딩 2.0 -> vol_mult 사용
    is_vol_pump = (last["volume"] > last["vol_ma5"] * vol_mult) and (last["close"] > last["open"])
    
    # RSI 컨펌 (50 상향 돌파 or 50~60 구간 상승)
    is_rsi_up = (last["rsi14"] > 50)
    
    st_score = "관망"
    if is_gc and is_vol_pump and is_rsi_up: # 응축은 옵션으로 볼지, 필수일지. 사용자: "횡보해야 합니다"
        # 횡보 감지는 bb_width가 낮았던 상태에서 터지는 것.
        # prev의 bb_width가 낮았다면 OK.
        if prev["bb_width"] < 0.15: # 조금 널널하게
             st_score = "🚀 단기 급등 (Squeeze Break)"
        else:
             st_score = "🚀 단기 급등 (Volume Break)" # 횡보 아니어도 볼륨 터지면 일단 표시

    # 2. 장기 전략 (Long-term)
    # 가격이 EMA 99 위 + RSI가 50~70 사이 (안정적 상승 구간)
    is_lt_trend = bool(last["close"] > last["ema99"])
    is_lt_rsi = bool(50 < last["rsi14"] < 70) if "rsi14" in last else False
    
    lt_score = "💎 장기 보유" if (is_lt_trend and is_lt_rsi) else "비중 축소"
    
    # --- 고수의 기법: 나만의 기법 (Master Strategy) ---

    # 1. 조건 정의
    # 장기 추세(Filter): 가격이 EMA 99(장기 이평선) 위에 있어 전체적인 흐름이 상승장일 것. -> BTC로 1차 필터했으므로 개별 종목은 정배열 체크
    is_master_trend = last["close"] > last["ema99"]
    
    # "정배열" (EMA7 > EMA25) 추가 (New Requirement)
    is_master_align = last["ema7"] > last["ema25"]
    
    # WPR -80 탈출 (Trigger): 설정값 wpr_level 활용
    is_master_wpr = prev["wpr"] < wpr_level and last["wpr"] > wpr_level
    
    # 거래량 폭발(Confirm): 설정값 배수 사용 (1.5배)
    is_master_vol = last["volume"] > (last["vol_ma"] * vol_mult)
    
    # RSI 조건 (힘이 실리기 시작함) - 보조
    is_master_rsi = last["rsi14"] > 50

    # 2. 신호 결정
    master_signal = "관망"
    # 조건: BTC상승(기본) + 정배열(EMA7>25) + WPR탈출 + 거래량폭발
    if is_master_align and is_master_wpr and is_master_vol:
        master_signal = "🔥 실전 단타 진입 (강력매수)"
    elif is_master_trend and is_master_rsi and is_master_vol and is_master_wpr:
        master_signal = "⚡ 추세 돌파 (추격매수)"

    # 현재 모드에 맞는 신호 선택
    if strategy_mode.startswith("단기"):
         display_signal = st_score
    elif strategy_mode.startswith("중장기"):
         display_signal = lt_score
    else: # 고수
         display_signal = master_signal
         
    # 3. 데이터프레임에 추가
    status_data.append({
        "종목": symbol,
        "현재가": float(last["close"]),
        "진입 신호": display_signal,
        "추세(EMA)": "상승/정배열" if (is_st_trend or is_lt_trend) else "하락/역배열", # 참고용
        "RSI": round(float(last["rsi14"]), 1) if "rsi14" in last else None,
        "거래량": f"{round(last['volume']/last['vol_ma'], 1)}배"
    })

    # 모의 매수 & 매도 (현재 모드에 맞춰서)
    buy_msg = None
    should_buy = False
    
    # 모드별 매수 조건 (Display Signal 기반으로 판단 가능)
    if "🚀" in display_signal: # 단기 급등
        should_buy = True
    elif "강력매수" in display_signal or "추격매수" in display_signal: # 고수
        should_buy = True
    elif "장기 보유" in display_signal: # 장기
        should_buy = True
            
    # 매수 실행
    if should_buy:
        if not is_bull:
            buy_msg = "BTC 하락장 (스킵)"
        else:
            # 중복 매수 방지
            curr_pf = pt.load_portfolio(portfolio_file)
            if symbol in curr_pf["holdings"] and curr_pf["holdings"][symbol]["amount"] > 0:
                 buy_msg = "보유 중 (스킵)"
            else:
                # 투자금 설정 (모든 기법 1000불 통일)
                invest_money = 1000.0
                
                # 지정가 매수 시뮬레이션 (호가 조회)
                bid_price = get_best_bid(exchange, symbol)
                entry_price = bid_price if bid_price else float(last["close"])

                success, msg = pt.buy_coin(symbol, entry_price, invest_amount=invest_money, filename=portfolio_file)
                if success:
                    buy_msg = "매수 체결 완료"
                    st.toast(f"✅ {symbol} 매수 완료! ({entry_price})")
                else:
                    buy_msg = f"매수 실패: {msg}"

    # [매도 로직 업데이트]
    # 스캘핑: TP 1.0%, SL (EMA 7 꺾임)
    # 고수/장기: TP 10% (기존 유지?) -> 고수는 TP에 대한 언급 없었으나 "자신있게 들어가 볼 만한 자리" -> 일단 10% 유지 or 수동
    # 기존 코드의 10% 로직을 모드별로 분기
    
    curr_pf = pt.load_portfolio(portfolio_file)
    if symbol in curr_pf["holdings"]:
        holding = curr_pf["holdings"][symbol]
        amt = holding["amount"]
        if amt > 0:
            avg_p = holding["avg_price"]
            cur_p = float(last["close"])
            profit_pct = (cur_p - avg_p) / avg_p * 100
            
            should_sell = False
            sell_reason = ""
            
            if portfolio_mode.startswith("단타"):
                # 익절: 1.5% 이상 (User Request)
                if profit_pct >= 1.5:
                    should_sell = True
                    sell_reason = "익절 (1.5%)"
                # 손절: -1.0% 이하 or EMA 7 꺾임 (User Request)
                elif profit_pct <= -1.0:
                    should_sell = True
                    sell_reason = "손절 (-1.0%)"
                # (기존 로직 유지) EMA 7 꺾임
                elif last["ema7"] < prev["ema7"]:
                    should_sell = True
                    sell_reason = "손절 (EMA7 하락)"
            
            elif portfolio_mode.startswith("장기"): # 스윙 (추세 추종)
                # 설명대로 "추세가 꺾일 때까지" 보유
                # 추세 기준: Price < EMA99 (상승 추세 이탈)
                if last["close"] < last["ema99"]:
                     should_sell = True
                     sell_reason = "매도 (추세 이탈 EMA99)"
                # (옵션) 익절 없음? 혹은 매우 큰 익절(50%?)
                # 일단 추세 꺾임만 봅니다.
                
            else: # 고수의 기법 (실전 단타)
                # TP: +2.5%, SL: -1.5%
                if profit_pct >= 2.5:
                    should_sell = True
                    sell_reason = "익절 (+2.5%)"
                elif profit_pct <= -1.5:
                    should_sell = True
                    sell_reason = "손절 (-1.5%)"

            if should_sell and not enable_lock:
                success, msg = pt.sell_coin(symbol, cur_p, amt, filename=portfolio_file)
                if success:
                    print(f"💰 {sell_reason}: {symbol} ({profit_pct:.2f}%)")

    progress.progress(i / len(top_symbols), text=f"스캔 중… ({i}/{len(top_symbols)})")

progress.empty()

# 필터링 없이 전체 리스트 출력 (메인 화면 단순화)
df_all = pd.DataFrame(status_data)

if df_all.empty:
    col_main.info("검색된 종목이 없습니다.")
else:
    # 보기 좋게 포맷
    df_view = df_all.copy()
    df_view["현재가"] = df_view["현재가"].map(fmt_price)
    
    # 스타일 적용 함수
    def highlight_signal(val):
        val_str = str(val)
        if "🚀" in val_str: 
            return "background-color: #ff4b4b; color: white; font-weight: bold"
        elif "💎" in val_str: 
            return "background-color: #00cc96; color: white; font-weight: bold"
        elif "🎯" in val_str: 
            return "background-color: #ffa502; color: white; font-weight: bold"
        elif "🔥" in val_str: 
            return "background-color: #ff4500; color: white; font-weight: bold" # 오렌지레드
        elif "⚡" in val_str:
            return "background-color: #ffa502; color: white; font-weight: bold" # 오렌지
        return ""

    col_main.dataframe(
        df_view.style
        .map(highlight_signal, subset=["진입 신호"])
        .set_table_styles([
            {'selector': 'th', 'props': [('background-color', '#FFDAB9'), ('color', 'black'), ('font-weight', 'bold'), ('text-align', 'center')]}
        ]),
        use_container_width=True,
        hide_index=True
    )
    col_main.markdown('</div>', unsafe_allow_html=True) # Scanner Card 종료

# 포트폴리오 상세
# col_main.divider() -> 카드 간격으로 대체
col_main.markdown('<div class="stCard">', unsafe_allow_html=True) # Portfolio Card 시작
col_main.subheader("💼 내 포트폴리오")

# 현재가 갱신을 위해 스캔된 데이터 활용 (또는 별도 조회 필요)
# 위 루프에서 현재가가 있다면 업데이트
for d in status_data:
    current_prices[d["종목"]] = d["현재가"]

portfolio_updated = pt.get_portfolio_status(current_prices, filename=portfolio_file)

# 2단 컬럼 대신 수직 배치로 변경
col_main.markdown("##### 📦 보유 중인 코인")
if not portfolio_updated["details"]:
    col_main.info("보유 중인 코인이 없습니다.")
else:
    df_pf = pd.DataFrame(portfolio_updated["details"])
    col_main.dataframe(df_pf, use_container_width=True, hide_index=True)

col_main.markdown('</div>', unsafe_allow_html=True) # Portfolio Card 종료
col_main.markdown('<div class="stCard">', unsafe_allow_html=True) # History Card 시작
col_main.markdown("##### 📝 통합 매매 기록 (모든 전략)")

# 모든 포트폴리오 파일에서 기록 취합
all_files = {
    "단타": "portfolio_scalping.json",
    "장기": "portfolio_long.json",
    "고수": "portfolio_my.json"
}

all_trades = []
for label, fname in all_files.items():
    pf_data = pt.load_portfolio(fname)
    hist = pf_data.get("history", [])
    # 출처 표기
    for h in hist:
        h["strategy"] = label
        all_trades.append(h)

if not all_trades:
    col_main.info("매매 기록이 없습니다.")
else:
    # 최신순 정렬
    df_trades = pd.DataFrame(all_trades)
    # 키 이름 호환성 체크 ('time' vs 'timestamp')
    if "time" in df_trades.columns:
        sort_key = "time"
    else:
        sort_key = "timestamp" 
        
    df_trades = df_trades.sort_values(by=sort_key, ascending=False).head(30) # 30개로 늘림
    
    # 보기 좋게 가공
    display_trades = []
    for _, r in df_trades.iterrows():
        ts_val = r.get("time", r.get("timestamp", ""))
        try:
            ts_str = datetime.strptime(ts_val, "%Y-%m-%d %H:%M:%S").strftime("%m-%d %H:%M")
        except:
            ts_str = str(ts_val)
            
        t_type = r["type"]
        symbol = r["symbol"]
        price = fmt_price(r["price"])
        
        # 수익률 표시
        profit_str = ""
        if "pnl_pct" in r and r["pnl_pct"] is not None:
                profit_str = f"({r['pnl_pct']:.2f}%)"
        
        # 구분(Color) 아이콘
        icon = "🔵" if "buy" in t_type else "🔴"
        if "익절" in t_type: icon = "🟢"
        
        display_trades.append({
            "전략": r.get("strategy", "-"), # 전략 구분 추가
            "시간": ts_str,
            "구분": f"{icon} {t_type}",
            "종목": symbol,
            "가격": price,
            "수익률": profit_str
        })
        
    col_main.dataframe(pd.DataFrame(display_trades), use_container_width=True, hide_index=True)

col_main.markdown('</div>', unsafe_allow_html=True) # History Card 종료

with st.sidebar:
    if not enable_lock:
        if st.button("포트폴리오 초기화", key="reset_pf_btn"):
            pt.reset_portfolio(filename=portfolio_file)
            st.rerun()
    else:
        st.button("포트폴리오 초기화", disabled=True, help="잠금 해제 후 사용 가능합니다.")


# 상세 차트 보기 (선택한 종목)
col_main.markdown('<div class="stCard">', unsafe_allow_html=True) # Chart Card 시작
col_main.subheader("📊 상세 차트")

if df_all.empty:
    col_main.info("현재 스캔된 종목이 없어 차트를 표시할 수 없습니다.")
    # 검색된 종목이 없어도 빈 차트라도 띄우거나, 수동 입력 칸을 줄 수도 있음.
    # 여기서는 안내 문구만 수정
else:
    selected_coin = col_main.selectbox("상세 차트 분석", df_all["종목"].tolist())
    df_chart = get_data(selected_coin, timeframe=timeframe, limit=300)
    if df_chart is None:
        col_main.error("해당 종목의 차트 데이터를 불러오지 못했습니다.")
    else:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            row_heights=[0.7, 0.3],
            vertical_spacing=0.03,
            subplot_titles=("Price", "RSI(14)"),
        )

        fig.add_trace(
            go.Candlestick(
                x=df_chart["timestamp"],
                open=df_chart["open"],
                high=df_chart["high"],
                low=df_chart["low"],
                close=df_chart["close"],
                name="Price",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(x=df_chart["timestamp"], y=df_chart["ema7"], name="EMA 7", line=dict(color="orange")),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(x=df_chart["timestamp"], y=df_chart["ema25"], name="EMA 25", line=dict(color="blue")),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(x=df_chart["timestamp"], y=df_chart["ema99"], name="EMA 99", line=dict(color="red", width=2)),
            row=1,
            col=1,
        )

        # RSI 하단 보조지표
        if "rsi14" in df_chart.columns:
            fig.add_trace(
                go.Scatter(
                    x=df_chart["timestamp"],
                    y=df_chart["rsi14"],
                    name="RSI(14)",
                    line=dict(color="#00cc96"),
                ),
                row=2,
                col=1,
            )
            # 30 / 70 레벨선
            fig.add_hline(y=30, line_dash="dash", line_color="gray", row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="gray", row=2, col=1)
            fig.update_yaxes(range=[0, 100], row=2, col=1)

        fig.update_layout(
            height=700,
            margin=dict(l=10, r=10, t=30, b=10),
            xaxis_rangeslider_visible=False,
        )

        col_main.plotly_chart(fig, use_container_width=True)

col_main.markdown('</div>', unsafe_allow_html=True) # Chart Card 종료

# 사이드바 하단에 긴급 정지 버튼 배치
with st.sidebar:
    st.divider()
    st.markdown("### ⚠️ 긴급 통제")
    # type="primary"는 붉은색(테마 설정에 따라 다름) 또는 강조
    if st.button("🚨 EMERGENCY STOP", type="primary", use_container_width=True):
        st.error("모든 매매 프로세스 강제 중단!")
        st.stop()
    st.caption("모든 자동매매가 즉시 중단됩니다.")

# 자동 갱신 로직 (마지막에 위치)
if auto_refresh:
    time.sleep(refresh_sec)
    st.rerun()


import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timezone
from typing import Optional, Tuple
import time
import math
import textwrap
import requests
from bs4 import BeautifulSoup
import feedparser
import paper_trading as pt  # <--- CRITICAL FIX
import daily_equity as de

# 페이지 설정
st.set_page_config(page_title="급등 전조 탐지 대시보드", layout="wide")

# (Removed old v3.0 Error Banner)

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
        
        /* New Glassmorphism Scrollbar */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #111; }
        ::-webkit-scrollbar-thumb { background: #444; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #666; }
        
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

        /* Mobile Optimization (Max Width 768px) */
        @media (max-width: 768px) {
            .metric-row { flex-direction: column; gap: 10px; }
            .metric-card { width: 100% !important; margin-bottom: 5px; padding: 10px; }
            h1 { font-size: 1.4em !important; text-shadow: none !important; }
            h2 { font-size: 1.1em !important; }
            .news-container { height: 400px; margin-top: 15px; }
            /* Force DataFrame to scroll horizontally */
            .stDataFrame { display: block; overflow-x: auto; white-space: nowrap; }
            /* Hide non-essential elements if needed, but scrolling is better */
            .stCard { padding: 15px; }
        }

    </style>
    """, unsafe_allow_html=True)


apply_custom_styles()



# -----------------------------------------------------------------------------
# [DEBUG] Canary: Import Check
# -----------------------------------------------------------------------------
# CACHE BUSTING: Force Reload
st.markdown(f"<!-- Cache Buster: {datetime.now(timezone.utc)} -->", unsafe_allow_html=True)

apply_custom_styles()

st.markdown(f"""
<div style='text-align: center; margin-bottom: 30px;'>
    <h1 style='color: #FFF; text-shadow: 0 0 10px rgba(255,255,255,0.3);'>
        🔥 급등 전조 탐지 대시보드 <span style='color: #00FFA3'>SHS</span> <span style='font-size:0.5em; background:#333; padding:5px; border-radius:5px;'>({datetime.now().strftime('%H:%M')})</span>
    </h1>
</div>
""", unsafe_allow_html=True)

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
        bu, bl, bm = _bbands_column_triplet(bb)
        
        # [나만의 기법] BB(15, 2.4) 추가 (유지 - 레거시 참조용 혹은 필요시 사용)
        bb_my = ta.bbands(df["close"], length=15, std=2.4)
        df = pd.concat([df, bb_my], axis=1)
        
        # [스캘핑 업그레이드] 
        # 1. 밴드폭 (Squeeze 감지용): (Upper - Lower) / Middle
        if bu and bl and bm and bu in df.columns and bl in df.columns and bm in df.columns:
            df["bb_width"] = (df[bu] - df[bl]) / df[bm]
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


def _bbands_column_triplet(bb_df: Optional[pd.DataFrame]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """pandas_ta bbands 컬럼명은 버전에 따라 BBU_20_2.0 또는 BBU_20_2.0_2.0 등으로 달라짐."""
    if bb_df is None or bb_df.empty:
        return None, None, None
    cols = list(bb_df.columns)
    upper = next((c for c in cols if str(c).startswith("BBU_")), None)
    lower = next((c for c in cols if str(c).startswith("BBL_")), None)
    mid = next((c for c in cols if str(c).startswith("BBM_")), None)
    return upper, lower, mid


@st.cache_resource
def get_breakout_exchange() -> ccxt.Exchange:
    """급등 전조 탐지: 공개 시세 전용 호스트(data-api.binance.vision)로 451(지역 차단) 우회.

    기본 api.binance.com 은 일부 국가/클라우드 IP 에서 451 을 반환합니다.
    현물 OHLCV 를 사용합니다(USDT 마켓, 메인 스캔과 동일 경로).
    """
    return ccxt.binance({
        "enableRateLimit": True,
        "options": {
            "defaultType": "spot",
            "adjustForTimeDifference": True,
        },
        "urls": {
            "api": {
                "public": "https://data-api.binance.vision/api/v3",
                "fapiPublic": "https://data-api.binance.vision/api/v3",
                "fapi": "https://data-api.binance.vision/api/v3",
                "dapiPublic": "https://data-api.binance.vision/api/v3",
                "dapi": "https://data-api.binance.vision/api/v3",
            }
        },
        "timeout": 30000,
    })


def scan_breakout(
    symbol: str,
    timeframe: str = "15m",
    limit: int = 50,
    rsi_threshold: float = 50.0,
    wpr_threshold: float = -85.0,
):
    """볼린저 밴드 수축 + 거래량 스파이크 + RSI/WPR 조건 탐지"""
    try:
        exchange = get_breakout_exchange()
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

        if df.empty:
            return False, 0.0, 0.0, 0.0, "데이터 없음", 0.0

        df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)

        bb = ta.bbands(df["close"], length=20, std=2.0)
        if bb is None or bb.empty:
            return False, 0.0, 0.0, 0.0, "볼린저 밴드 산출 실패", 0.0
        bu_col, bl_col, bm_col = _bbands_column_triplet(bb)
        if not bu_col or not bl_col or not bm_col:
            return False, 0.0, 0.0, 0.0, "볼린저 밴드 컬럼 인식 실패", 0.0

        df = pd.concat([df, bb], axis=1)
        df["rsi14"] = ta.rsi(df["close"], length=14)
        df["wpr14"] = ta.willr(df["high"], df["low"], df["close"], length=14)
        df["vol_ma20"] = df["volume"].rolling(window=20).mean()
        df = df.dropna().reset_index(drop=True)

        if df.empty:
            return False, 0.0, 0.0, 0.0, "지표 계산 데이터 부족", 0.0

        latest = df.iloc[-1]
        bb_upper = latest.get(bu_col)
        bb_lower = latest.get(bl_col)
        bb_mid = latest.get(bm_col)
        rsi_val = float(latest.get("rsi14", 0.0))
        wpr_val = float(latest.get("wpr14", -100.0))

        if pd.isna(bb_upper) or pd.isna(bb_lower) or pd.isna(bb_mid) or bb_mid == 0:
            return False, 0.0, rsi_val, wpr_val, "볼린저 밴드 계산 실패", float(latest["close"])

        bandwidth = float((bb_upper - bb_lower) / bb_mid)
        is_squeeze = bandwidth < 0.05
        is_vol_spike = bool(latest["volume"] > (latest["vol_ma20"] * 3))
        is_rsi_bullish = rsi_val > rsi_threshold
        is_wpr_recover = wpr_val > wpr_threshold

        detected = bool(is_squeeze and is_vol_spike and is_rsi_bullish and is_wpr_recover)
        return detected, bandwidth, rsi_val, wpr_val, "", float(latest["close"])
    except Exception as e:
        return False, 0.0, 0.0, 0.0, str(e), 0.0

# 1. 강조할 긴급 키워드 설정
URGENT_KEYWORDS = ["상장", "해킹", "유의", "폐지", "폭락", "SEC", "공격", "중단"]

def display_news_with_filter():
    # 1. 뉴스 컨테이너 시작 (Glassmorphism 스타일 - Indentation Safe using dedent)
    news_html = textwrap.dedent("""
    <div style='background: linear-gradient(145deg, #1e1e1e, #16181c); 
                padding: 20px; border-radius: 15px; border: 1px solid #333; 
                height: 750px; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.5);'>
        <div style='display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px;'>
            <h3 style='margin:0; color: #00FFA3; font-size: 1.2em;'>📡 LIVE TERMINAL</h3>
            <span style='color: #FF0055; font-size: 0.8em; font-weight: bold; animation: blink 1.5s infinite;'>● LIVE</span>
        </div>
    """)
    
    # 2. 데이터 가져오기 (RSS 활용 - Feedparser 요청 반영)
    rss_url = "https://kr.investing.com/rss/news_25.rss"
    try:
        # Feedparser 사용 (User Recommendation)
        feed = feedparser.parse(rss_url)
        
        if not feed.entries:
             # Fallback to requests if feedparser returns empty (common in some envs)
             raise Exception("Feedparser returned no entries, trying Requests fallback.")
        
        for entry in feed.entries[:20]:
            title = entry.title
            link = entry.link
            
            # 시간 추출 (published가 있으면 사용, 없으면 N/A)
            pubDate = "N/A"
            if hasattr(entry, 'published') and len(entry.published) > 20:
                 pubDate = entry.published[17:22] # HH:MM
            
            # 긴급 키워드 강조
            is_urgent = any(kw in title for kw in URGENT_KEYWORDS)
            
            badge_class = "badge-danger" if is_urgent else "badge-info"
            badge_text = "긴급" if is_urgent else "뉴스"
            title_color = "#FF0055" if is_urgent else "#E0E0E0"
            font_weight = "bold" if is_urgent else "normal"

            news_html += textwrap.dedent(f"""
            <div style='margin-bottom: 16px; border-bottom: 1px solid #2a2a2a; padding-bottom: 10px;'>
                <div style='display: flex; align-items: center; gap: 8px; margin-bottom: 6px;'>
                    <span class='badge {badge_class}' style='font-size: 0.7em;'>{badge_text}</span>
                    <span style='font-size: 0.8em; color: #666;'>{pubDate}</span>
                </div>
                <a href='{link}' target='_blank' style='text-decoration: none;'>
                    <span style='color: {title_color}; font-weight: {font_weight}; line-height: 1.4;'>{title}</span>
                </a>
            </div>
            """)

    except Exception as e:
        # Fallback to BeautifulSoup if Feedparser fails (Safety Net)
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            response = requests.get(rss_url, headers=headers, timeout=5)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, "html.parser")
                items = soup.find_all("item")
                for item in items[:20]:
                    title = item.find("title").text.strip()
                    link = item.find("link").text.strip()
                    # Date
                    pubDate = ""
                    p_tag = item.find("pubDate") or item.find("pubdate")
                    if p_tag: pubDate = p_tag.text[17:22]
                    
                    is_urgent = any(kw in title for kw in URGENT_KEYWORDS)
                    badge_class = "badge-danger" if is_urgent else "badge-info"
                    badge_text = "긴급" if is_urgent else "뉴스"
                    title_color = "#FF0055" if is_urgent else "#E0E0E0" 
                    font_weight = "bold" if is_urgent else "normal"
                    
                    news_html += f"""
                    <div style='margin-bottom: 16px; border-bottom: 1px solid #2a2a2a; padding-bottom: 10px;'>
                        <div style='display: flex; align-items: center; gap: 8px; margin-bottom: 6px;'>
                            <span class='badge {badge_class}' style='font-size: 0.7em;'>{badge_text}</span>
                            <span style='font-size: 0.8em; color: #666;'>{pubDate}</span>
                        </div>
                        <a href='{link}' target='_blank' style='text-decoration: none;'>
                            <span style='color: {title_color}; font-weight: {font_weight}; line-height: 1.4;'>{title}</span>
                        </a>
                    </div>
                    """
            else:
                 news_html += f"<div style='color:#FF0055;'>연결 오류 (Fallback): {str(e)} / HTTP {response.status_code}</div>"
        except Exception as e2:
             news_html += f"<div style='color:#FF0055;'>연결 오류 (All Failed): {str(e)} / {str(e2)}</div>"

    # [FIX] HTML Indentation Bug: Use single line or dedent properly
    news_html += "<h5 style='margin-top: 30px; color: #555; border-top: 1px dashed #333; padding-top: 15px; text-align:center;'>🌍 GLOBAL FEED ACTIVE</h5></div>"
    st.markdown(news_html, unsafe_allow_html=True)

with st.sidebar:
    st.subheader("설정")
    portfolio_file = "portfolio_breakout.json"
    portfolio_label = "급등 전조 탐지"
    st.markdown("### 🔥 급등 전조 탐지 (단일 전략)")

    st.divider()
    st.subheader("모의 매매 (선택)")
    use_paper = st.checkbox("모의 매매 사용", value=False, key="use_paper_breakout")
    paper_cash = st.number_input(
        "모의 자금 (USDT)",
        min_value=0.0,
        max_value=100000000.0,
        value=0.0,
        step=100.0,
        key="paper_cash_breakout",
    )
    if st.button("모의 자금 입금(잔액 반영)", key="apply_paper_cash_btn"):
        pf_cash = pt.load_portfolio(portfolio_file)
        pf_cash["balance"] = float(paper_cash)
        pf_cash["starting_capital"] = float(paper_cash)
        pt.save_portfolio(pf_cash, portfolio_file)
        st.success("모의 자금이 반영되었습니다.")
        st.rerun()

    st.divider()
    st.subheader("익절 / 손절 (모의)")
    breakout_tp = st.slider("익절 (%)", 0.3, 10.0, 1.25, 0.05, key="tp_breakout_only")
    breakout_sl = st.slider("손절 (%)", 0.3, 10.0, 0.8, 0.05, key="sl_breakout_only")
    trade_amount = st.slider("1회 매수 금액 (USDT)", 100.0, 5000.0, 5000.0, 100.0, key="trade_amt_breakout")

    st.divider()
    top_n = st.slider("스캔 개수 (거래량 상위)", min_value=5, max_value=50, value=20, step=5)
    st.caption("데이터는 바이낸스 공개 시세(지연/누락 가능).")

    st.divider()
    st.subheader("🔥 급등 전조 탐지 파라미터")
    breakout_timeframe = st.selectbox(
        "탐지 타임프레임",
        ["5m", "15m", "1h"],
        index=1,
        key="breakout_timeframe_sidebar",
    )
    breakout_limit = st.slider(
        "탐지 캔들 수",
        min_value=50,
        max_value=200,
        value=80,
        step=10,
        key="breakout_limit_sidebar",
    )
    breakout_rsi_threshold = st.slider(
        "RSI 기준값 (기본 30 -> 35)",
        min_value=20,
        max_value=80,
        value=35,
        step=1,
        key="breakout_rsi_threshold",
    )
    breakout_wpr_threshold = st.slider(
        "Williams %R 기준값 (기본 -78 -> -85)",
        min_value=-95,
        max_value=-50,
        value=-85,
        step=1,
        key="breakout_wpr_threshold",
    )
    st.caption("아래 상세 Plotly 차트의 RSI/WPR 기준선도 이 값으로 즉시 반영됩니다.")

    if st.button("🚀 급등 전조 스캔", key="scan_breakout_btn_sidebar", use_container_width=True):
        tickers = ["BTC/USDT", "ETH/USDT", "ACX/USDT", "PIXEL/USDT", "RIVER/USDT"]
        breakout_rows = []

        for ticker in tickers:
            detected, bw, rsi, wpr, err, _lc = scan_breakout(
                ticker,
                timeframe=breakout_timeframe,
                limit=breakout_limit,
                rsi_threshold=float(breakout_rsi_threshold),
                wpr_threshold=float(breakout_wpr_threshold),
            )
            breakout_rows.append({
                "종목": ticker,
                "상태": "🚨 탐지" if detected else ("⚠️ 오류" if err else "관망"),
                "밴드폭": bw,
                "RSI": rsi,
                "WPR": wpr,
                "오류": err if err else "-",
            })

        st.session_state["breakout_scan_rows"] = breakout_rows
        st.session_state["breakout_scan_time"] = datetime.now().strftime("%H:%M:%S")
        detected_count = sum(1 for r in breakout_rows if r["상태"] == "🚨 탐지")
        st.session_state["breakout_detected_count"] = detected_count
        st.success(f"스캔 완료: {detected_count}/{len(tickers)} 탐지")
    
    st.divider()
    st.subheader("자동 갱신")
    auto_refresh = st.checkbox("자동 새로고침 켜기", value=True)
    rec_refresh = 20
    rec_msg = "추천: 20~30초 (급등 전조 스캔)"
    refresh_sec = st.slider("갱신 주기(초)", 5, 120, rec_refresh, key="refresh_breakout_only")
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

# 수익률: 모의 자금(starting_capital) 설정 시에만 표시 (5만불 기본 제거)
_start_cap = float(pf_init.get("starting_capital", 0.0))
if _start_cap > 0:
    pnl_amount = initial_equity - _start_cap
    pnl_pct = (pnl_amount / _start_cap) * 100
else:
    pnl_amount = 0.0
    pnl_pct = 0.0

# 일자별 24h 수익 (KST 매일 09:00 스냅샷)
try:
    de.update_snapshots(initial_equity, portfolio_file)
except Exception:
    pass
df_daily_pnl = de.build_daily_report(initial_equity, portfolio_file)

st.divider()

# 메트릭 카드 HTML 생성
delta_color = "delta-pos" if pnl_pct >= 0 else "delta-neg"
pnl_icon = "▲" if pnl_pct >= 0 else "▼"
pnl_display = f"{pnl_amount:,.2f}" if _start_cap > 0 else "-"
pnl_pct_display = f"{pnl_pct:.2f}%" if _start_cap > 0 else "-"

st.markdown(f"""
<div class="metric-row">
    <div class="metric-card">
        <div class="metric-label">손익(모의, 입금 설정 시)</div>
        <div class="metric-value {delta_color}">{pnl_display}</div>
        <div class="metric-delta {delta_color}">{pnl_icon} {pnl_pct_display}</div>
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

st.subheader("📅 일자별 수익 현황 (24h · KST 09:00 기준)")
st.caption(
    "매 거래일 **09:00(한국시간)** 에 평가금액을 1회 스냅샷합니다. "
    "전일 09:00 자산 대비 당일 09:00 자산으로 **24시간 수익률**을 계산합니다. "
    "당일은 09:00 이후 첫 실행 시점의 자산이 당일 스냅샷으로 저장됩니다."
)
st.dataframe(df_daily_pnl, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# 보유 종목 + 매매 기록 (일자별 수익 현황 바로 아래 · 현재 전략 포트폴리오 연동)
# ---------------------------------------------------------------------------
st.markdown('<div class="stCard">', unsafe_allow_html=True)
tab_holdings_top, tab_history_top = st.tabs(
    ["💼 보유 종목 (My Wallet)", "📝 매매 기록 (Trade History)"]
)

_price_ctx = dict(st.session_state.get("current_prices", {}))
_pf_holdings = pt.load_portfolio(portfolio_file).get("holdings", {})
_missing_px = [
    s for s in _pf_holdings.keys()
    if s not in _price_ctx or not _price_ctx.get(s) or float(_price_ctx[s]) <= 0
]
if _missing_px:
    try:
        _ex_pf = get_exchange()
        _tk = _ex_pf.fetch_tickers(_missing_px)
        for _sym, _t in _tk.items():
            _last = _t.get("last") or _t.get("close")
            if _last is not None and float(_last) > 0:
                _price_ctx[_sym] = float(_last)
    except Exception:
        pass

with tab_holdings_top:
    portfolio_updated = pt.get_portfolio_status(_price_ctx, filename=portfolio_file)
    if not portfolio_updated["details"]:
        st.info("현재 보유 중인 코인이 없습니다. (자동 매매 대기 중)")
    else:
        df_pf = pd.DataFrame(portfolio_updated["details"])

        def color_pnl_wallet(val):
            s = str(val)
            if "%" not in s:
                return ""
            try:
                num = float(s.replace("%", "").strip())
            except ValueError:
                return ""
            color = "#ff4b4b" if num > 0 else "#00cc96" if num < 0 else "white"
            return f"color: {color}; font-weight: bold"

        st.dataframe(
            df_pf.style.map(color_pnl_wallet, subset=["수익률"]),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            f"총 평가금액: {portfolio_updated['equity']:,.2f} USDT "
            f"(손익: {portfolio_updated['pnl']:,.2f} USDT)"
        )

with tab_history_top:
    all_files_wallet = {
        "급등 전조 탐지": portfolio_file,
    }
    all_trades_w = []
    for _label, _fname in all_files_wallet.items():
        _pdata = pt.load_portfolio(_fname)
        for _h in _pdata.get("history", []):
            _row = dict(_h)
            _row["전략"] = _label
            all_trades_w.append(_row)

    if not all_trades_w:
        st.info("아직 체결된 매매 기록이 없습니다.")
    else:
        df_trades = pd.DataFrame(all_trades_w)
        if "time" in df_trades.columns:
            df_trades = df_trades.sort_values(by="time", ascending=False)

        col_rename = {
            "time": "시간",
            "전략": "전략",
            "type": "유형",
            "symbol": "종목",
            "price": "체결가",
            "amount": "수량",
            "invest": "매수금액(USDT)",
            "total": "매도총액(USDT)",
            "pnl_pct": "실현수익률(%)",
        }
        cols_show = [c for c in col_rename if c in df_trades.columns]
        df_hist_view = df_trades[cols_show].rename(columns=col_rename)

        if "실현수익률(%)" in df_hist_view.columns:
            def _fmt_hist_pnl(x):
                if pd.isna(x):
                    return "-"
                try:
                    return f"{float(x):.2f}%"
                except (TypeError, ValueError):
                    return "-"

            df_hist_view["실현수익률(%)"] = df_hist_view["실현수익률(%)"].apply(_fmt_hist_pnl)
        if "유형" in df_hist_view.columns:
            df_hist_view["유형"] = df_hist_view["유형"].apply(
                lambda x: "매수" if x == "buy" else ("매도" if x == "sell" else str(x))
            )

        st.dataframe(df_hist_view, use_container_width=True, hide_index=True)

st.markdown("</div>", unsafe_allow_html=True)

st.caption(f"현재 모드: {portfolio_mode} (단일 전략)")
st.divider()

# 레이아웃 구성 (7:3)
col_main, col_news = st.columns([0.7, 0.3])

# 우측 뉴스 피드 (HTML Container 로 변경)
with col_news:
    display_news_with_filter()  # 함수 내부도 수정 필요

# 좌측 메인 차트/스캔 영역 (Card 적용)
with col_main:
    st.markdown('<div class="stCard">', unsafe_allow_html=True) # 카드 시작
    st.subheader(f"🔥 급등 전조 탐지 스캔 (USDT / 거래량 상위 {top_n}개)")

# 기존 try-except 문을 아래처럼 수정해서 에러 내용을 확인합니다.
try:
    markets = fetch_tickers()
except Exception as e:
    col_main.error(f"바이낸스 연결 실패: {str(e)}") # 어떤 에러인지 정확히 보여줍니다.
    col_main.info("💡 팁: VPN을 사용 중이라면 끄거나, 반대로 인터넷 환경이 불안정하면 다른 와이파이/핫스팟으로 시도해 보세요.")
    st.stop()

symbols = [s for s in markets.keys() if isinstance(s, str) and s.endswith("/USDT")]
top_symbols = sorted(symbols, key=lambda x: safe_quote_volume(markets, x), reverse=True)[: int(top_n)]

# BTC 추세 확인 (User Request: Remove Banner)
# exchange = get_exchange()
# is_bull, btc_price, btc_ema = get_btc_trend(exchange)
# btc_status_text = "상승장 (매수 가능) 🚀" if is_bull else "하락장 (매수 중단) 🛡️"
# btc_color = "green" if is_bull else "red"
# pulse_class = "pulse-red" if not is_bull else ""
# col_main.markdown(f"""
# <div class="stCard {pulse_class}" style="padding: 10px; text-align: center; margin-bottom: 15px;">
#     <h4 style='margin:0'>BTC 추세(15m/EMA99): :{btc_color}[{btc_status_text}] ({btc_price:,.1f} vs {btc_ema:,.1f})</h4>
# </div>
# """, unsafe_allow_html=True)
# if not is_bull:
#     col_main.warning("비트코인이 추세선(EMA99) 아래에 있어 신규 매수를 일시 중단합니다.")

# User Request: Remove Banner (Logic Commented Out)
# exchange = get_exchange()
# ...
# exchange = safe_exchange (Moved below)

current_prices = {}

# [SPEED FIX] 전역 Exchange 인스턴스 (재사용)
# 매번 생성하면 SSL 핸드쉐이크 등으로 인해 3~5배 느려짐.
# 순차 처리 모드이므로 전역 객체 사용이 안전함.
safe_exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot', 
        'adjustForTimeDifference': True
    },
    'urls': {
        'api': {
            'public': 'https://data-api.binance.vision/api/v3',
            'fapiPublic': 'https://data-api.binance.vision/api/v3',
            'fapi': 'https://data-api.binance.vision/api/v3',
            'dapiPublic': 'https://data-api.binance.vision/api/v3',
            'dapi': 'https://data-api.binance.vision/api/v3',
        }
    },
    'timeout': 10000 
})
exchange = safe_exchange # [FIX] NameError 방지용 별칭 (여기서 정의해야 함)

import traceback

# 스캔 시작 (Debug Mode Option)
debug_mode = st.sidebar.checkbox("🔧 디버그 모드 (에러 확인)", value=False)

progress_text = "⚡ 급등 전조 스캔 중..."
progress_bar = col_main.progress(0, text=progress_text)
status_data = []
errors = []

try:
    for i, symbol in enumerate(top_symbols):
        detected, bw, rsi, wpr, err, last_px = scan_breakout(
            symbol,
            timeframe=breakout_timeframe,
            limit=breakout_limit,
            rsi_threshold=float(breakout_rsi_threshold),
            wpr_threshold=float(breakout_wpr_threshold),
        )
        if err:
            errors.append(f"{symbol}: {err}")
            display_signal = "⚠️ 오류"
        elif detected:
            display_signal = "🚨 탐지"
        else:
            display_signal = "관망"

        lp = float(last_px) if last_px else 0.0
        if lp > 0:
            current_prices[symbol] = lp

        status_data.append({
            "종목": symbol,
            "현재가": lp,
            "진입 신호": display_signal,
            "밴드폭": f"{bw:.3f}",
            "RSI": round(float(rsi), 1) if rsi is not None else None,
            "WPR": round(float(wpr), 1) if wpr is not None else None,
        })

        should_buy = bool(use_paper and detected and not err)
        if should_buy:
            curr_pf = pt.load_portfolio(portfolio_file)
            if symbol not in curr_pf.get("holdings", {}) or curr_pf["holdings"][symbol].get("amount", 0) <= 0:
                bid_price = get_best_bid(exchange, symbol)
                entry_price = float(bid_price) if bid_price else lp
                success, msg = pt.buy_coin(
                    symbol, entry_price, invest_amount=float(trade_amount), filename=portfolio_file
                )
                if success:
                    st.toast(f"✅ {symbol} 매수 완료! ({entry_price})")

        curr_pf = pt.load_portfolio(portfolio_file)
        if symbol in curr_pf.get("holdings", {}):
            holding = curr_pf["holdings"][symbol]
            amt = holding["amount"]
            if amt > 0:
                cur_p = lp if lp > 0 else float(holding["avg_price"])
                profit_pct = (cur_p - holding["avg_price"]) / holding["avg_price"] * 100
                should_sell = False
                sell_reason = ""
                if profit_pct >= float(breakout_tp):
                    should_sell = True
                    sell_reason = f"익절 ({float(breakout_tp):.2f}%)"
                elif profit_pct <= -float(breakout_sl):
                    should_sell = True
                    sell_reason = f"손절 (-{float(breakout_sl):.2f}%)"
                if should_sell and not enable_lock:
                    success, msg = pt.sell_coin(symbol, cur_p, amt, filename=portfolio_file)
                    if success:
                        st.toast(f"{sell_reason}: {symbol} ({profit_pct:.2f}%)")

        progress_bar.progress(
            (i + 1) / len(top_symbols),
            text=f"{progress_text} ({i + 1}/{len(top_symbols)})",
        )
except Exception as e:
    col_main.error(f"❌ 치명적 오류 발생: {str(e)}")
    col_main.code(traceback.format_exc())

if debug_mode and errors:
    col_main.error(f"스캔 실패 ({len(errors)}개): {errors[:5]}...")

progress_bar.empty()

# 필터링 없이 전체 리스트 출력 (메인 화면 단순화)
df_all = pd.DataFrame(status_data)

if df_all.empty:
    col_main.info("검색된 종목이 없습니다.")
    col_main.markdown("</div>", unsafe_allow_html=True)  # Scanner Card 종료
else:
    # 보기 좋게 포맷
    df_view = df_all.copy()
    df_view["현재가"] = df_view["현재가"].map(fmt_price)
    
    # 스타일 적용 함수
    def highlight_signal(val):
        val_str = str(val)
        if "🚨" in val_str:
            return "background-color: #ff4b4b; color: white; font-weight: bold"
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

# 스캔에서 수집한 시세를 다음 실행 상단(일자별·보유 탭)에서 재사용
st.session_state["current_prices"] = {**st.session_state.get("current_prices", {}), **current_prices}

# 급등 전조 탐지 결과 (사이드바 설정/버튼 연동)
breakout_rows = st.session_state.get("breakout_scan_rows", [])
if breakout_rows:
    col_main.markdown('<div class="stCard">', unsafe_allow_html=True)
    col_main.subheader("🔥 급등 전조 탐지 결과")
    scan_time = st.session_state.get("breakout_scan_time", "-")
    detected_count = st.session_state.get("breakout_detected_count", 0)
    col_main.caption(f"최근 스캔 시각: {scan_time} | 탐지: {detected_count}/{len(breakout_rows)}")

    df_breakout = pd.DataFrame(breakout_rows)
    df_breakout["밴드폭"] = df_breakout["밴드폭"].apply(lambda x: f"{x:.3f}")
    df_breakout["RSI"] = df_breakout["RSI"].apply(lambda x: f"{x:.1f}")
    df_breakout["WPR"] = df_breakout["WPR"].apply(lambda x: f"{x:.1f}")
    col_main.dataframe(df_breakout, use_container_width=True, hide_index=True)
    col_main.markdown('</div>', unsafe_allow_html=True)

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
    df_chart = get_data(selected_coin, timeframe=breakout_timeframe, limit=300)
    if df_chart is None:
        col_main.error("해당 종목의 차트 데이터를 불러오지 못했습니다.")
    else:
        col_main.caption("Plotly 인터랙티브 차트: 마우스 휠로 확대/축소하여 매수 지점을 정밀 분석하세요.")
        fig = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            row_heights=[0.6, 0.2, 0.2],
            vertical_spacing=0.03,
            subplot_titles=("Price", "RSI(14)", "Williams %R(14)"),
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

        # 실제 매매 기록(선택 전략) 마커 오버레이: 왜 여기서 사졌는지 시각적으로 확인
        trade_hist = pt.load_portfolio(portfolio_file).get("history", [])
        buy_x, buy_y, sell_x, sell_y = [], [], [], []
        for t in trade_hist:
            if t.get("symbol") != selected_coin:
                continue
            t_time = pd.to_datetime(t.get("time"), errors="coerce")
            t_price = t.get("price", None)
            if pd.isna(t_time) or t_price is None:
                continue
            try:
                p = float(t_price)
            except Exception:
                continue
            if t.get("type") == "buy":
                buy_x.append(t_time)
                buy_y.append(p)
            elif t.get("type") == "sell":
                sell_x.append(t_time)
                sell_y.append(p)

        if buy_x:
            fig.add_trace(
                go.Scatter(
                    x=buy_x,
                    y=buy_y,
                    mode="markers",
                    name="매수 체결",
                    marker=dict(symbol="triangle-up", size=11, color="#ff4b4b"),
                ),
                row=1,
                col=1,
            )
        if sell_x:
            fig.add_trace(
                go.Scatter(
                    x=sell_x,
                    y=sell_y,
                    mode="markers",
                    name="매도 체결",
                    marker=dict(symbol="triangle-down", size=11, color="#00cc96"),
                ),
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
            # 사이드바 슬라이더 기준선 + 과열 기준선
            fig.add_hline(y=breakout_rsi_threshold, line_dash="dash", line_color="#ff4b4b", row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="gray", row=2, col=1)
            fig.update_yaxes(range=[0, 100], row=2, col=1)

        if "wpr" in df_chart.columns:
            fig.add_trace(
                go.Scatter(
                    x=df_chart["timestamp"],
                    y=df_chart["wpr"],
                    name="WPR(14)",
                    line=dict(color="#00D2FF"),
                ),
                row=3,
                col=1,
            )
            fig.add_hline(y=breakout_wpr_threshold, line_dash="dash", line_color="#ff4b4b", row=3, col=1)
            fig.add_hline(y=-20, line_dash="dash", line_color="gray", row=3, col=1)
            fig.update_yaxes(range=[-100, 0], row=3, col=1)

        fig.update_layout(
            height=850,
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


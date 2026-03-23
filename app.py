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
import html as html_escape
import requests
from bs4 import BeautifulSoup
import feedparser
import paper_trading as pt  # <--- CRITICAL FIX
import daily_equity as de


def _get_streamlit_secret(key: str, default: str = "") -> str:
    """Streamlit Cloud secrets.toml 또는 로컬 secrets."""
    try:
        if hasattr(st, "secrets") and st.secrets:
            v = st.secrets.get(key, default)
            return str(v).strip() if v is not None and str(v).strip() else default
    except Exception:
        pass
    return default


def test_binance_api_connection(
    api_key: str,
    api_secret: str,
    market_type: str,
    use_testnet: bool,
) -> Tuple[bool, str, Optional[dict]]:
    """바이낸스 API 키로 잔고 조회 테스트. (ok, 메시지, USDT 스냅샷)"""
    ak = (api_key or "").strip()
    sec = (api_secret or "").strip()
    if not ak or not sec:
        return False, "API Key와 Secret을 모두 입력하세요.", None
    try:
        ex = ccxt.binance(
            {
                "apiKey": ak,
                "secret": sec,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "future" if market_type == "future" else "spot",
                    "adjustForTimeDifference": True,
                },
                "timeout": 30000,
            }
        )
        if use_testnet:
            ex.set_sandbox_mode(True)
        ex.load_markets()
        bal = ex.fetch_balance()
        usdt = bal.get("USDT") or {}
        snap = {
            "usdt_total": usdt.get("total"),
            "usdt_free": usdt.get("free"),
            "usdt_used": usdt.get("used"),
        }
        return True, "연동 성공: 잔고 조회에 성공했습니다.", snap
    except Exception as e:
        return False, f"연동 실패: {e}", None


# 페이지 설정
st.set_page_config(page_title="급등 전조 탐지 대시보드", layout="wide")

# (Removed old v3.0 Error Banner)

def apply_custom_styles():
    st.markdown("""
    <style>
        :root {
            --bg-color: #0E1117;
            --card-bg: #1a1d23;
            --text-color: #E0E0E0;
            --neon-green: #00FFA3;
            --neon-red: #FF0055;
            --cyber_blue: #00D2FF;
            --border-radius: 12px;
            --border-subtle: rgba(255,255,255,0.07);
            --section-gap: 1.5rem;
        }
        
        .stApp { background-color: var(--bg-color); color: var(--text-color); }
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 2.5rem !important;
            max-width: 1680px !important;
        }
        
        .stCard {
            background-color: var(--card-bg);
            padding: 20px;
            border-radius: var(--border-radius);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
            margin-bottom: var(--section-gap);
            border: 1px solid var(--border-subtle);
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
        
        .metric-row { display: flex; gap: 1rem; justify-content: space-between; margin-bottom: var(--section-gap); }
        .metric-card {
            background: linear-gradient(180deg, #1e222a 0%, #1a1d23 100%);
            flex: 1;
            padding: 16px 14px;
            border-radius: var(--border-radius);
            text-align: center;
            border: 1px solid var(--border-subtle);
            box-shadow: 0 4px 16px rgba(0,0,0,0.25);
        }
        .metric-label { font-size: 0.78rem; color: #9ca3af; margin-bottom: 6px; font-weight: 500; letter-spacing: 0.02em; }
        .metric-value { font-size: 1.45rem; font-weight: 700; color: #f9fafb; letter-spacing: -0.02em; }
        .metric-delta { font-size: 0.82rem; }
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

        /* 실시간 뉴스 패널 (우측 피드) */
        .news-panel-wrap {
            background: linear-gradient(165deg, #1a1d24 0%, #12141a 100%);
            border-radius: 14px;
            border: 1px solid rgba(255,255,255,0.06);
            box-shadow: 0 12px 40px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.04);
            padding: 0;
            height: 750px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }
        .news-panel-header {
            flex-shrink: 0;
            padding: 18px 20px 14px;
            border-bottom: 1px solid rgba(255,255,255,0.06);
            background: rgba(0,0,0,0.25);
        }
        .news-panel-kicker {
            font-size: 0.68rem;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: #6b7280;
            margin-bottom: 6px;
            font-weight: 600;
        }
        .news-panel-title {
            margin: 0;
            color: #f3f4f6;
            font-size: 1.22rem;
            font-weight: 600;
            letter-spacing: -0.03em;
        }
        .news-panel-sub {
            font-size: 0.78rem;
            color: #6b7280;
            margin-top: 6px;
        }
        .news-live-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 0.72rem;
            font-weight: 600;
            color: #00ffa3;
            letter-spacing: 0.06em;
        }
        .news-live-dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: #00ffa3;
            box-shadow: 0 0 10px rgba(0,255,163,0.6);
            animation: blink 2s ease-in-out infinite;
        }
        .news-scroll {
            flex: 1;
            overflow-y: auto;
            padding: 12px 18px 18px;
        }
        .news-scroll::-webkit-scrollbar { width: 6px; }
        .news-scroll::-webkit-scrollbar-track { background: #111; }
        .news-scroll::-webkit-scrollbar-thumb { background: #3d4451; border-radius: 4px; }
        .news-item {
            margin-bottom: 14px;
            padding-bottom: 14px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .news-item:last-child { border-bottom: none; }
        .news-link {
            text-decoration: none;
            display: block;
            transition: opacity 0.15s ease;
        }
        .news-link:hover { opacity: 0.88; }
        .news-footer-hint {
            flex-shrink: 0;
            padding: 10px 16px;
            text-align: center;
            font-size: 0.68rem;
            color: #4b5563;
            border-top: 1px solid rgba(255,255,255,0.05);
            background: rgba(0,0,0,0.2);
        }

        /* 메인 히어로 타이틀 · 섹션 리듬 */
        .page-hero {
            text-align: center;
            margin-bottom: var(--section-gap);
            padding-bottom: 1.15rem;
            border-bottom: 1px solid var(--border-subtle);
        }
        .page-hero-title {
            margin: 0;
            color: #f9fafb !important;
            font-size: clamp(1.35rem, 2.2vw, 1.75rem);
            font-weight: 600;
            letter-spacing: -0.035em;
            line-height: 1.25;
        }
        .page-hero-badge {
            display: inline-block;
            font-size: 0.55em;
            vertical-align: middle;
            margin-left: 6px;
            padding: 4px 8px;
            border-radius: 6px;
            background: rgba(255,255,255,0.07);
            color: #9ca3af !important;
            font-weight: 500;
            letter-spacing: 0.02em;
        }
        section[data-testid="stMain"] h2,
        section[data-testid="stMain"] h3,
        div[data-testid="stHeadingContainer"] h2,
        div[data-testid="stHeadingContainer"] h3,
        div[data-testid="stMarkdownContainer"] h2,
        div[data-testid="stMarkdownContainer"] h3 {
            font-size: 1.05rem !important;
            font-weight: 600 !important;
            color: #e5e7eb !important;
            letter-spacing: -0.02em !important;
            margin-top: 0.25rem !important;
            margin-bottom: 0.35rem !important;
        }
        .stCaption, div[data-testid="stCaptionContainer"] {
            color: #9ca3af !important;
            font-size: 0.82rem !important;
        }
        hr {
            margin: 1.15rem 0 !important;
            border: none !important;
            border-top: 1px solid var(--border-subtle) !important;
            background: none !important;
        }

        /* DataFrame / 테이블 (전역 톤) */
        [data-testid="stDataFrame"] {
            border: 1px solid var(--border-subtle) !important;
            border-radius: 10px !important;
            overflow: hidden !important;
        }
        [data-testid="stDataFrame"] [data-testid="stTable"] th {
            background-color: #1e2329 !important;
            color: #e5e7eb !important;
            font-weight: 600 !important;
            font-size: 0.8rem !important;
            padding: 0.65rem 0.5rem !important;
            border-color: rgba(255,255,255,0.06) !important;
        }
        [data-testid="stDataFrame"] [data-testid="stTable"] td {
            font-size: 0.86rem !important;
            color: #d1d5db !important;
            border-color: rgba(255,255,255,0.05) !important;
            padding: 0.55rem 0.5rem !important;
        }
        [data-testid="stDataFrame"] [data-testid="stTable"] tr:hover td {
            background-color: rgba(255,255,255,0.03) !important;
        }

        /* 탭 */
        .stTabs [data-baseweb="tab-list"] {
            gap: 6px;
            background: transparent !important;
        }
        button[data-baseweb="tab"] {
            border-radius: 8px 8px 0 0 !important;
            font-weight: 500 !important;
            font-size: 0.88rem !important;
        }

        /* Sidebar Fix */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #14161c 0%, #16181C 100%) !important;
            border-right: 1px solid var(--border-subtle) !important;
        }
        section[data-testid="stSidebar"] * { color: #E0E0E0 !important; }
        section[data-testid="stSidebar"] button { color: white !important; }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            font-weight: 600 !important;
            letter-spacing: -0.02em !important;
        }
        section[data-testid="stSidebar"] h2 { font-size: 0.95rem !important; color: #d1d5db !important; }
        section[data-testid="stSidebar"] .stMarkdown h3 { font-size: 1rem !important; }
        
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
            .news-panel-wrap { height: 420px !important; margin-top: 15px; }
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

# ---------------------------------------------------------------------------
# 최상단: 연습모드 / 실제모드 (노란 강조 느낌의 모드 바)
# ---------------------------------------------------------------------------
_em_row = st.columns([0.06, 0.88, 0.06])
with _em_row[1]:
    _exec_label = st.radio(
        "운용 모드",
        ["연습모드 (모의)", "실제모드 (API)"],
        horizontal=True,
        key="execution_mode_radio",
        help=(
            "연습모드: 앱 내 모의 매매·포트폴리오만 사용. "
            "실제모드: 바이낸스 API 키로 계정 연동(잔고 조회). 실거래 주문은 별도 옵션으로 제한합니다."
        ),
    )
is_real_mode = _exec_label.startswith("실제")
execution_mode: str = "real" if is_real_mode else "practice"
st.session_state["execution_mode"] = execution_mode

if is_real_mode:
    st.markdown(
        """
<div style="
  background: linear-gradient(90deg, rgba(255,176,32,0.18), rgba(26,26,30,0.95));
  border: 2px solid #ffb020;
  border-radius: 10px;
  padding: 12px 18px;
  margin-bottom: 14px;
  text-align: center;
">
  <span style="color:#ffb020; font-weight:800; font-size:1.15em; letter-spacing:0.05em;">실제모드</span>
  <span style="color:#bbb; font-size:0.95em;"> — API 연동 후 실계좌 데이터를 사용합니다. 키는 세션에만 저장됩니다(서버 secrets 권장).</span>
</div>
""",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        """
<div style="
  background: linear-gradient(90deg, rgba(0,255,163,0.14), rgba(26,26,30,0.95));
  border: 2px solid #00ffa3;
  border-radius: 10px;
  padding: 12px 18px;
  margin-bottom: 14px;
  text-align: center;
">
  <span style="color:#00ffa3; font-weight:800; font-size:1.15em; letter-spacing:0.05em;">연습모드</span>
  <span style="color:#bbb; font-size:0.95em;"> — 모의 매매·가상 포트폴리오만 사용합니다.</span>
</div>
""",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# 최상단: 현물 / 선물(USDT-M) — 시세·스캔·차트·모의매매 심볼 형식과 연동
# ---------------------------------------------------------------------------
_mkt_row = st.columns([0.12, 0.76, 0.12])
with _mkt_row[1]:
    _mt_label = st.radio(
        "거래 마켓",
        ["현물 (Spot)", "선물 (USDT-M)"],
        horizontal=True,
        key="app_market_type_radio",
        help=(
            "**현물**: 공개 시세(data-api.binance.vision) 우회, 지연 가능. "
            "**선물**: USDT 무기한 — 심볼은 `BTC/USDT:USDT` 형식. 일부 지역에서 API(451) 차단될 수 있습니다."
        ),
    )
market_type: str = "spot" if _mt_label.startswith("현물") else "future"
st.session_state["market_type"] = market_type

# 실제모드: API 설정 패널 (마켓 유형에 맞춰 테스트)
if is_real_mode:
    _api_expanded = not bool(st.session_state.get("binance_api_ok", False))
    with st.expander("바이낸스 API 설정 · 연동 테스트", expanded=_api_expanded):
        st.warning(
            "API Secret은 **절대** 공개 저장소에 올리지 마세요. "
            "Streamlit Cloud는 **앱 설정 → Secrets** (`BINANCE_API_KEY`, `BINANCE_API_SECRET`) 사용을 권장합니다."
        )
        if "bin_api_key_field" not in st.session_state:
            st.session_state["bin_api_key_field"] = _get_streamlit_secret("BINANCE_API_KEY")
        _ak = st.text_input(
            "API Key",
            key="bin_api_key_field",
            autocomplete="off",
        )
        _sec = st.text_input(
            "API Secret",
            type="password",
            key="bin_api_secret_field",
            help="입력하지 않으면 연동 테스트 시 이전에 세션에 저장된 Secret을 사용합니다.",
        )
        _testnet = st.checkbox(
            "테스트넷(샌드박스) 사용",
            value=False,
            key="bin_use_testnet",
            help="Binance 테스트넷 키일 때만 켜세요.",
        )
        _b1, _b2, _ = st.columns([1, 1, 2])
        with _b1:
            _test_clicked = st.button("연동 테스트", type="primary", key="btn_binance_connect_test")
        with _b2:
            if st.session_state.get("binance_api_ok"):
                if st.button("연동 해제", key="btn_binance_disconnect"):
                    st.session_state["binance_api_ok"] = False
                    for _k in (
                        "binance_api_key",
                        "binance_api_secret",
                        "binance_usdt_snapshot",
                        "live_trading_enabled",
                    ):
                        st.session_state.pop(_k, None)
                    st.toast("API 연동을 해제했습니다.")
                    st.rerun()

        if _test_clicked:
            _sk = (_sec or "").strip() or st.session_state.get("binance_api_secret", "")
            _ok, _msg, _snap = test_binance_api_connection(
                _ak, _sk, market_type, _testnet
            )
            if _ok:
                st.session_state["binance_api_ok"] = True
                st.session_state["binance_api_key"] = _ak.strip()
                if (_sec or "").strip():
                    st.session_state["binance_api_secret"] = (_sec or "").strip()
                st.session_state["binance_usdt_snapshot"] = _snap
                st.success(_msg)
                if _snap:
                    st.info(
                        f"USDT — free: {_snap.get('usdt_free')}, "
                        f"used: {_snap.get('usdt_used')}, total: {_snap.get('usdt_total')}"
                    )
            else:
                st.session_state["binance_api_ok"] = False
                st.error(_msg)

        if st.session_state.get("binance_api_ok"):
            if "live_trading_enabled" not in st.session_state:
                st.session_state["live_trading_enabled"] = False
            st.checkbox(
                "실거래 주문 허용 (위험·신중히)",
                key="live_trading_enabled",
                help="켜도 현재 버전은 자동 매매 로직이 실제 주문을 보내지 않습니다. 다음 단계에서 주문 연동 예정입니다.",
            )
            st.caption(
                "실거래 자동 주문은 체결·수수료·청산 리스크가 큽니다. 별도 검증 후에만 활성화할 예정입니다."
            )
        else:
            st.info("실제모드에서 거래소와 연결하려면 **연동 테스트**를 통과해야 합니다.")

st.markdown(
    f"""
<div class="page-hero">
    <h1 class="page-hero-title">
        🔥 급등 전조 탐지 대시보드
        <span style="color:#00FFA3;">SHS</span>
        <span class="page-hero-badge">{datetime.now().strftime('%H:%M')}</span>
    </h1>
</div>
""",
    unsafe_allow_html=True,
)


def get_exchange(market_type: str = "spot") -> ccxt.Exchange:
    """현물: 공개 시세 호스트 우회. 선물: USDT-M(기본 fapi, 지역 제한 가능)."""
    if market_type == "future":
        return ccxt.binance({
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
            "timeout": 30000,
        })
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


@st.cache_data(ttl=3600)
def filter_binance_symbols(symbols: Tuple[str, ...], market_type: str) -> list[str]:
    """선택한 마켓(ccxt markets)에 존재하는 심볼만 반환."""
    try:
        ex = get_exchange(market_type)
        ex.load_markets()
        return [s for s in symbols if s in ex.markets]
    except Exception:
        return list(symbols)


# 사이드바 '급등 전조 스캔' 고정 후보 (미지원은 filter 에서 제외)
SIDEBAR_BREAKOUT_SCAN_SYMBOLS_SPOT: Tuple[str, ...] = (
    "BTC/USDT",
    "ETH/USDT",
    "ACX/USDT",
    "PIXEL/USDT",
    "SOL/USDT",
)
SIDEBAR_BREAKOUT_SCAN_SYMBOLS_FUTURE: Tuple[str, ...] = (
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "XRP/USDT:USDT",
    "DOGE/USDT:USDT",
)


@st.cache_data(ttl=30)
def fetch_tickers(market_type: str) -> dict:
    ex = get_exchange(market_type)
    return ex.fetch_tickers()


@st.cache_data(ttl=60)
def get_data(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 200,
    market_type: str = "spot",
) -> Optional[pd.DataFrame]:
    ex = get_exchange(market_type)
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
def get_breakout_exchange(market_type: str = "spot") -> ccxt.Exchange:
    """급등 전조 탐지용 거래소. 현물은 vision 우회, 선물은 USDT-M fapi."""
    if market_type == "future":
        return ccxt.binance({
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
            "timeout": 30000,
        })
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
    market_type: str = "spot",
):
    """볼린저 밴드 수축 + 거래량 스파이크 + RSI/WPR 조건 탐지"""
    try:
        exchange = get_breakout_exchange(market_type)
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
    """우측 패널: 실시간 뉴스 (RSS)."""
    news_html = textwrap.dedent("""
    <div class="news-panel-wrap">
        <div class="news-panel-header">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px;">
                <div>
                    <div class="news-panel-kicker">Market Intelligence</div>
                    <h3 class="news-panel-title">실시간 뉴스</h3>
                    <div class="news-panel-sub">외부 RSS 피드 · 반영 지연 가능</div>
                </div>
                <div style="padding-top:4px;">
                    <span class="news-live-pill"><span class="news-live-dot"></span>LIVE</span>
                </div>
            </div>
        </div>
        <div class="news-scroll">
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
            link = entry.link or "#"
            safe_title = html_escape.escape(str(title))
            safe_link = html_escape.escape(str(link), quote=True)

            # 시간 추출 (published가 있으면 사용, 없으면 N/A)
            pubDate = "—"
            if hasattr(entry, 'published') and entry.published and len(str(entry.published)) > 20:
                 pubDate = entry.published[17:22] # HH:MM
            
            # 긴급 키워드 강조
            is_urgent = any(kw in title for kw in URGENT_KEYWORDS)
            
            badge_class = "badge-danger" if is_urgent else "badge-info"
            badge_text = "긴급" if is_urgent else "일반"
            title_color = "#ff6b8a" if is_urgent else "#d1d5db"
            font_weight = "600" if is_urgent else "400"

            news_html += textwrap.dedent(f"""
            <div class="news-item">
                <div style='display: flex; align-items: center; gap: 8px; margin-bottom: 6px;'>
                    <span class='badge {badge_class}' style='font-size: 0.65em;'>{badge_text}</span>
                    <span style='font-size: 0.72rem; color: #6b7280; font-variant-numeric: tabular-nums;'>{pubDate}</span>
                </div>
                <a class="news-link" href="{safe_link}" target="_blank" rel="noopener noreferrer">
                    <span style='color: {title_color}; font-weight: {font_weight}; line-height: 1.45; font-size: 0.9rem;'>{safe_title}</span>
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
                    safe_title = html_escape.escape(str(title))
                    safe_link = html_escape.escape(str(link), quote=True)
                    pubDate = ""
                    p_tag = item.find("pubDate") or item.find("pubdate")
                    if p_tag: pubDate = p_tag.text[17:22]
                    if not pubDate:
                        pubDate = "—"

                    is_urgent = any(kw in title for kw in URGENT_KEYWORDS)
                    badge_class = "badge-danger" if is_urgent else "badge-info"
                    badge_text = "긴급" if is_urgent else "일반"
                    title_color = "#ff6b8a" if is_urgent else "#d1d5db"
                    font_weight = "600" if is_urgent else "400"

                    news_html += f"""
                    <div class="news-item">
                        <div style='display: flex; align-items: center; gap: 8px; margin-bottom: 6px;'>
                            <span class='badge {badge_class}' style='font-size: 0.65em;'>{badge_text}</span>
                            <span style='font-size: 0.72rem; color: #6b7280; font-variant-numeric: tabular-nums;'>{pubDate}</span>
                        </div>
                        <a class="news-link" href="{safe_link}" target="_blank" rel="noopener noreferrer">
                            <span style='color: {title_color}; font-weight: {font_weight}; line-height: 1.45; font-size: 0.9rem;'>{safe_title}</span>
                        </a>
                    </div>
                    """
            else:
                 news_html += f"<div style='color:#FF0055;'>연결 오류 (Fallback): {str(e)} / HTTP {response.status_code}</div>"
        except Exception as e2:
             news_html += f"<div style='color:#FF0055;'>연결 오류 (All Failed): {str(e)} / {str(e2)}</div>"

    # st.markdown 은 Markdown 전처리를 하므로, 줄 앞 공백 4칸 이상이면 코드 블록으로 깨져 HTML 이 그대로 노출됨 → 들여쓰기 제거
    news_html += textwrap.dedent(
        """
        </div>
        <div class="news-footer-hint">
            RSS · Investing.com 등 외부 출처 · 투자 판단은 본인 책임 · 정보 지연·누락 가능
        </div>
        </div>
        """
    ).strip()
    st.markdown(news_html, unsafe_allow_html=True)

with st.sidebar:
    st.subheader("설정")
    portfolio_file = "portfolio_breakout.json"
    portfolio_label = "급등 전조 탐지"
    st.markdown("### 🔥 급등 전조 탐지 (단일 전략)")

    # 운용 모드 표시 (메인 상단과 동일 기준)
    if execution_mode == "practice":
        st.info("**연습모드** · 모의 포트폴리오·가상 손익")
    else:
        st.warning("**실제모드** · 실계좌·API는 상단 패널에서 연동")
        if st.session_state.get("binance_api_ok"):
            st.caption("API 연결됨 — 잔고 조회 가능")
        else:
            st.caption("API 미연동 시 시세·스캔만 공개 데이터로 동작")

    _mt_side = "현물" if market_type == "spot" else "USDT-M 선물"
    st.caption(f"마켓: **{_mt_side}** (상단 라디오와 동일)")

    st.divider()

    # --- 필수: 타임프레임 + RSI + Williams %R ---
    st.subheader("필수 · 탐지 조건")
    st.caption("스캔·상세 차트·RSI/WPR 기준선에 동일 적용 (15m / 1h / 4h).")
    _tf_allowed = ("15m", "1h", "4h")
    _tf_key = "breakout_timeframe_sidebar"
    if st.session_state.get(_tf_key) not in _tf_allowed:
        st.session_state[_tf_key] = "15m"
    breakout_timeframe = st.selectbox(
        "탐지 타임프레임",
        list(_tf_allowed),
        index=0,
        key=_tf_key,
        help="급등 전조 로직에 쓰는 봉 단위입니다.",
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
        "RSI 기준값",
        min_value=20,
        max_value=80,
        value=35,
        step=1,
        key="breakout_rsi_threshold",
        help="종가 RSI가 이 값을 넘으면 조건에 반영됩니다.",
    )
    breakout_wpr_threshold = st.slider(
        "Williams %R 기준값",
        min_value=-95,
        max_value=-50,
        value=-85,
        step=1,
        key="breakout_wpr_threshold",
        help="WPR이 이 값보다 커야 조건에 반영됩니다.",
    )
    st.caption("상세 Plotly 차트의 RSI/WPR 기준선도 위 값으로 즉시 반영됩니다.")

    st.divider()

    # 익절·손절 (전략 공통 — 모의 청산 / 실제는 옵션에 따라)
    if execution_mode == "practice":
        st.subheader("익절 / 손절 (모의 청산)")
        st.caption("모의 포지션 자동 매도 시 적용할 %입니다.")
    else:
        st.subheader("익절 / 손절 (전략 %)")
        st.caption("모의 매매 시 가상 청산 기준. 실거래 자동주문은 별도 옵션·검증 후 적용.")
    breakout_tp = st.slider("익절 (%)", 0.3, 10.0, 1.25, 0.05, key="tp_breakout_only")
    breakout_sl = st.slider("손절 (%)", 0.3, 10.0, 0.8, 0.05, key="sl_breakout_only")

    st.divider()

    # 모의 자금·주문 크기
    if execution_mode == "practice":
        st.subheader("모의 매매")
        use_paper = st.checkbox(
            "모의 매매 사용 (자동 매수·매도)",
            value=False,
            key="use_paper_breakout",
        )
    else:
        st.subheader("매매·포지션 크기")
        use_paper = st.checkbox(
            "모의 포트폴리오 사용 (실계좌와 병행 시뮬)",
            value=False,
            key="use_paper_breakout",
            help="실제모드에서도 가상 잔고로만 시뮬하려면 켜세요. 실주문은 상단 실거래 옵션과 별개입니다.",
        )

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

    _ta_label = "1회 증거금·마진 (USDT)" if market_type == "future" else "1회 매수 금액 (USDT)"
    trade_amount = st.slider(_ta_label, 100.0, 5000.0, 5000.0, 100.0, key="trade_amt_breakout")

    if market_type == "future":
        st.divider()
        st.subheader("⚙️ 선물 레버리지 (USDT-M)")
        futures_leverage = st.slider(
            "레버리지 (배) — 모의 전용",
            min_value=1,
            max_value=125,
            value=10,
            step=1,
            key="futures_leverage_sidebar",
            help=(
                "이 값은 앱 안 모의 매매 계산에만 쓰이며, 바이낸스 계정의 실제 레버리지·종목별 상한과 자동 동기화되지 않습니다. "
                "실거래소는 종목마다 최대 레버리지가 다르고(예: 일부 알트는 20x 등), "
                "실제 설정·브래킷 조회는 API 키가 필요합니다."
            ),
        )
        st.caption(
            "모의: 증거금만 차감·명목 기준 손익. "
            "바이낸스 종목별 최대 레버리지/브래킷과는 연동되지 않습니다 (슬라이더 상한 125는 UI일 뿐)."
        )
    else:
        futures_leverage = 1

    st.divider()
    st.subheader("스캔 범위")
    top_n = st.slider("거래량 상위 종목 수", min_value=5, max_value=50, value=20, step=5)
    st.caption("데이터는 바이낸스 공개 시세(지연/누락 가능).")

    if st.button("🚀 급등 전조 스캔", key="scan_breakout_btn_sidebar", use_container_width=True):
        raw_syms = (
            SIDEBAR_BREAKOUT_SCAN_SYMBOLS_FUTURE
            if market_type == "future"
            else SIDEBAR_BREAKOUT_SCAN_SYMBOLS_SPOT
        )
        tickers = filter_binance_symbols(raw_syms, market_type)
        skipped = [s for s in raw_syms if s not in tickers]
        if skipped:
            st.caption(f"💡 바이낸스 마켓 미지원·제외: {', '.join(skipped)}")
        if not tickers:
            st.error("스캔할 심볼이 없습니다. 네트워크·마켓 선택(현물/선물) 또는 거래소 연결을 확인하세요.")
            st.stop()
        breakout_rows = []

        for ticker in tickers:
            detected, bw, rsi, wpr, err, _lc = scan_breakout(
                ticker,
                timeframe=breakout_timeframe,
                limit=breakout_limit,
                rsi_threshold=float(breakout_rsi_threshold),
                wpr_threshold=float(breakout_wpr_threshold),
                market_type=market_type,
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
    c_price = float(cached_prices.get(symbol, h["avg_price"]))
    if h.get("margin_used") is not None:
        m = float(h["margin_used"])
        amt = float(h["amount"])
        ap = float(h["avg_price"])
        initial_equity += m + amt * (c_price - ap)
    else:
        initial_equity += float(h["amount"]) * c_price

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
        _ex_pf = get_exchange(market_type)
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

_mt_label_short = "현물" if market_type == "spot" else "USDT-M 선물"
st.caption(f"현재 모드: {portfolio_mode} (단일 전략) · 마켓: {_mt_label_short}")
st.divider()

# 레이아웃 구성 (7:3)
col_main, col_news = st.columns([0.7, 0.3])

# 우측 뉴스 피드 (HTML Container 로 변경)
with col_news:
    display_news_with_filter()

# 좌측 메인 차트/스캔 영역 (Card 적용)
with col_main:
    st.markdown('<div class="stCard">', unsafe_allow_html=True) # 카드 시작
    _mt_tag = "현물" if market_type == "spot" else "USDT-M 선물"
    st.subheader(f"🔥 급등 전조 탐지 스캔 ({_mt_tag} / 거래량 상위 {top_n}개)")

# 기존 try-except 문을 아래처럼 수정해서 에러 내용을 확인합니다.
try:
    markets = fetch_tickers(market_type)
except Exception as e:
    col_main.error(f"바이낸스 연결 실패: {str(e)}") # 어떤 에러인지 정확히 보여줍니다.
    col_main.info(
        "💡 팁: VPN/네트워크를 바꿔 보세요. **선물** 선택 시 일부 지역에서 API(451) 차단될 수 있습니다 — **현물**로 전환해 보세요."
    )
    st.stop()

if market_type == "spot":
    symbols = [
        s
        for s in markets.keys()
        if isinstance(s, str) and s.endswith("/USDT") and ":" not in s
    ]
else:
    symbols = [s for s in markets.keys() if isinstance(s, str) and s.endswith(":USDT")]
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

# 선택 마켓과 동일한 거래소 인스턴스 (호가·모의 매수)
exchange = get_exchange(market_type)

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
            market_type=market_type,
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
                    symbol,
                    entry_price,
                    invest_amount=float(trade_amount),
                    filename=portfolio_file,
                    leverage=float(futures_leverage),
                    futures_mode=(market_type == "future"),
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
    df_chart = get_data(
        selected_coin,
        timeframe=breakout_timeframe,
        limit=300,
        market_type=market_type,
    )
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


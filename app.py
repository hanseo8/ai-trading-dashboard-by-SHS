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
import requests


# 페이지 설정
st.set_page_config(page_title="은둔고수 트레이딩 보드", layout="wide")


@st.cache_resource
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
        df["wpr"] = ta.willr(df["high"], df["low"], df["close"], length=14)
        df["vol_ma"] = ta.sma(df["volume"], length=10)
        df["rsi14"] = ta.rsi(df["close"], length=14)

        # 결측치가 있는 초기 구간 제거(지표 안정화)
        df = df.dropna().reset_index(drop=True)
        if len(df) < 3:
            return None
        return df
    except Exception:
        return None


def fmt_price(x: float) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "-"
    if x >= 1000:
        return f"{x:,.2f}"
    if x >= 1:
        return f"{x:,.4f}"
    return f"{x:,.8f}"


def safe_quote_volume(markets: dict, symbol: str) -> float:
    try:
        v = markets.get(symbol, {}).get("quoteVolume", None)
        if v is None:
            return 0.0
        return float(v)
    except Exception:
        return 0.0


# 상단 헤더
st.title("📈 AI 자동매매 실시간 상황판")

# 목표 수익 / 달성률 설정 (임시: 실현 손익 0 기준)
TARGET_PROFIT_USDT = 100.0
current_profit_usdt = 0.0  # TODO: 실제 실현 손익 연동 가능
achievement_rate = (current_profit_usdt / TARGET_PROFIT_USDT * 100.0) if TARGET_PROFIT_USDT > 0 else 0.0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("오늘의 목표 수익", f"{TARGET_PROFIT_USDT:.0f} USDT")
col2.metric("달성률", f"{achievement_rate:.1f}%")
col3.metric("현재 운용 시드", "100 USDT")
col4.metric("알고리즘 상태", "정상 작동 중", delta="Active")
col5.metric("마지막 갱신", datetime.now().strftime("%H:%M:%S"))


with st.sidebar:
    st.subheader("설정")
    timeframe = st.selectbox("타임프레임", ["15m", "1h", "4h", "1d"], index=1)
    top_n = st.slider("스캔 개수", min_value=5, max_value=50, value=20, step=5)
    vol_mult = st.slider("거래량 조건(이동평균 대비 배수)", 1.0, 5.0, 2.0, 0.1)
    wpr_level = st.slider("WPR 기준선(과매도 탈출)", -95, -50, -85, 1)
    st.caption("데이터는 바이낸스 공개 시세(지연/누락 가능).")


# 종목 리스트 및 신호 확인
st.divider()
st.subheader("🔥 실시간 정밀 스캔 (USDT 마켓)")

# 기존 try-except 문을 아래처럼 수정해서 에러 내용을 확인합니다.
try:
    markets = fetch_tickers()
except Exception as e:
    st.error(f"바이낸스 연결 실패: {str(e)}") # 어떤 에러인지 정확히 보여줍니다.
    st.info("💡 팁: VPN을 사용 중이라면 끄거나, 반대로 인터넷 환경이 불안정하면 다른 와이파이/핫스팟으로 시도해 보세요.")
    st.stop()

symbols = [s for s in markets.keys() if isinstance(s, str) and s.endswith("/USDT")]
top_symbols = sorted(symbols, key=lambda x: safe_quote_volume(markets, x), reverse=True)[: int(top_n)]

status_data = []
progress = st.progress(0, text="스캔 중…")
for i, symbol in enumerate(top_symbols, start=1):
    df = get_data(symbol, timeframe=timeframe, limit=200)
    if df is None:
        progress.progress(i / len(top_symbols), text=f"스캔 중… ({i}/{len(top_symbols)})")
        continue

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # 조건 체크
    is_trend = bool(last["ema7"] > last["ema25"] and last["close"] > last["ema99"])
    is_wpr = bool(prev["wpr"] < wpr_level and last["wpr"] > wpr_level)
    is_vol = bool(last["volume"] > (last["vol_ma"] * float(vol_mult)))

    signal = "🚀 강력 매수" if (is_trend and is_wpr and is_vol) else "관망"

    vol_ratio = None
    try:
        vol_ratio = float(last["volume"]) / float(last["vol_ma"]) if float(last["vol_ma"]) else None
    except Exception:
        vol_ratio = None

    status_data.append(
        {
            "종목": symbol,
            "현재가": float(last["close"]),
            "Williams %R": round(float(last["wpr"]), 2),
            "RSI(14)": round(float(last["rsi14"]), 1) if "rsi14" in last else None,
            "거래량 비율": f"{round(vol_ratio, 1)}배" if vol_ratio is not None else "-",
            "신호": signal,
        }
    )

    progress.progress(i / len(top_symbols), text=f"스캔 중… ({i}/{len(top_symbols)})")

progress.empty()

df_status = pd.DataFrame(status_data)
if df_status.empty:
    st.warning("스캔 결과가 없습니다(데이터 누락/지표 계산 불가). 설정을 바꾸거나 잠시 후 다시 시도해 주세요.")
else:
    # 보기 좋게 포맷(표시용)
    df_view = df_status.copy()
    df_view["현재가"] = df_view["현재가"].map(fmt_price)
    st.dataframe(df_view, use_container_width=True, hide_index=True)


# 상세 차트 보기 (선택한 종목)
st.divider()
st.subheader("📊 상세 차트")

if df_status.empty:
    st.info("먼저 스캔 결과가 있어야 상세 차트를 볼 수 있어요.")
    st.stop()

selected_coin = st.selectbox("상세 차트 분석", df_status["종목"].tolist())
df_chart = get_data(selected_coin, timeframe=timeframe, limit=300)
if df_chart is None:
    st.error("해당 종목의 차트 데이터를 불러오지 못했습니다.")
    st.stop()

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

st.plotly_chart(fig, use_container_width=True)


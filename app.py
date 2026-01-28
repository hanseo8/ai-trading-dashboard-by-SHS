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
import paper_trading as pt


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
        df["wpr"] = ta.willr(df["high"], df["low"], df["close"], length=14)
        df["vol_ma"] = ta.sma(df["volume"], length=10)
        df["vol_ma"] = ta.sma(df["volume"], length=10)
        df["rsi14"] = ta.rsi(df["close"], length=14)

        # 추가 지표 (전략별)
        # 1. MACD (중립적)
        macd = ta.macd(df["close"])
        if macd is not None:
            df = pd.concat([df, macd], axis=1)
        
        # 2. Bollinger Bands (보수적)
        bb = ta.bbands(df["close"], length=20, std=2)
        if bb is not None:
            df = pd.concat([df, bb], axis=1)

        # 3. ATR (공격적)
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)
        if "atr" in df.columns:
            df["atr_ma"] = ta.sma(df["atr"], length=20) # ATR 이동평균 (변동성 돌파 확인용)

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

# 포트폴리오 로드
current_prices = {} # 현재가 수집용
portfolio = pt.get_portfolio_status(current_prices)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("오늘의 목표 수익", f"{TARGET_PROFIT_USDT:.0f} USDT")
col2.metric("달성률", f"{achievement_rate:.1f}%")
col3.metric("모의투자 평가금액", f"{portfolio['total_asset']:,.2f} USDT", delta=f"{portfolio['total_pnl']:,.2f} ({portfolio['total_pnl_pct']:.2f}%)")
col4.metric("잔액(예수금)", f"{portfolio['balance']:,.2f} USDT")
col5.metric("마지막 갱신", datetime.now().strftime("%H:%M:%S"))


with st.sidebar:
    st.subheader("설정")
    timeframe = st.selectbox("타임프레임", ["15m", "1h", "4h", "1d"], index=1)
    top_n = st.slider("스캔 개수", min_value=5, max_value=50, value=20, step=5)
    vol_mult = st.slider("거래량 조건(이동평균 대비 배수)", 1.0, 5.0, 2.0, 0.1)
    wpr_level = st.slider("WPR 기준선(과매도 탈출)", -95, -50, -85, 1)
    st.caption("데이터는 바이낸스 공개 시세(지연/누락 가능).")
    
    st.divider()
    st.subheader("자동 갱신")
    auto_refresh = st.checkbox("자동 새로고침 켜기", value=True)
    refresh_sec = st.slider("갱신 주기(초)", 5, 60, 5)


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

    # 기본 조건 (공통)
    is_trend = bool(last["ema7"] > last["ema25"] and last["close"] > last["ema99"])
    is_wpr = bool(prev["wpr"] < wpr_level and last["wpr"] > wpr_level)
    is_vol = bool(last["volume"] > (last["vol_ma"] * float(vol_mult)))
    base_signal = is_trend and is_wpr and is_vol

    # 전략별 조건
    # 1. 보수적 (Safe): 볼린저 밴드 상단 돌파 시 매수 금지 (과열 방지)
    # BBU_20_2.0 컬럼 확인 필요
    bbu = last.get("BBU_20_2.0")
    bbm = last.get("BBM_20_2.0")
    is_conservative = False
    if base_signal and bbu is not None:
        # 밴드 중간보다 위에 있고, 상단을 뚫지는 않았을 때 (안전 구간)
        if last["close"] > bbm and last["close"] < bbu:
            is_conservative = True

    # 2. 중립적 (Neutral): MACD 골든크로스/상승 추세 확인
    # MACDh_12_26_9 (Histogram) > 0
    hist = last.get("MACDh_12_26_9")
    is_neutral = False
    if base_signal and hist is not None:
        # 히스토그램이 양수 (상승 모멘텀)
        if hist > 0:
            is_neutral = True

    # 3. 공격적 (Aggressive): 변동성 돌파 (ATR 상승)
    atr = last.get("atr")
    atr_ma = last.get("atr_ma")
    is_aggressive = False
    if base_signal and atr is not None and atr_ma is not None:
        # 변동성이 평균보다 높아짐 (큰 움직임 예상)
        if atr > atr_ma:
            is_aggressive = True

    # 하나라도 해당되면 표시
    if is_conservative or is_neutral or is_aggressive:
        common_data = {
            "종목": symbol,
            "현재가": float(last["close"]),
            "WPR": round(float(last["wpr"]), 2),
            "RSI": round(float(last["rsi14"]), 1) if "rsi14" in last else None,
        }
        
        if is_conservative:
            status_data.append({**common_data, "전략": "🛡️ 보수적", "신호": "안전 진입"})
        if is_neutral:
            status_data.append({**common_data, "전략": "⚖️ 중립적", "신호": "추세 확인"})
        if is_aggressive:
            status_data.append({**common_data, "전략": "⚔️ 공격적", "신호": "변동성 돌파"})

    # 모의 매수 (어떤 전략이든 강력 신호면 매수)
    buy_msg = None
    if is_conservative or is_neutral or is_aggressive:
        # 중복 매수 방지
        if symbol in portfolio["holdings"] and portfolio["holdings"][symbol]["amount"] > 0:
             buy_msg = "보유 중 (스킵)"
        else:
            success, msg = pt.buy_coin(symbol, float(last["close"]), invest_amount=100.0)
            # 로그는 너무 길어지니 생략하거나 가장 강력한 전략 하나만 표시
            
    progress.progress(i / len(top_symbols), text=f"스캔 중… ({i}/{len(top_symbols)})")

progress.empty()

# 탭으로 분리하여 표시
tab1, tab2, tab3 = st.tabs(["🛡️ 보수적 (안전)", "⚖️ 중립적 (정확)", "⚔️ 공격적 (수익)"])

df_all = pd.DataFrame(status_data)

def show_strategy_list(strategy_name):
    if df_all.empty:
        st.info("검색된 종목이 없습니다.")
        return
    
    subset = df_all[df_all["전략"] == strategy_name].copy()
    if subset.empty:
        st.warning(f"'{strategy_name}' 조건에 맞는 종목이 없습니다.")
    else:
        # 중복 제거 (한 종목이 여러 전략에 걸릴 수 있음 -> 리스트에는 각각 표시됨)
        # 보기 좋게 포맷
        subset["현재가"] = subset["현재가"].map(fmt_price)
        st.dataframe(subset, use_container_width=True, hide_index=True)

with tab1:
    st.caption("볼린저 밴드 내부에서 안정적인 상승을 노립니다 (과열 종목 제외).")
    show_strategy_list("🛡️ 보수적")
with tab2:
    st.caption("MACD 모멘텀이 살아있는 확실한 추세를 따릅니다.")
    show_strategy_list("⚖️ 중립적")
with tab3:
    st.caption("변동성(ATR)이 확대되는 구간에서 큰 수익을 노립니다.")
    show_strategy_list("⚔️ 공격적")

# 포트폴리오 상세
st.divider()
st.subheader("💼 내 포트폴리오 (모의투자)")

# 현재가 갱신을 위해 스캔된 데이터 활용 (또는 별도 조회 필요)
# 위 루프에서 현재가가 있다면 업데이트
for d in status_data:
    current_prices[d["종목"]] = d["현재가"]

portfolio_updated = pt.get_portfolio_status(current_prices)
if not portfolio_updated["details"]:
    st.info("보유 중인 코인이 없습니다.")
else:
    df_pf = pd.DataFrame(portfolio_updated["details"])
    st.dataframe(df_pf, use_container_width=True, hide_index=True)

with st.sidebar:
    if st.button("포트폴리오 초기화"):
        pt.reset_portfolio()
        st.rerun()


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


# 자동 갱신 로직 (마지막에 위치)
if auto_refresh:
    time.sleep(refresh_sec)
    st.rerun()


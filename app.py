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
st.set_page_config(page_title="서한석의 코인 자동매매", layout="wide")

# 1. 제목 (중앙 정렬 + 밑줄 장식)
st.markdown("""
<div style='text-align: center;'>
    <h1 style='display: inline-block; border-bottom: 3px solid #FF4B4B; padding-bottom: 10px;'>서한석의 코인 자동매매 실시간 상황판</h1>
</div>
""", unsafe_allow_html=True)

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

with st.sidebar:
    st.subheader("설정")
    timeframe = st.selectbox("타임프레임", ["5m", "15m", "1h", "4h", "1d"], index=1)
    top_n = st.slider("스캔 개수", min_value=5, max_value=50, value=20, step=5)
    vol_mult = st.slider("거래량 조건(이동평균 대비 배수)", 1.0, 5.0, 1.1, 0.1) # 기본값 1.1로 완화
    wpr_level = st.slider("WPR 기준선(과매도 탈출)", -95, -50, -85, 1)
    st.caption("데이터는 바이낸스 공개 시세(지연/누락 가능).")
    
    st.divider()
    st.subheader("자동 갱신")
    auto_refresh = st.checkbox("자동 새로고침 켜기", value=True)
    refresh_sec = st.slider("갱신 주기(초)", 5, 60, 5)

# 포트폴리오 파일 결정 (단타/장기)
if timeframe in ["5m", "15m"]:
    portfolio_mode = "단타 (Scalping)"
    portfolio_file = "portfolio_scalping.json"
else:
    portfolio_mode = "장기 (Long-Term)"
    portfolio_file = "portfolio_long.json"

# 상단 포트폴리오 요약
pf_init = pt.load_portfolio(portfolio_file)

st.divider()
col1, col2, col3, col4, col5 = st.columns(5)

# 평가금액 계산을 위해 간단히 예전 기록이나(없으면) 초기값 사용
# 정확한 PnL은 아래 스캔 루프가 돌아야 현재가를 아는데, 
# 헤더는 먼저 뜨므로 일단 예수금/초기자금 위주로 표시하고 '갱신 중' 느낌을 줌
with col1:
    st.metric("오늘의 목표 수익", "100 USDT")
with col2:
    st.metric("달성률", "0.0%")
with col3:
    st.metric(f"모의투자 평가금액", f"{pf_init['balance']:.2f} USDT", "갱신 대기")
with col4:
    st.metric("잔액(예수금)", f"{pf_init['balance']:.2f} USDT")
with col5:
    st.metric("마지막 갱신", datetime.now().strftime("%H:%M:%S"))

st.caption(f"현재 모드: {portfolio_mode} - 타임프레임에 따라 계좌가 자동 전환됩니다.")
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


current_prices = {}
status_data = []
progress = st.progress(0, text="스캔 중…")
for i, symbol in enumerate(top_symbols, start=1):
    df = get_data(symbol, timeframe=timeframe, limit=200)
    if df is None:
        progress.progress(i / len(top_symbols), text=f"스캔 중… ({i}/{len(top_symbols)})")
        continue

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # --- 전략 판별 로직 ---

    # 1. 단기 전략 (Short-term)
    # EMA 7/25 골든크로스 + Williams %R 과매도 탈출 (-80 상향 돌파)
    # is_st_trend: 단기 정배열
    try:
        is_st_trend = bool(last["ema7"] > last["ema25"])
    except:
        is_st_trend = False
        
    # is_st_signal: WPR -80 상향 돌파
    is_st_signal = bool(prev["wpr"] < -80 and last["wpr"] > -80)
    
    st_score = "🚀 단기 매수" if (is_st_trend and is_st_signal) else "관망"

    # 2. 장기 전략 (Long-term)
    # 가격이 EMA 99 위 + RSI가 50~70 사이 (안정적 상승 구간)
    is_lt_trend = bool(last["close"] > last["ema99"])
    is_lt_rsi = bool(50 < last["rsi14"] < 70) if "rsi14" in last else False
    
    lt_score = "� 장기 보유" if (is_lt_trend and is_lt_rsi) else "비중 축소"

    # 데이터프레임 기록용
    status_data.append({
        "종목": symbol,
        "현재가": float(last["close"]),
        "단기 신호": st_score,
        "장기 전략": lt_score,
        "RSI": round(float(last["rsi14"]), 1) if "rsi14" in last else None,
        "WPR": round(float(last["wpr"]), 2)
    })

    # 모의 매수 (현재 모드에 맞춰서)
    buy_msg = None
    should_buy = False
    
    if portfolio_mode.startswith("단타"):
        if st_score == "🚀 단기 매수":
            should_buy = True
    elif portfolio_mode.startswith("장기"):
        if lt_score == "💎 장기 보유":
            should_buy = True
            
    if should_buy:
        # 중복 매수 방지
        curr_pf = pt.load_portfolio(portfolio_file)
        if symbol in curr_pf["holdings"] and curr_pf["holdings"][symbol]["amount"] > 0:
             buy_msg = "보유 중 (스킵)"
        else:
            success, msg = pt.buy_coin(symbol, float(last["close"]), invest_amount=100.0, filename=portfolio_file)
            
    progress.progress(i / len(top_symbols), text=f"스캔 중… ({i}/{len(top_symbols)})")

progress.empty()

# 화면 상단에 라디오 버튼 추가
portfolio_view = st.radio("포트폴리오 보기", ["전체", "단기 스캘핑", "장기 스윙"], horizontal=True)

df_all = pd.DataFrame(status_data)

if df_all.empty:
    st.info("검색된 종목이 없습니다.")
else:
    df_view = df_all.copy()
    
    # 필터링
    if portfolio_view == "단기 스캘핑":
        # 단기 매수 신호가 있거나 관망인 종목 중 추세 좋은것? 
        # 사용자는 "단기 신호"가 "🚀 단기 매수" 인 것을 중요하게 볼 것임.
        # 하지만 너무 적으면 심심하니 전체 리스트에서 필터링
        df_filtered = df_view[df_view["단기 신호"] == "🚀 단기 매수"]
        if df_filtered.empty: # 없으면 전체 보여주되 메시지
             st.warning("현재 '🚀 단기 매수' 신호가 뜬 종목이 없습니다. (전체 목록 표시)")
             df_filtered = df_view
    elif portfolio_view == "장기 스윙":
        df_filtered = df_view[df_view["장기 전략"] == "💎 장기 보유"]
        if df_filtered.empty:
             st.warning("현재 '💎 장기 보유' 구간인 종목이 없습니다. (전체 목록 표시)")
             df_filtered = df_view
    else:
        df_filtered = df_view

    # 보기 좋게 포맷
    if not df_filtered.empty:
        df_filtered["현재가"] = df_filtered["현재가"].map(fmt_price)
        
        # 스타일 적용 함수
        def highlight_signal(val):
            if "🚀" in str(val): # 단기 매수
                return "background-color: #ff4b4b; color: white; font-weight: bold"
            elif "💎" in str(val): # 장기 보유
                return "background-color: #00cc96; color: white; font-weight: bold"
            return ""

        st.dataframe(
            df_filtered.style.map(highlight_signal, subset=["단기 신호", "장기 전략"]),
            use_container_width=True,
            hide_index=True
        )

# 포트폴리오 상세
st.divider()
st.subheader(f"💼 내 포트폴리오 ({portfolio_mode})")

# 현재가 갱신을 위해 스캔된 데이터 활용 (또는 별도 조회 필요)
# 위 루프에서 현재가가 있다면 업데이트
for d in status_data:
    current_prices[d["종목"]] = d["현재가"]

portfolio_updated = pt.get_portfolio_status(current_prices, filename=portfolio_file)
if not portfolio_updated["details"]:
    st.info("보유 중인 코인이 없습니다.")
else:
    df_pf = pd.DataFrame(portfolio_updated["details"])
    st.dataframe(df_pf, use_container_width=True, hide_index=True)

with st.sidebar:
    if st.button("포트폴리오 초기화"):
        pt.reset_portfolio(filename=portfolio_file)
        st.rerun()


# 상세 차트 보기 (선택한 종목)
st.divider()
st.subheader("📊 상세 차트")

if df_all.empty:
    st.info("현재 스캔된 종목이 없어 차트를 표시할 수 없습니다.")
    # 검색된 종목이 없어도 빈 차트라도 띄우거나, 수동 입력 칸을 줄 수도 있음.
    # 여기서는 안내 문구만 수정
else:
    selected_coin = st.selectbox("상세 차트 분석", df_all["종목"].tolist())
    df_chart = get_data(selected_coin, timeframe=timeframe, limit=300)
    if df_chart is None:
        st.error("해당 종목의 차트 데이터를 불러오지 못했습니다.")
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

        st.plotly_chart(fig, use_container_width=True)


# 자동 갱신 로직 (마지막에 위치)
if auto_refresh:
    time.sleep(refresh_sec)
    st.rerun()


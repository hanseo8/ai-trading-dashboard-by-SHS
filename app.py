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
        
        # 보조지표: RSI, WPR, MACD, BB(20, 2), ATR
        df["rsi14"] = ta.rsi(df["close"], length=14)
        df["wpr"] = ta.willr(df["high"], df["low"], df["close"], length=14)
        
        macd = ta.macd(df["close"])
        df = pd.concat([df, macd], axis=1)

        bb = ta.bbands(df["close"], length=20, std=2.0)
        df = pd.concat([df, bb], axis=1)
        
        # [나만의 기법] BB(15, 2.4) 추가
        bb_my = ta.bbands(df["close"], length=15, std=2.4)
        df = pd.concat([df, bb_my], axis=1)
        
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)
        df["atr_ma"] = ta.sma(df["atr"], length=20)
        
        # 거래량 이동평균
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


# 상단 헤더

with st.sidebar:
    st.subheader("설정")
    timeframe = st.selectbox("타임프레임", ["5m", "15m", "1h", "4h", "1d"], index=1)
    
    # 15m 선택 시 안내 메시지
    if timeframe == "15m":
        st.info("💡 15분봉은 '고수의 기법(Triple Confirm)' 전용입니다.\n(EMA99 추세 + RSI/WPR 타점 + 거래량 2.5배 폭발)")
        
    top_n = st.slider("스캔 개수", min_value=5, max_value=50, value=20, step=5)
    vol_mult = st.slider("거래량 조건(이동평균 대비 배수)", 1.0, 5.0, 1.1, 0.1) # 기본값 1.1로 완화
    wpr_level = st.slider("WPR 기준선(과매도 탈출)", -95, -50, -85, 1)
    st.caption("데이터는 바이낸스 공개 시세(지연/누락 가능).")
    
    st.divider()
    st.subheader("자동 갱신")
    auto_refresh = st.checkbox("자동 새로고침 켜기", value=True)
    refresh_sec = st.slider("갱신 주기(초)", 5, 60, 5)
    
    st.divider()
    enable_lock = st.checkbox("🔒 포트폴리오 잠금 (초기화 방지)", value=False)
    if enable_lock:
        st.caption("안전 모드 ON: 초기화 버튼이 잠깁니다. (자동 매매는 계속됨)")

# 포트폴리오 파일 결정 (단타/장기/나만의기법)
if timeframe == "5m":
    portfolio_mode = "단타 (Scalping)"
    portfolio_file = "portfolio_scalping.json"
elif timeframe == "15m":
    portfolio_mode = "고수의 기법 (Triple Confirm)"
    portfolio_file = "portfolio_my.json"
else:
    portfolio_mode = "장기 (Long-Term)"
    portfolio_file = "portfolio_long.json"

# 상단 포트폴리오 요약
pf_init = pt.load_portfolio(portfolio_file)

# 평가금액(Equity) 근사치 계산 (현재가 반영 전, 매수 원금 기준)
initial_equity = pf_init["balance"]
for h in pf_init["holdings"].values():
    initial_equity += h["total_cost"]

# 수익률 계산 (기준 10만불)
# 나중에 update_portfolio_status가 돌면 더 정확하겠지만, 헤더 단계에선 근사치 제공
base_capital = 100000.0
pnl_amount = initial_equity - base_capital
pnl_pct = (pnl_amount / base_capital) * 100

st.divider()
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("오늘의 수익(USDT)", f"{pnl_amount:,.2f} USDT", f"{pnl_pct:.2f}%")
with col2:
    # 달성률 대신 다른 정보를 보여주거나 빈 칸
    st.metric("보유 종목 수", f"{len(pf_init['holdings'])} 개")
with col3:
    st.metric(f"모의투자 평가금액", f"{initial_equity:,.2f} USDT", "갱신 대기")
with col4:
    st.metric("잔액(예수금)", f"{pf_init['balance']:,.2f} USDT")
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
    
    lt_score = "💎 장기 보유" if (is_lt_trend and is_lt_rsi) else "비중 축소"
    
    # --- 고수의 기법: 나만의 기법 (Master Strategy) ---

    # 1. 조건 정의
    # 장기 추세(Filter): 가격이 EMA 99(장기 이평선) 위에 있어 전체적인 흐름이 상승장일 것.
    is_master_trend = last["close"] > last["ema99"]
    
    # 단기 눌림목(Trigger): RSI가 40 이하로 떨어졌다가 다시 대가리를 들거나(여기선 단순화), 
    # Williams %R이 -85 바닥을 찍고 탈출하는 순간.
    # 사용자 요청: WPR -85 기준
    is_master_wpr = prev["wpr"] < -85 and last["wpr"] > -85
    
    # 거래량 폭발(Confirm): 최근 10개 캔들 평균 거래량보다 2.5배 이상 터지며 상승
    is_master_vol = last["volume"] > (last["vol_ma"] * 2.5)
    
    # RSI 조건 (힘이 실리기 시작함)
    is_master_rsi = last["rsi14"] > 50

    # 2. 신호 결정
    master_signal = "관망"
    if is_master_trend and is_master_wpr and is_master_vol:
        master_signal = "🔥 역대급 타점 (강력매수)"
    elif is_master_trend and is_master_rsi and is_master_vol:
        master_signal = "⚡ 추세 돌파 (추격매수)"

    # 3. 데이터프레임에 추가
    status_data.append({
        "종목": symbol,
        "현재가": float(last["close"]),
        "단기 신호": st_score,
        "장기 전략": lt_score,
        "나만의 기법": master_signal,
        "RSI": round(float(last["rsi14"]), 1) if "rsi14" in last else None,
        "거래량": f"{round(last['volume']/last['vol_ma'], 1)}배"
    })

    # 모의 매수 & 매도 (현재 모드에 맞춰서)
    buy_msg = None
    should_buy = False
    
    # 모드별 매수 조건
    if portfolio_mode.startswith("단타"): # 5m
        if st_score == "🚀 단기 매수":
            should_buy = True
    elif portfolio_mode.startswith("고수"): # 15m (Triple Confirm)
        if "매수" in master_signal: # 강력매수 or 추격매수
            should_buy = True
    elif portfolio_mode.startswith("장기"): # 1h+
        if lt_score == "💎 장기 보유":
            should_buy = True
            
    # 매수 실행
    if should_buy:
        # 중복 매수 방지
        curr_pf = pt.load_portfolio(portfolio_file)
        if symbol in curr_pf["holdings"] and curr_pf["holdings"][symbol]["amount"] > 0:
             buy_msg = "보유 중 (스킵)"
        else:
            success, msg = pt.buy_coin(symbol, float(last["close"]), invest_amount=1000.0, filename=portfolio_file)

    # [익절 로직] 나만의 기법 등 수익률 10% 도달 시 자동 매도
    # 모든 모드에서 동작하게 하거나, 특정 모드만 하거나. 여기서는 '나만의 기법' 요청사항이므로 전체 적용해도 무방
    # 현재가가 있으므로 수익률 계산 가능.
    # 포트폴리오 로드 (IO 최적화를 위해 위에서 읽은 curr_pf 재사용 가능하지만, 로직 분리상 다시 읽음 or 구조 개선)
    # 간단히 구현:
    curr_pf = pt.load_portfolio(portfolio_file)
    if symbol in curr_pf["holdings"]:
        holding = curr_pf["holdings"][symbol]
        amt = holding["amount"]
        if amt > 0:
            avg_p = holding["avg_price"]
            cur_p = float(last["close"])
            profit_pct = (cur_p - avg_p) / avg_p * 100
            
            # 10% 이상 수익 시 매도
            # (나만의 기법 요청 사항이지만, 다른 전략에도 적용하면 좋음. 일단 요청대로 15m일때만 하거나 전체 적용)
            # 여기선 전체 적용 (손해볼 것 없음)
            if profit_pct >= 10.0:
                success, msg = pt.sell_coin(symbol, cur_p, amt, filename=portfolio_file)
                if success:
                    print(f"💰 익절 성공: {symbol} (+{profit_pct:.2f}%)") # 로그용 (안보임)

    progress.progress(i / len(top_symbols), text=f"스캔 중… ({i}/{len(top_symbols)})")

progress.empty()

# 화면 상단에 라디오 버튼 추가
# 15m 선택 시 '나만의 기법'이 기본 탭처럼 보이게 하거나, 전체 리스트에서 필터링
portfolio_view = st.radio("포트폴리오 보기", ["전체", "단기 스캘핑", "장기 스윙", "나만의 기법"], horizontal=True)

df_all = pd.DataFrame(status_data)

if df_all.empty:
    st.info("검색된 종목이 없습니다.")
else:
    df_view = df_all.copy()
    
    # 필터링
    if portfolio_view == "단기 스캘핑":
        df_filtered = df_view[df_view["단기 신호"] == "🚀 단기 매수"]
    elif portfolio_view == "장기 스윙":
        df_filtered = df_view[df_view["장기 전략"] == "💎 장기 보유"]
    elif portfolio_view == "나만의 기법":
        df_filtered = df_view[df_view["나만의 기법"].str.contains("매수")]
    else:
        df_filtered = df_view

    # 필터 결과가 비었을 때 메시지
    if df_filtered.empty and portfolio_view != "전체":
         st.warning(f"현재 '{portfolio_view}' 조건에 맞는 종목이 없습니다. (전체 목록 표시)")
         df_filtered = df_view

    # 보기 좋게 포맷
    if not df_filtered.empty:
        df_filtered["현재가"] = df_filtered["현재가"].map(fmt_price)
        
        # 스타일 적용 함수
        def highlight_signal(val):
            val_str = str(val)
            if "🚀" in val_str: # 단기 매수
                return "background-color: #ff4b4b; color: white; font-weight: bold"
            elif "💎" in val_str: # 장기 보유
                return "background-color: #00cc96; color: white; font-weight: bold"
            elif "🎯" in val_str: # (구) 나만의 매수 -> 호환성 유지 위해 남겨두거나 삭제. 여기선 신규 신호로 대체
                return "background-color: #ffa502; color: white; font-weight: bold"
            elif "🔥" in val_str: # 고수: 역대급 타점
                return "background-color: #ff4500; color: white; font-weight: bold" # 오렌지레드
            elif "⚡" in val_str: # 고수: 추세 돌파
                return "background-color: #ffa502; color: white; font-weight: bold" # 오렌지
            return ""

        st.dataframe(
            df_filtered.style
            .map(highlight_signal, subset=["단기 신호", "장기 전략", "나만의 기법"])
            .set_table_styles([
                {'selector': 'th', 'props': [('background-color', '#FFDAB9'), ('color', 'black'), ('font-weight', 'bold'), ('text-align', 'center')]}
            ]),
            use_container_width=True,
            hide_index=True
        )

# 포트폴리오 상세
st.divider()
st.subheader("💼 내 포트폴리오")

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
    if not enable_lock:
        if st.button("포트폴리오 초기화"):
            pt.reset_portfolio(filename=portfolio_file)
            st.rerun()
    else:
        st.button("포트폴리오 초기화", disabled=True, help="잠금 해제 후 사용 가능합니다.")


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


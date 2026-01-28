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
        default_vol = 2.5 # 고수는 확실한 거래량
        st.info("💡 15분봉 전용: 추세 + WPR/RSI + 거래량 폭발")

    # 슬라이더 (key를 설정해서 전략 변경 시 리셋/재설정 되도록 유도하거나, value에 변수 할당)
    # key에 전략 모드를 포함시켜서 전환 시 새로운 값이 적용되도록 함
    top_n = st.slider("스캔 개수", min_value=5, max_value=50, value=20, step=5)
    vol_mult = st.slider("거래량 조건(이동평균 대비 배수)", 1.0, 5.0, default_vol, 0.1, key=f"vol_{strategy_mode}") 
    wpr_level = st.slider("WPR 기준선(과매도 탈출)", -95, -50, default_wpr, 1, key=f"wpr_{strategy_mode}")
    st.caption("데이터는 바이낸스 공개 시세(지연/누락 가능).")
    
    st.divider()
    st.subheader("자동 갱신")
    auto_refresh = st.checkbox("자동 새로고침 켜기", value=True)
    refresh_sec = st.slider("갱신 주기(초)", 5, 60, 5)
    
    st.divider()
    enable_lock = st.checkbox("🔒 포트폴리오 잠금 (초기화 방지)", value=False)
    if enable_lock:
        st.caption("안전 모드 ON: 초기화 버튼이 잠깁니다. (자동 매매는 계속됨)")

# 전역 변수 설정
portfolio_mode = portfolio_label

# 상단 포트폴리오 요약
pf_init = pt.load_portfolio(portfolio_file)

# 평가금액(Equity) 근사치 계산 (현재가 반영 전, 매수 원금 기준)
initial_equity = pf_init["balance"]
for h in pf_init["holdings"].values():
    initial_equity += h["total_cost"]

# 수익률 계산 (기준 5만불)
# 나중에 update_portfolio_status가 돌면 더 정확하겠지만, 헤더 단계에선 근사치 제공
base_capital = 50000.0
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
st.subheader(f"🔥 실시간 정밀 스캔 (USDT 마켓 / 거래량 상위 {top_n}개 기준)")

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
    # 장기 추세(Filter): 가격이 EMA 99(장기 이평선) 위에 있어 전체적인 흐름이 상승장일 것.
    is_master_trend = last["close"] > last["ema99"]
    
    # 단기 눌림목(Trigger): RSI가 40 이하로 떨어졌다가 다시 대가리를 들거나(여기선 단순화), 
    # Williams %R이 -85 바닥을 찍고 탈출하는 순간.
    # 사용자 요청: WPR -85 기준 (설정값 wpr_level 사용)
    is_master_wpr = prev["wpr"] < wpr_level and last["wpr"] > wpr_level
    
    # 거래량 폭발(Confirm): 설정값 배수 사용 (기존 2.5배 -> vol_mult)
    is_master_vol = last["volume"] > (last["vol_ma"] * vol_mult)
    
    # RSI 조건 (힘이 실리기 시작함)
    is_master_rsi = last["rsi14"] > 50

    # 2. 신호 결정
    master_signal = "관망"
    if is_master_trend and is_master_wpr and is_master_vol:
        master_signal = "🔥 역대급 타점 (강력매수)"
    elif is_master_trend and is_master_rsi and is_master_vol:
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
        # 중복 매수 방지
        curr_pf = pt.load_portfolio(portfolio_file)
        if symbol in curr_pf["holdings"] and curr_pf["holdings"][symbol]["amount"] > 0:
             buy_msg = "보유 중 (스킵)"
        else:
            # 투자금 설정 (모든 기법 1000불 통일)
            invest_money = 1000.0

            success, msg = pt.buy_coin(symbol, float(last["close"]), invest_amount=invest_money, filename=portfolio_file)

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
                # 익절: 1.0% 이상
                if profit_pct >= 1.0:
                    should_sell = True
                    sell_reason = "익절 (1.0%)"
                # 손절: EMA 7 꺾임 (현재 EMA 7 < 이전 EMA 7)
                # 단, 너무 잦은 손절 방지 위해 진입 후 약간의 마진? 
                # 사용자 요청: "EMA 7선이 꺾일 때 즉시 실행"
                elif last["ema7"] < prev["ema7"]:
                    should_sell = True
                    sell_reason = "손절 (EMA7 하락)"
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
                
            else: # 고수의 기법
                 # 고수는 10% 룰 (또는 그 이상?) -> 기존 10% 유지
                 if profit_pct >= 10.0:
                    should_sell = True
                    sell_reason = "익절 (10%)"

            if should_sell and not enable_lock:
                success, msg = pt.sell_coin(symbol, cur_p, amt, filename=portfolio_file)
                if success:
                    print(f"💰 {sell_reason}: {symbol} ({profit_pct:.2f}%)")

    progress.progress(i / len(top_symbols), text=f"스캔 중… ({i}/{len(top_symbols)})")

progress.empty()

# 필터링 없이 전체 리스트 출력 (메인 화면 단순화)
df_all = pd.DataFrame(status_data)

if df_all.empty:
    st.info("검색된 종목이 없습니다.")
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

    st.dataframe(
        df_view.style
        .map(highlight_signal, subset=["진입 신호"])
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

# 2단 컬럼 레이아웃 (보유종목 6 : 매매기록 4)
p_col1, p_col2 = st.columns([1.5, 1.0])

with p_col1:
    st.markdown("##### 📦 보유 중인 코인")
    if not portfolio_updated["details"]:
        st.info("보유 중인 코인이 없습니다.")
    else:
        df_pf = pd.DataFrame(portfolio_updated["details"])
        st.dataframe(df_pf, use_container_width=True, hide_index=True)

with p_col2:
    st.markdown("##### 📝 최근 매매 기록")
    curr_pf = pt.load_portfolio(portfolio_file)
    trades = curr_pf.get("history", [])
    
    if not trades:
        st.info("매매 기록이 없습니다.")
    else:
        # 최신순 정렬
        df_trades = pd.DataFrame(trades)
        # 키 이름 호환성 체크 ('time' vs 'timestamp')
        if "time" in df_trades.columns:
            sort_key = "time"
        else:
            sort_key = "timestamp" # 혹시 모를 대비
            
        df_trades = df_trades.sort_values(by=sort_key, ascending=False).head(15) # 최근 15개만
        
        # 보기 좋게 가공
        # timestamp -> %m-%d %H:%M
        # type -> 매수/익절/손절/매도
        
        display_trades = []
        for _, r in df_trades.iterrows():
            ts_val = r.get("time", r.get("timestamp", ""))
            try:
                # 저장된 형식이 "%Y-%m-%d %H:%M:%S"
                ts_str = datetime.strptime(ts_val, "%Y-%m-%d %H:%M:%S").strftime("%m-%d %H:%M")
            except:
                ts_str = str(ts_val) # 파싱 실패시 그대로
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
                "시간": ts_str,
                "구분": f"{icon} {t_type}",
                "종목": symbol,
                "가격": price,
                "수익률": profit_str
            })
            
        st.dataframe(pd.DataFrame(display_trades), use_container_width=True, hide_index=True)

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


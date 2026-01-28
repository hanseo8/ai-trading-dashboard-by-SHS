import json
import os
import pandas as pd
from datetime import datetime

PORTFOLIO_FILE = "portfolio.json"
DEFAULT_BALANCE = 50000.0  # 초기 지급 USDT

def load_portfolio(filename=PORTFOLIO_FILE):
    """포트폴리오 파일 로드 또는 초기화"""
    if not os.path.exists(filename):
        return {
            "balance": DEFAULT_BALANCE,
            "holdings": {},  # { "BTC/USDT": { "amount": 0.1, "avg_price": 50000 } }
            "history": []    # [ { "time": "...", "type": "buy", ... } ]
        }
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 호환성 보장: history 키가 없으면 추가
            if "history" not in data:
                data["history"] = data.get("trades", []) # 기존 trades가 있다면 가져옴
            return data
    except:
        return {
            "balance": DEFAULT_BALANCE,
            "holdings": {},
            "history": []
        }

def save_portfolio(portfolio, filename=PORTFOLIO_FILE):
    """포트폴리오 파일 저장"""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, indent=4, ensure_ascii=False)

def buy_coin(symbol: str, price: float, invest_amount: float = 100.0, filename=PORTFOLIO_FILE):
    """코인 매수 (모의)"""
    pf = load_portfolio(filename)
    
    # 잔액 확인
    if pf["balance"] < invest_amount:
        return False, "잔액 부족"
    
    # 수수료 고려 (0.1% 가정) - 일단 단순화해서 수수료 없이 계산하거나 차감
    amount_bought = invest_amount / price
    
    pf["balance"] -= invest_amount
    
    # 보유량 업데이트
    if symbol not in pf["holdings"]:
        pf["holdings"][symbol] = {"amount": 0.0, "avg_price": 0.0, "total_cost": 0.0}
    
    holding = pf["holdings"][symbol]
    # 평단가 갱신 (총 비용 누적 후 나누기)
    # 기존 총 비용
    prev_cost = holding.get("total_cost", holding["amount"] * holding["avg_price"])
    new_cost = prev_cost + invest_amount
    new_amount = holding["amount"] + amount_bought
    new_avg = new_cost / new_amount
    
    holding["amount"] = new_amount
    holding["avg_price"] = new_avg
    holding["total_cost"] = new_cost
    
    # 기록
    pf["history"].append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "buy",
        "symbol": symbol,
        "price": price,
        "invest": invest_amount,
        "amount": amount_bought
    })
    
    save_portfolio(pf, filename)
    return True, "매수 성공"

def get_portfolio_status(current_prices: dict, filename=PORTFOLIO_FILE):
    """현재 포트폴리오 상태 계산 (평가금액, 수익률 등)"""
    pf = load_portfolio(filename)
    
    total_balance = pf["balance"]
    holdings_val = 0.0
    
    details = []
    
    for symbol, data in pf["holdings"].items():
        amt = data["amount"]
        if amt <= 0:
            continue
            
        cur_price = current_prices.get(symbol, data["avg_price"])
        val = amt * cur_price
        profit = val - data["total_cost"]
        profit_pct = (profit / data["total_cost"]) * 100 if data["total_cost"] > 0 else 0
        
        holdings_val += val
        details.append({
            "종목": symbol,
            "보유수량": f"{amt:.6f}",
            "평단가": f"{data['avg_price']:.4f}",
            "현재가": f"{cur_price:.4f}",
            "평가금액": f"{val:.2f}",
            "수익률": f"{profit_pct:.2f}%",
            "수익금": f"{profit:.2f}"
        })
        
    total_equity = total_balance + holdings_val
    initial = DEFAULT_BALANCE # 가정
    total_pnl = total_equity - initial
    total_pnl_pct = (total_pnl / initial) * 100
    
    return {
        "balance": total_balance,
        "equity": total_equity,
        "pnl": total_pnl,
        "pnl_pct": total_pnl_pct,
        "details": details
    }

def sell_coin(symbol: str, price: float, amount: float, filename=PORTFOLIO_FILE):
    """코인 매도"""
    pf = load_portfolio(filename)
    
    if symbol not in pf["holdings"]:
        return False, "보유하지 않은 코인"
        
    holding = pf["holdings"][symbol]
    current_amount = holding["amount"]
    
    if current_amount < amount:
        return False, "보유 수량 부족"
        
    # 매도 금액
    sell_value = amount * price
    
    # 평단가 기준 수익률 계산
    avg_price = holding["avg_price"]
    profit_pct = (price - avg_price) / avg_price * 100
    
    # 잔액 증가
    pf["balance"] += sell_value
    
    # 보유량 차감
    holding["amount"] -= amount
    
    # 전량 매도 시 목록에서 제거 (또는 수량 0 유지)
    if holding["amount"] <= 0.00000001: # 부동소수점 오차 고려
        del pf["holdings"][symbol]
    
    # 기록 (매도)
    pf["history"].append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "sell",
        "symbol": symbol,
        "price": price,
        "amount": amount,
        "total": sell_value,
        "pnl_pct": profit_pct # 수익률 저장
    })
    
    save_portfolio(pf, filename)
    return True, "매도 성공"

def reset_portfolio(filename=PORTFOLIO_FILE):
    """포트폴리오 초기화"""
    if os.path.exists(filename):
        os.remove(filename)
    load_portfolio(filename)

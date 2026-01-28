import json
import os
import pandas as pd
from datetime import datetime

PORTFOLIO_FILE = "portfolio.json"
DEFAULT_BALANCE = 1000.0  # 초기 지급 USDT

def load_portfolio():
    """포트폴리오 파일 로드 또는 초기화"""
    if not os.path.exists(PORTFOLIO_FILE):
        return {
            "balance": DEFAULT_BALANCE,
            "holdings": {},  # { "BTC/USDT": { "amount": 0.1, "avg_price": 50000, "trades": [] } }
            "history": []    # [ { "time": "...", "symbol": "...", "type": "buy", "price": 100, "amount": 1, "total": 100 } ]
        }
    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "balance": DEFAULT_BALANCE,
            "holdings": {},
            "history": []
        }

def save_portfolio(portfolio):
    """포트폴리오 파일 저장"""
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, indent=4, ensure_ascii=False)

def buy_coin(symbol: str, price: float, invest_amount: float = 100.0):
    """코인 매수 (모의)"""
    portfolio = load_portfolio()
    balance = portfolio.get("balance", 0.0)

    # 잔액 부족 체크
    if balance < invest_amount:
        return False, "잔액 부족"

    # 수량 계산
    amount = invest_amount / price

    # 잔액 차감
    portfolio["balance"] = balance - invest_amount

    # 보유량 업데이트
    holdings = portfolio.get("holdings", {})
    if symbol not in holdings:
        holdings[symbol] = {"amount": 0.0, "avg_price": 0.0, "total_cost": 0.0}
    
    current_holding = holdings[symbol]
    new_total_amount = current_holding["amount"] + amount
    new_total_cost = current_holding.get("total_cost", 0.0) + invest_amount
    new_avg_price = new_total_cost / new_total_amount

    holdings[symbol] = {
        "amount": new_total_amount,
        "avg_price": new_avg_price,
        "total_cost": new_total_cost
    }
    portfolio["holdings"] = holdings

    # 기록 추가
    portfolio["history"].append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": symbol,
        "type": "buy",
        "price": price,
        "amount": amount,
        "total": invest_amount
    })

    save_portfolio(portfolio)
    return True, "매수 성공"

def get_portfolio_status(current_prices: dict):
    """현재 포트폴리오 상태 계산 (평가금액, 수익률 등)"""
    portfolio = load_portfolio()
    balance = portfolio["balance"]
    holdings = portfolio["holdings"]
    
    total_asset = balance
    details = []

    for symbol, data in holdings.items():
        if data["amount"] <= 0:
            continue
            
        cur_price = current_prices.get(symbol, data["avg_price"]) # 현재가 없으면 평단가로 계산(변동없음)
        val = data["amount"] * cur_price
        cost = data["total_cost"]
        pnl = val - cost
        pnl_pct = (pnl / cost * 100) if cost > 0 else 0.0

        total_asset += val
        details.append({
            "종목": symbol,
            "보유수량": data["amount"],
            "평단가": data["avg_price"],
            "현재가": cur_price,
            "평가금액": val,
            "수익금": pnl,
            "수익률": pnl_pct
        })
    
    start_balance = DEFAULT_BALANCE # TODO: 필요시 초기자금 설정 기능 추가
    total_pnl = total_asset - start_balance
    total_pnl_pct = (total_pnl / start_balance * 100) if start_balance > 0 else 0.0

    return {
        "balance": balance,
        "total_asset": total_asset,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "details": details,
        "history": portfolio["history"]
    }

def reset_portfolio():
    """포트폴리오 초기화"""
    if os.path.exists(PORTFOLIO_FILE):
        os.remove(PORTFOLIO_FILE)
    load_portfolio()

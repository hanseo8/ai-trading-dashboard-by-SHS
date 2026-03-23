import json
import os
import shutil
import pandas as pd
from datetime import datetime

PORTFOLIO_FILE = "portfolio.json"
DEFAULT_BALANCE = 0.0  # 기본 모의 자금 없음 (앱에서 설정 시 입금)

def load_portfolio(filename=PORTFOLIO_FILE):
    """포트폴리오 파일 로드 또는 초기화"""
    if not os.path.exists(filename):
        return {
            "balance": DEFAULT_BALANCE,
            "holdings": {},
            "history": [],
            "starting_capital": 0.0,
        }
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 호환성 보장: history 키가 없으면 추가
            if "history" not in data:
                data["history"] = data.get("trades", [])
            if "starting_capital" not in data:
                data["starting_capital"] = 0.0
            return data
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        # 파일이 존재하는데 에러가 난 경우 (깨짐 등) -> 백업 후 초기화 (데이터 손실 방지용 백업)
        if os.path.exists(filename) and os.path.getsize(filename) > 0:
            backup_name = filename + ".bak"
            shutil.copy(filename, backup_name)
            print(f"Corrupted file backed up to {backup_name}")
            
        return {
            "balance": DEFAULT_BALANCE,
            "holdings": {},
            "history": [],
            "starting_capital": 0.0,
        }

def save_portfolio(portfolio, filename=PORTFOLIO_FILE):
    """포트폴리오 파일 저장"""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, indent=4, ensure_ascii=False)

def buy_coin(
    symbol: str,
    price: float,
    invest_amount: float = 100.0,
    filename=PORTFOLIO_FILE,
    leverage: float = 1.0,
    futures_mode: bool = False,
):
    """코인 매수 (모의). 선물: invest_amount=증거금(마진), 명목가치=마진×레버리지."""
    pf = load_portfolio(filename)
    lev = max(1.0, float(leverage or 1.0))

    if futures_mode:
        margin = float(invest_amount)
        notional = margin * lev
        if pf["balance"] < margin:
            return False, "잔액 부족"
        amount_bought = notional / price
        pf["balance"] -= margin

        if symbol not in pf["holdings"]:
            pf["holdings"][symbol] = {"amount": 0.0, "avg_price": 0.0, "total_cost": 0.0}

        holding = pf["holdings"][symbol]
        prev_cost = holding.get("total_cost", holding["amount"] * holding["avg_price"])
        new_cost = prev_cost + notional
        new_amount = holding["amount"] + amount_bought
        new_avg = new_cost / new_amount if new_amount > 0 else price

        holding["amount"] = new_amount
        holding["avg_price"] = new_avg
        holding["total_cost"] = new_cost
        holding["margin_used"] = float(holding.get("margin_used", 0.0)) + margin
        holding["leverage"] = lev

        pf["history"].append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "buy",
            "symbol": symbol,
            "price": price,
            "invest": margin,
            "amount": amount_bought,
            "leverage": lev,
            "notional": notional,
            "margin": margin,
        })

        save_portfolio(pf, filename)
        return True, "매수 성공 (선물·마진)"

    # --- 현물 ---
    if pf["balance"] < invest_amount:
        return False, "잔액 부족"

    amount_bought = invest_amount / price
    pf["balance"] -= invest_amount

    if symbol not in pf["holdings"]:
        pf["holdings"][symbol] = {"amount": 0.0, "avg_price": 0.0, "total_cost": 0.0}

    holding = pf["holdings"][symbol]
    prev_cost = holding.get("total_cost", holding["amount"] * holding["avg_price"])
    new_cost = prev_cost + invest_amount
    new_amount = holding["amount"] + amount_bought
    new_avg = new_cost / new_amount

    holding["amount"] = new_amount
    holding["avg_price"] = new_avg
    holding["total_cost"] = new_cost
    holding.pop("margin_used", None)
    holding.pop("leverage", None)

    pf["history"].append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "buy",
        "symbol": symbol,
        "price": price,
        "invest": invest_amount,
        "amount": amount_bought,
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
        avg_price = float(data["avg_price"])
        margin_used = data.get("margin_used")

        if margin_used is not None:
            m = float(margin_used)
            unrealized = amt * (float(cur_price) - avg_price)
            val = m + unrealized
            profit = unrealized
            profit_pct = (profit / m) * 100 if m > 0 else 0.0
            lev = float(data.get("leverage", 1.0))
            lev_s = f"{lev:.0f}x" if lev == int(lev) else f"{lev:.1f}x"
        else:
            val = amt * cur_price
            profit = val - data["total_cost"]
            profit_pct = (profit / data["total_cost"]) * 100 if data["total_cost"] > 0 else 0
            lev_s = "-"

        holdings_val += val
        row = {
            "종목": symbol,
            "레버리지": lev_s,
            "보유수량": f"{amt:.6f}",
            "평단가": f"{data['avg_price']:.4f}",
            "현재가": f"{cur_price:.4f}",
            "평가금액": f"{val:.2f}",
            "수익률": f"{profit_pct:.2f}%",
            "수익금": f"{profit:.2f}",
        }
        details.append(row)
        
    total_equity = total_balance + holdings_val
    initial = float(pf.get("starting_capital", DEFAULT_BALANCE))
    if initial <= 0:
        total_pnl = 0.0
        total_pnl_pct = 0.0
    else:
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

    avg_price = float(holding["avg_price"])
    profit_pct = (price - avg_price) / avg_price * 100
    margin_used = holding.get("margin_used")

    if margin_used is not None:
        m = float(margin_used)
        ratio = amount / current_amount
        released_margin = m * ratio
        unrealized = amount * (price - avg_price)
        pf["balance"] += released_margin + unrealized
        holding["margin_used"] = m - released_margin
        holding["amount"] -= amount
        holding["total_cost"] = holding["amount"] * holding["avg_price"] if holding["amount"] > 0 else 0.0
        sell_value = released_margin + unrealized
    else:
        sell_value = amount * price
        pf["balance"] += sell_value
        holding["amount"] -= amount

    if holding["amount"] <= 0.00000001:
        del pf["holdings"][symbol]

    pf["history"].append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "sell",
        "symbol": symbol,
        "price": price,
        "amount": amount,
        "total": sell_value,
        "pnl_pct": profit_pct,
    })

    save_portfolio(pf, filename)
    return True, "매도 성공"

def reset_portfolio(filename=PORTFOLIO_FILE):
    """포트폴리오 초기화"""
    if os.path.exists(filename):
        os.remove(filename)
    load_portfolio(filename)

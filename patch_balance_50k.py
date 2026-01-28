import json
import os

files = ["portfolio_scalping.json", "portfolio_long.json", "portfolio_my.json"]
target_balance = 50000.0

print(f"Patching portfolios to balance: {target_balance}...")

for f in files:
    if os.path.exists(f):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
            
            # 밸런스만 수정, 보유량은 유지 (또는 리셋하고 싶으면 아예 초기화)
            # 사용자 요청: "통장잔고는 50,000USD로 세팅 해줘" -> 기존 내역이 있다면 유지하되 잔고만 조정?
            # 아니면 아예 초기화? 보통 이런 요청은 "시작 금액" 재설정을 의미하므로
            # 보유중인 평단가/수량은 놔두고 balance를 50000으로 리셋하는건 회계상 안맞을 수 있음 (이미 산 돈이 빠져나갔어야 하므로)
            # 따라서 가장 깔끔한건 "완전 초기화" 혹은 "현재 자산 가치 + 현금 = 50000" 인데
            # 여기선 사용자가 "세팅 해줘"라고 했으므로 아예 초기화(Reset) 하는게 혼선이 적음.
            
            data["balance"] = target_balance
            data["holdings"] = {} # 보유종목 초기화 (새로운 마음으로)
            data["trades"] = []
            
            with open(f, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=4)
            print(f"[OK] {f} reset to {target_balance}")
            
        except Exception as e:
            print(f"[ERR] {f}: {e}")
    else:
        # 파일이 없으면 생성
        data = {"balance": target_balance, "holdings": {}, "trades": []}
        with open(f, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
        print(f"[NEW] {f} created with {target_balance}")

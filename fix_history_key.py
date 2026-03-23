import json
import os

files = ["portfolio_scalping.json", "portfolio_long.json", "portfolio_my.json"]

print("Fixing missing 'history' key in portfolios...")

for f in files:
    if os.path.exists(f):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
            
            modified = False
            if "history" not in data:
                print(f"[{f}] Missing 'history'. Fixing...")
                data["history"] = data.get("trades", [])
                modified = True
                
            if modified:
                with open(f, "w", encoding="utf-8") as file:
                    json.dump(data, file, ensure_ascii=False, indent=4)
                print(f"[{f}] Fixed.")
            else:
                print(f"[{f}] Already OK.")
            
        except Exception as e:
            print(f"[ERR] {f}: {e}")

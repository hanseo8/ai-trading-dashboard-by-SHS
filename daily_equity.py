# -*- coding: utf-8 -*-
"""
매일 09:00 (KST) 기준 자산 스냅샷 → 전일 09:00 대비 당일 09:00 까지 24h 수익률 (실거래소 일일 정산과 유사)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, time
from typing import Any, Dict, List

import pandas as pd

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore

KST = ZoneInfo("Asia/Seoul") if ZoneInfo else None


def snapshot_path(portfolio_file: str) -> str:
    base = os.path.splitext(os.path.basename(portfolio_file))[0]
    return f"{base}_daily_snapshots.json"


def _load(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"snapshots": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _today_9am_kst(now_kst: datetime) -> datetime:
    return now_kst.replace(hour=9, minute=0, second=0, microsecond=0)


def update_snapshots(equity: float, portfolio_file: str) -> Dict[str, Any]:
    """
    KST 기준 오늘 09:00 이후, 아직 오늘 날짜 스냅샷이 없으면 1건 추가.
    (대시보드가 9시 이후 처음 켜질 때 당일 오픈 자산으로 기록 — 실시간 9시 정확 시세는 앱 실행 시점 자산)
    """
    if KST is None:
        return {"snapshots": []}
    path = snapshot_path(portfolio_file)
    data = _load(path)
    snaps: List[Dict[str, Any]] = data.get("snapshots", [])
    now_kst = datetime.now(KST)
    today_str = now_kst.strftime("%Y-%m-%d")
    t9 = _today_9am_kst(now_kst)

    existing_dates = {s.get("date") for s in snaps}
    if now_kst >= t9 and today_str not in existing_dates:
        snaps.append(
            {
                "date": today_str,
                "equity": float(equity),
                "recorded_at": now_kst.isoformat(),
            }
        )
        snaps.sort(key=lambda x: x.get("date", ""))
    data["snapshots"] = snaps
    _save(path, data)
    return data


def build_daily_report(current_equity: float, portfolio_file: str) -> pd.DataFrame:
    """확정 구간(연속 스냅샷 쌍) + 마지막 스냅샷~현재 진행 행."""
    path = snapshot_path(portfolio_file)
    data = _load(path)
    snaps: List[Dict[str, Any]] = sorted(
        data.get("snapshots", []), key=lambda x: x.get("date", "")
    )
    rows: List[Dict[str, Any]] = []

    if not snaps:
        return pd.DataFrame(
            columns=[
                "기간 (KST)",
                "시작 자산 (D 09:00)",
                "종 자산 (D+1 09:00)",
                "24h 수익률",
                "상태",
            ]
        )

    for i in range(len(snaps) - 1):
        d0 = snaps[i].get("date", "")
        d1 = snaps[i + 1].get("date", "")
        try:
            e0 = float(snaps[i]["equity"])
            e1 = float(snaps[i + 1]["equity"])
        except (KeyError, TypeError, ValueError):
            continue
        ret = (e1 - e0) / e0 * 100.0 if e0 else 0.0
        rows.append(
            {
                "기간 (KST)": f"{d0} 09:00 → {d1} 09:00",
                "시작 자산 (D 09:00)": f"{e0:,.2f}",
                "종 자산 (D+1 09:00)": f"{e1:,.2f}",
                "24h 수익률": f"{ret:+.2f}%",
                "상태": "확정",
            }
        )

    # 진행 구간: 마지막 스냅샷 시점 ~ 현재
    last = snaps[-1]
    try:
        e0 = float(last["equity"])
        d0 = last.get("date", "")
    except (KeyError, TypeError, ValueError):
        return pd.DataFrame(rows)

    ret_live = (float(current_equity) - e0) / e0 * 100.0 if e0 else 0.0
    rows.append(
        {
            "기간 (KST)": f"{d0} 09:00 → 현재",
            "시작 자산 (D 09:00)": f"{e0:,.2f}",
            "종 자산 (D+1 09:00)": f"{float(current_equity):,.2f}",
            "24h 수익률": f"{ret_live:+.2f}%",
            "상태": "진행중 (당일/미결산)",
        }
    )

    return pd.DataFrame(rows)

"""生成每日市场简报（README.md）。数据全部来自公开接口，无需密钥。"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (market-digest/1.0)"}
WATCH = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LINK", "AVAX", "TON"]


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


def spot() -> dict[str, dict]:
    out = {}
    for row in get("https://api.gateio.ws/api/v4/spot/tickers"):
        cp = row.get("currency_pair", "")
        if not cp.endswith("_USDT"):
            continue
        base = cp[:-5]
        try:
            out[base] = {
                "last": float(row["last"]),
                "pct": float(row.get("change_percentage") or 0),
                "vol": float(row.get("quote_volume") or 0),
            }
        except (KeyError, ValueError, TypeError):
            continue
    return out


def funding() -> dict[str, float]:
    out = {}
    for row in get("https://api.gateio.ws/api/v4/futures/usdt/tickers"):
        name = row.get("contract", "")
        if name.endswith("_USDT"):
            try:
                out[name[:-5]] = float(row.get("funding_rate") or 0)
            except (ValueError, TypeError):
                continue
    return out


def fmt(v: float) -> str:
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 1:
        return f"{v:,.2f}"
    return f"{v:.6f}".rstrip("0").rstrip(".")


def main() -> None:
    now = datetime.now(timezone.utc)
    s = spot()
    f = funding()

    liquid = {k: v for k, v in s.items() if v["vol"] >= 3_000_000 and v["last"] > 0}
    movers = sorted(liquid.items(), key=lambda kv: kv[1]["pct"], reverse=True)
    gainers = [m for m in movers if m[1]["pct"] > 0][:10]
    losers = sorted(liquid.items(), key=lambda kv: kv[1]["pct"])[:10]

    print(f"# 市场日报 · {now:%Y-%m-%d}\n")
    print("> 数据来源：Gate.io 公开接口（USDT 现货 + USDT 永续）  ")
    print(f"> 生成时间：{now:%Y-%m-%d %H:%M} UTC ｜ 自动更新，无需人工干预\n")

    print("## 主流币\n")
    print("| 币种 | 价格 (USDT) | 24h 涨跌 | 24h 成交额 |")
    print("| --- | ---: | ---: | ---: |")
    for sym in WATCH:
        row = s.get(sym)
        if not row:
            continue
        print(f"| {sym} | {fmt(row['last'])} | {row['pct']:+.2f}% | ${row['vol']/1e6:.0f}M |")

    print("\n## 涨幅榜（成交额 ≥ $3M）\n")
    print("| 币种 | 价格 | 24h | 成交额 |")
    print("| --- | ---: | ---: | ---: |")
    for sym, row in gainers:
        print(f"| {sym} | {fmt(row['last'])} | {row['pct']:+.2f}% | ${row['vol']/1e6:.0f}M |")

    print("\n## 跌幅榜（成交额 ≥ $3M）\n")
    print("| 币种 | 价格 | 24h | 成交额 |")
    print("| --- | ---: | ---: | ---: |")
    for sym, row in losers:
        print(f"| {sym} | {fmt(row['last'])} | {row['pct']:+.2f}% | ${row['vol']/1e6:.0f}M |")

    print("\n## 资金费率（USDT 永续，8 小时）\n")
    print("> 正费率 = 多头付给空头；负费率 = 空头付给多头。数值按 24h 成交额靠前的合约排序。\n")
    print("| 合约 | 资金费率 | 年化（未复利） |")
    print("| --- | ---: | ---: |")
    top = sorted(
        ((k, v) for k, v in f.items() if k in liquid),
        key=lambda kv: -liquid[kv[0]]["vol"],
    )[:12]
    for sym, rate in top:
        print(f"| {sym} | {rate*1e4:+.3f} bps | {rate*3*365*100:+.1f}% |")

    print("\n---\n")
    print("本页由 GitHub Actions 每日自动生成与提交，不构成任何投资建议。")
    print(f"\n<!-- generated at {now.isoformat(timespec='seconds')} -->")


if __name__ == "__main__":
    main()

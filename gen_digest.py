"""生成每日市场简报：README.md（最新）+ archive/YYYY-MM-DD.md（归档）+ archive/README.md（索引）。

数据源：Gate.io 公开接口 → 失败时自动退到 CoinGecko。无需任何密钥。
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (market-digest/2.0)"}
WATCH = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LINK", "AVAX", "TON"]
ROOT = Path(__file__).resolve().parent


def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def spot_gate() -> dict[str, dict]:
    out = {}
    for row in get("https://api.gateio.ws/api/v4/spot/tickers"):
        cp = row.get("currency_pair", "")
        if not cp.endswith("_USDT"):
            continue
        try:
            out[cp[:-5]] = {
                "last": float(row["last"]),
                "pct": float(row.get("change_percentage") or 0),
                "vol": float(row.get("quote_volume") or 0),
            }
        except (KeyError, ValueError, TypeError):
            continue
    return out


def spot_coingecko() -> dict[str, dict]:
    out = {}
    rows = get(
        "https://api.coingecko.com/api/v3/coins/markets"
        "?vs_currency=usd&order=market_cap_desc&per_page=250&page=1"
        "&price_change_percentage=24h"
    )
    for row in rows:
        sym = (row.get("symbol") or "").upper()
        try:
            out[sym] = {
                "last": float(row.get("current_price") or 0),
                "pct": float(row.get("price_change_percentage_24h") or 0),
                "vol": float(row.get("total_volume") or 0),
            }
        except (TypeError, ValueError):
            continue
    return out


def funding_gate() -> dict[str, float]:
    out = {}
    try:
        for row in get("https://api.gateio.ws/api/v4/futures/usdt/tickers"):
            name = row.get("contract", "")
            if name.endswith("_USDT"):
                try:
                    out[name[:-5]] = float(row.get("funding_rate") or 0)
                except (ValueError, TypeError):
                    continue
    except Exception:
        return {}
    return out


def fmt(v: float) -> str:
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 1:
        return f"{v:,.2f}"
    return f"{v:.6f}".rstrip("0").rstrip(".")


def build() -> str:
    now = datetime.now(timezone.utc)
    source = "Gate.io"
    try:
        s = spot_gate()
        if len(s) < 50:
            raise RuntimeError("gate too few pairs")
    except Exception:
        s = spot_coingecko()
        source = "CoinGecko（Gate 不可用时的兜底源）"

    f = funding_gate() if source == "Gate.io" else {}
    liquid = {k: v for k, v in s.items() if v["vol"] >= 3_000_000 and v["last"] > 0}
    movers = sorted(liquid.items(), key=lambda kv: kv[1]["pct"], reverse=True)
    gainers = [m for m in movers if m[1]["pct"] > 0][:10]
    losers = sorted(liquid.items(), key=lambda kv: kv[1]["pct"])[:10]

    out = [f"# 市场日报 · {now:%Y-%m-%d}\n"]
    out.append(f"> 数据来源：{source}（成交额 ≥ $3M 才入榜）  ")
    out.append(f"> 生成时间：{now:%Y-%m-%d %H:%M} UTC ｜ 每日自动更新\n")

    out.append("## 主流币\n")
    out.append("| 币种 | 价格 (USDT) | 24h 涨跌 | 24h 成交额 |")
    out.append("| --- | ---: | ---: | ---: |")
    for sym in WATCH:
        row = s.get(sym)
        if not row:
            continue
        out.append(f"| {sym} | {fmt(row['last'])} | {row['pct']:+.2f}% | ${row['vol']/1e6:.0f}M |")

    for title, rows in (("涨幅榜", gainers), ("跌幅榜", losers)):
        out.append(f"\n## {title}（成交额 ≥ $3M）\n")
        out.append("| 币种 | 价格 | 24h | 成交额 |")
        out.append("| --- | ---: | ---: | ---: |")
        for sym, row in rows:
            out.append(f"| {sym} | {fmt(row['last'])} | {row['pct']:+.2f}% | ${row['vol']/1e6:.0f}M |")

    if f:
        out.append("\n## 资金费率（USDT 永续，8 小时）\n")
        out.append("> 正费率 = 多头付给空头；负费率 = 空头付给多头。\n")
        out.append("| 合约 | 资金费率 | 年化（未复利） |")
        out.append("| --- | ---: | ---: |")
        top = sorted(((k, v) for k, v in f.items() if k in liquid), key=lambda kv: -liquid[kv[0]]["vol"])[:12]
        for sym, rate in top:
            out.append(f"| {sym} | {rate*1e4:+.3f} bps | {rate*3*365*100:+.1f}% |")

    out.append("\n---\n")
    out.append("历史：见 [archive/](archive/)。本页由 GitHub Actions 每日自动生成，不构成任何投资建议。")
    out.append(f"\n<!-- generated at {now.isoformat(timespec='seconds')} source={source} -->")
    return "\n".join(out) + "\n"


def write_archive(text: str) -> None:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    arch = ROOT / "archive"
    arch.mkdir(exist_ok=True)
    (arch / f"{day}.md").write_text(text, encoding="utf-8")

    files = sorted((p.stem for p in arch.glob("*.md") if p.name != "README.md"), reverse=True)
    lines = ["# 历史归档\n", f"共 {len(files)} 份日报，最新在前。\n"]
    for d in files[:120]:
        lines.append(f"- [{d}]({d}.md)")
    (arch / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    text = build()
    (ROOT / "README.md").write_text(text, encoding="utf-8")
    write_archive(text)
    print(text)


if __name__ == "__main__":
    main()

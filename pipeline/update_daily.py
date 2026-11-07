"""从公开行情、交易所份额和基金净值增量更新看板的日度序列。"""
import io
import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from openpyxl import load_workbook

from build_data import UA, _sse_one, mkt, retry

DATA_FILE = Path(__file__).resolve().parents[1] / "site" / "data.js"
PREFIX = "window.__DATA = "
EAST_ASIA = timezone(timedelta(hours=8))


def request(url, params, referer, binary=False):
    def fetch():
        response = requests.get(url, params=params, headers={**UA, "Referer": referer}, timeout=30)
        response.raise_for_status()
        return response.content if binary else response.json()

    # 行情源偶发主动断连，逐步拉长重试间隔，避免短时间连续请求。
    return retry(fetch, n=3, wait=5)


def number(value):
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"无效数值 {value}")
    return value


def kline(secid, start, end):
    payload = request("https://push2his.eastmoney.com/api/qt/stock/kline/get", {
        "secid": secid, "klt": 101, "fqt": 0, "beg": start.replace("-", ""),
        "end": end.replace("-", ""), "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
    }, "https://quote.eastmoney.com/")
    data = payload["data"]
    if data["code"] != secid.split(".")[1]:
        raise ValueError(f"{secid} 行情代码不匹配")
    result = {}
    for row in data["klines"]:
        day, _, close, _, _, _, amount = row.split(",")
        result[day] = (number(close), number(amount))
    return result


def nav_values(code, start, end):
    result = {}
    page = 1
    while True:
        data = request("https://api.fund.eastmoney.com/f10/lsjz", {
            "fundCode": code, "startDate": start, "endDate": end,
            "pageIndex": page, "pageSize": 20,
        }, "https://fundf10.eastmoney.com/")
        if data["ErrCode"] != 0:
            raise ValueError(f"{code} 净值接口返回 {data['ErrCode']}")
        rows = data["Data"]["LSJZList"]
        for row in rows:
            if row.get("DWJZ"):
                result[row["FSRQ"]] = number(row["DWJZ"])
        if not rows or page * 20 >= data["TotalCount"]:
            return result
        page += 1


def szse_shares(basket, start, end):
    content = request("https://www.szse.cn/api/report/ShowReport", {
        "SHOWTYPE": "xlsx", "CATALOGID": "scsj_fund_jjgm", "TABKEY": "tab1",
        "txtStart": start, "txtEnd": end, "jjlb": "ETF",
    }, "https://www.szse.cn/market/fund/volume/etf/index.html", binary=True)
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        # 深交所文件的 dimension 声明为 A1，实际包含多行、四列。
        workbook.active.reset_dimensions()
        rows = workbook.active.values
        header = list(next(rows))
        fields = [header.index(key) for key in ("日期", "基金代码", "基金规模(份)")]
        result = {}
        for row in rows:
            day, code, shares = (row[index] for index in fields)
            if str(code) in basket and shares is not None:
                result[str(day)[:10], str(code)] = number(str(shares).replace(",", ""))
        return result
    finally:
        workbook.close()


def update(board, end):
    daily = board["daily"]
    start = daily["dates"][-1]
    # 按月分批补齐，即使长期停更也能限制单次报表的规模。
    end = min(end, (datetime.fromisoformat(start) + timedelta(days=31)).date().isoformat())
    if end <= start:
        return 0
    index = kline("1.000001", start, end)
    if start not in index:
        raise ValueError("指数交易日历缺少上次发布日，无法确定相邻交易日")
    days = sorted(index)
    if len(days) == 1:
        return 0
    basket = [entry["code"] for entry in board["meta"]["basket"]]
    if len(basket) != len(set(basket)) or not basket:
        raise ValueError("无效的 ETF 篮子")

    def fund(code):
        market_id = "1" if mkt(code) == "sh" else "0"
        return code, (kline(f"{market_id}.{code}", start, end), nav_values(code, start, end))

    with ThreadPoolExecutor(max_workers=3) as pool:
        funds = dict(pool.map(fund, basket))
        shares = szse_shares(basket, start, end)
        for day, holdings in zip(days, pool.map(_sse_one, days)):
            for code in basket:
                if code in holdings and mkt(code) == "sh":
                    shares[day, code] = number(holdings[code][0])

    added = 0
    for prev, day in zip(days, days[1:]):
        missing = [code for code, (prices, navs) in funds.items()
                   if day not in prices or not navs.get(day) or (day, code) not in shares
                   or (prev, code) not in shares]
        if missing:
            print(f"{day} 等待完整披露，缺 {', '.join(missing)}")
            if (datetime.fromisoformat(end) - datetime.fromisoformat(day)).days >= 5:
                raise ValueError(f"{day} 长期缺失，须检查上游数据")
            break
        amount = round(sum(prices[day][1] for prices, _ in funds.values()) / 1e8, 2)
        flow = round(sum((shares[day, c] - shares[prev, c]) * navs[day]
                         for c, (_, navs) in funds.items()) / 1e8, 2)
        row = {"date": day, "amount": amount, "netflow": flow}
        for key, value in (("dates", day), ("amount", amount), ("netflow", flow),
                           ("idx", index[day][0]), ("nfCov", len(basket)), ("amtCov", len(basket))):
            daily[key].append(value)
        if flow > 100:
            board["support"].append(row.copy())
        board["recent"] = (board["recent"] + [row])[-4:]
        board["meta"]["latestDay"] = day
        added += 1
    return added


def main():
    text = DATA_FILE.read_text(encoding="utf-8").strip()
    if not text.startswith(PREFIX):
        raise ValueError("无法识别 data.js")
    board = json.loads(text[len(PREFIX):].removesuffix(";"))
    # 深交所 T 日份额可能盘后修订，最多只使用北京时间昨天的数据。
    end = (datetime.now(EAST_ASIA).date() - timedelta(days=1)).isoformat()
    count = 0
    while added := update(board, end):
        count += added
        if board["meta"]["latestDay"] >= end:
            break
    if count:
        target = DATA_FILE.with_suffix(".tmp")
        target.write_text(PREFIX + json.dumps(board, ensure_ascii=False, allow_nan=False) + ";\n",
                          encoding="utf-8")
        target.replace(DATA_FILE)
    print(f"新增 {count} 个交易日，日度数据截至 {board['meta']['latestDay']}")


if __name__ == "__main__":
    main()

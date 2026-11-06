"""逐只对账 ETF 实际成交额、收盘价乘成交份额，以及腾讯 15:00 的累计成交额。"""
import argparse
import csv
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from pathlib import Path

from update_daily import DATA_FILE, PREFIX, mkt, request

YI = Decimal(10**8)
FIELDS = ["日期", "代码", "简称", "成交量(手)", "收盘价(元)", "实际成交额(亿元)",
          "收盘价乘成交份额(亿元)", "差额(亿元)", "腾讯15点累计(亿元)"]


def row_for(code, name, day):
    market = mkt(code)
    secid = ("1." if market == "sh" else "0.") + code
    key = day.replace("-", "")
    payload = request("https://push2his.eastmoney.com/api/qt/stock/kline/get", {
        "secid": secid, "beg": key, "end": key, "klt": 101, "fqt": 0,
        "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57",
    }, "https://quote.eastmoney.com/")["data"]
    if payload["code"] != code or len(payload["klines"]) != 1:
        raise ValueError(f"{code} 缺少 {day} 日线")
    dt, _, close, _, _, lots, amount = payload["klines"][0].split(",")
    if dt != day:
        raise ValueError(f"{code} 日期错误 {dt}")
    actual = Decimal(amount) / YI
    estimate = Decimal(close) * int(lots) * 100 / YI
    symbol = market + code
    quotes = request("https://web.ifzq.gtimg.cn/appstock/app/day/query",
                     {"code": symbol}, "https://gu.qq.com/")["data"][symbol]["data"]
    reference = next((Decimal(line.split()[3]) / YI for item in quotes if item["date"] == key
                      for line in item["data"] if line.startswith("1500 ")), None)
    return [day, code, name, int(lots), close, actual, estimate, estimate - actual, reference]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("day", type=date.fromisoformat)
    parser.add_argument("output", type=Path, help="UTF-8 CSV 路径；腾讯五日窗口之外留空")
    args = parser.parse_args()
    data = json.loads(DATA_FILE.read_text(encoding="utf-8").removeprefix(PREFIX).strip().removesuffix(";"))
    def collect(fund):
        return row_for(fund["code"], fund["name"], args.day.isoformat())
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = sorted(pool.map(collect, data["meta"]["basket"]), key=lambda r: -abs(r[7]))
    sums = [sum(r[i] for r in rows) for i in (5, 6, 7)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(FIELDS)
        for row in rows:
            writer.writerow([format(v, "f") if isinstance(v, Decimal) else v for v in row])
    print(f"{len(rows)} 只，实际 {sums[0]:.4f} 亿，收盘价换算 {sums[1]:.4f} 亿，差额 {sums[2]:+.4f} 亿")


if __name__ == "__main__":
    main()

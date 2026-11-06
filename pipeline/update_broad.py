"""按沪深交易所 ETF 目录和份额公告补齐 12 类宽基的日度净流入。"""
import argparse
import csv
import io
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import load_workbook

from build_data import _sse_one, mkt
from update_daily import EAST_ASIA, kline, nav_values, request, szse_shares

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site/broad.js"
MEMBERS = ROOT / "reference/data/broad_members.csv"
RULES = ROOT / "reference/data/broad_benchmarks.json"
PREFIX = "window.__BROAD = "


def sz_report(catalog, fields):
    content = request("https://fund.szse.cn/api/report/ShowReport",
                      {"SHOWTYPE": "xlsx", "CATALOGID": catalog, "TABKEY": "tab1"},
                      "https://fund.szse.cn/marketdata/etf/index.html", binary=True)
    book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        book.active.reset_dimensions()
        rows = book.active.values
        header = list(next(rows))
        indexes = [header.index(field) for field in fields]
        return [tuple(str(row[i]).strip() for i in indexes) for row in rows]
    finally:
        book.close()


def catalogue(rules):
    mapping = {market: {} for market in ("sh", "sz")}
    for cat, markets in rules.items():
        for market, values in markets.items():
            for index in values:
                if index in mapping[market]:
                    raise ValueError(f"重复指数规则 {market} {index}")
                mapping[market][index] = cat
    payload = request("https://query.sse.com.cn/commonQuery.do", {
        "sqlId": "COMMON_JJZWZ_JJLB_L", "CATEGORY": "F100", "type": "inParams",
        "isPagination": "true", "pageHelp.pageNo": 1, "pageHelp.pageSize": 2000,
    }, "https://etf.sse.com.cn/")
    sh = payload["pageHelp"]["data"]
    if not sh or len(sh) != int(payload["pageHelp"]["total"]):
        raise ValueError("沪市 ETF 目录不完整")
    sz = sz_report("fund_etf", ["证券代码", "证券简称", "拟合指数"])
    sz_dates = {code: day for code, kind, day in sz_report("1000_lf", ["基金代码", "基金类别", "上市日期"])
                if kind == "ETF"}
    if len(sz) < 500 or len({r[0] for r in sz}) != len(sz):
        raise ValueError("深市 ETF 目录不完整")
    rows = [(r["FUND_CODE"], r["FUND_EXPANSION_ABBR"], r["INDEX_NAME"].replace(" ", ""),
             r["LISTING_DATE"]) for r in sh]
    rows.extend((code, name, index.split()[0] if index else "", sz_dates.get(code, ""))
                for code, name, index in sz)
    members = {}
    for code, name, index, listed in rows:
        category = mapping[mkt(code)].get(index)
        if category:
            if code in members:
                raise ValueError(f"目录代码重复 {code}")
            members[code] = dict(code=code, name=name, benchmark=index, category=category,
                                 listed=date.fromisoformat(listed[:10]).isoformat())
    if set(rules) != {m["category"] for m in members.values()}:
        raise ValueError("12 类未全部覆盖")
    return members, len(rows)


def check_members(members, previous, published):
    # 目录偶发缺行不能视为退市。实际退市/转指数须核实生效日后调整存档。
    for code, old in previous.items():
        if code not in members or members[code]["category"] != old["category"]:
            raise ValueError(f"{code} 从目录消失或分类变更，请复核生效日")
    unexpected = [c for c, m in members.items() if c not in previous and m["listed"] <= published]
    if previous and unexpected:
        raise ValueError(f"新匹配到已上市基金，须复核历史覆盖 {unexpected}")


def extend(board, members, days):
    sz_codes = {c for c in members if mkt(c) == "sz"}
    shares = szse_shares(sz_codes, days[0], days[-1])
    with ThreadPoolExecutor(max_workers=3) as pool:
        for day, rows in zip(days, pool.map(_sse_one, days)):
            shares.update({(day, c): v[0] for c, v in rows.items() if c in members and mkt(c) == "sh"})

    changes = {}
    active = {}
    changed = set()
    for previous, day in zip(days, days[1:]):
        changes[day] = {}
        active[day] = [c for c, m in members.items() if m["listed"] <= day]
        for code in active[day]:
            # 首日没有相邻上市交易日，不把初始份额计作当日申购。
            if members[code]["listed"] > previous:
                continue
            if (previous, code) not in shares or (day, code) not in shares:
                raise ValueError(f"缺少相邻两日的交易所份额 {code} {previous} / {day}")
            delta = shares[day, code] - shares[previous, code]
            if delta:
                changes[day][code] = delta
                changed.add(code)

    def fund_nav(code):
        return code, nav_values(code, days[1], days[-1])

    with ThreadPoolExecutor(max_workers=4) as pool:
        nav = dict(pool.map(fund_nav, sorted(changed)))
    for day in days[1:]:
        sums = dict.fromkeys(board["categories"], 0.0)
        for code, delta in changes[day].items():
            if nav[code].get(day, 0) <= 0:
                raise ValueError(f"缺少当日单位净值 {code} {day}")
            sums[members[code]["category"]] += delta * nav[code][day] / 1e8
        board["dates"].append(day)
        for cat, value in sums.items():
            board["byCategory"][cat].append(round(value, 4))
        board["cumulative"].append(round(board["cumulative"][-1] + sum(sums.values()), 4))
        counts = Counter(members[c]["category"] for c in active[day])
        board["meta"].update(dateLast=day, broadCount=len(active[day]), categoryCounts=dict(counts))
        print(f"{day} 宽基 {len(active[day])} 只，其中 {len(changes[day])} 只份额变动，"
              f"合计 {sum(sums.values()):+.2f} 亿", flush=True)


def validate(board):
    days = board["dates"]
    series = board["byCategory"]
    if (len(days) != len(set(days)) or days != sorted(days) or len(series) != 12
            or set(series) != set(board["categories"]) or any(len(v) != len(days) for v in series.values())
            or len(board["cumulative"]) != len(days)):
        raise ValueError("宽基日期或分类序列不一致")
    board["heat"] = {"dates": days[-22:], "byCategory": {c: v[-22:] for c, v in series.items()}}
    board["meta"].update(cumLast=board["cumulative"][-1], cumMin=min(board["cumulative"]))


def atomic_write(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(value.encode("utf-8"))
    os.replace(temp, path)


def read_members():
    if not MEMBERS.exists():
        return {}
    with MEMBERS.open(encoding="utf-8", newline="") as f:
        return {row["code"]: row for row in csv.DictReader(f)}


def verify_latest(board, rules):
    # 用实时披露重算末日，不写盘；避免“已经是最新日期”掩盖接口故障。
    previous, day = board["dates"][-2:]
    members, _ = catalogue(rules)
    check_members(members, read_members(), day)
    probe = {"categories": board["categories"], "dates": [previous],
             "byCategory": {cat: [] for cat in rules}, "cumulative": [board["cumulative"][-2]],
             "meta": {}}
    extend(probe, members, [previous, day])
    for cat in rules:
        if abs(probe["byCategory"][cat][0] - board["byCategory"][cat][-1]) > 0.0001:
            raise ValueError(f"{day} {cat} 已发布值与重新计算的结果不同，需复核修订")
    if (probe["meta"]["categoryCounts"] != board["meta"]["categoryCounts"]
            or abs(probe["cumulative"][-1] - board["cumulative"][-1]) > 0.0001):
        raise ValueError("末日覆盖数或累计值与重新计算的结果不同")
    print(f"{day} 全部 12 类及累计额复算通过")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through", type=date.fromisoformat, help="最多补到指定日期，且不晚于北京时间昨天")
    parser.add_argument("--verify-latest", action="store_true", help="从公开源复算已发布末日，仅校验")
    args = parser.parse_args()
    board = json.loads(DATA.read_text(encoding="utf-8").removeprefix(PREFIX).strip().removesuffix(";"))
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    if set(rules) != set(board["categories"]):
        raise ValueError("指数映射和站点分类不一致")
    if args.verify_latest:
        verify_latest(board, rules)
        return
    yesterday = datetime.now(EAST_ASIA).date() - timedelta(days=1)
    end = min(yesterday, args.through or yesterday).isoformat()
    start = board["dates"][-1]
    if start >= end:
        print(f"宽基已更新至 {start}")
        return
    members = None
    while start < end:
        stop = min(end, (date.fromisoformat(start) + timedelta(days=31)).isoformat())
        days = sorted(kline("1.000001", start, stop))
        if not days or days[0] != start:
            raise ValueError(f"交易日历没有包含上次发布日 {start}")
        if len(days) == 1:
            break
        if members is None:
            members, universe = catalogue(rules)
            check_members(members, read_members(), start)
            board["meta"].update(universeTotal=universe, catalogueDate=datetime.now(EAST_ASIA).date().isoformat())
            board["meta"].setdefault("publicStart", days[1])
        extend(board, members, days)
        start = days[-1]
        if stop == end:
            break
    if members is not None:
        validate(board)
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=["code", "name", "benchmark", "category", "listed"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(members[c] for c in sorted(members))
        # 先落目录，最后推进数据日期，中途失败可从旧日期安全重试。
        atomic_write(MEMBERS, stream.getvalue())
        atomic_write(DATA, PREFIX + json.dumps(board, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + ";\n")
    print(f"宽基发布末日 {start}")


if __name__ == "__main__":
    main()

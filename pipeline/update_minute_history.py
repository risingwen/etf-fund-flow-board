"""回补、增量归档和校验现行 ETF 篮子的 240 点累计成交额（亿元）。"""
import argparse
import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from itertools import accumulate
from os import environ

from update_daily import DATA_FILE, EAST_ASIA, PREFIX, kline, mkt, number, request, retry

ARCHIVE = DATA_FILE.with_name("minute-history.json")
YI = 100_000_000


def tencent_curves(code, times, end):
    symbol = mkt(code) + code
    payload = request("https://web.ifzq.gtimg.cn/appstock/app/day/query",
                      {"code": symbol}, "https://gu.qq.com/")
    if payload["code"] != 0:
        raise ValueError(f"{symbol} 腾讯接口异常")
    curves = {}
    for record in payload["data"][symbol]["data"]:
        day = datetime.strptime(record["date"], "%Y%m%d").date().isoformat()
        if day > end:
            continue
        points = {}
        for line in record["data"]:
            clock, _, _, amount = line.split()[:4]
            slot = clock[:2] + ":" + clock[2:]
            if slot in points:
                raise ValueError(f"{code} {day} {slot} 重复")
            points[slot] = number(amount)
        if all(t in points for t in times):
            curves[day] = [points[t] for t in times]
    return curves


def tdx_curves(code, times, end):
    from eltdx import TdxClient

    raw = {}
    symbol = mkt(code) + code
    host = environ.get("TDX_HOST", "119.29.19.242:7709")
    with TdxClient(host=host, timeout=12) as client:
        for offset in range(0, 64000, 800):
            bars = client.bars.get(symbol, period="1m", start=offset, count=800).bars
            for bar in bars:
                day = bar.time.date().isoformat()
                if day > end:
                    continue
                clock = bar.time.strftime("%H:%M")
                points = raw.setdefault(day, {})
                if clock in points or clock not in times:
                    raise ValueError(f"{code} {day} 分钟时间异常 {clock}")
                points[clock] = number(bar.amount)
            if len(bars) < 800:
                break
        else:
            raise ValueError("分钟历史分页超过协议偏移范围")
    return {day: list(accumulate(points[t] for t in times)) for day, points in raw.items()
            if len(points) == len(times)}


def check_curve(values, times, context):
    if (len(values) != len(times) or any(not math.isfinite(v) or v < 0 for v in values)
            or any(a > b for a, b in zip(values, values[1:]))):
        raise ValueError(f"{context} 累计成交额缺失、为负或倒退")


def read_archive(codes, times):
    if not ARCHIVE.exists():
        return {}
    archive = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    if archive["version"] != 1 or codes != archive["codes"] or times != archive["times"]:
        raise ValueError("归档时间轴或成分与当前看板不符")
    days = archive["days"]
    if sorted(days) != archive["calendar"]:
        raise ValueError("归档交易日历和曲线不一致")
    for day, curve in days.items():
        check_curve(curve, times, day)
    return days


def save(codes, times, curves):
    days = sorted(curves)
    header = json.dumps(dict(version=1, codes=codes, times=times, calendar=days), separators=(",", ":"))
    # 每日一行，让每日提交的差异可读。
    rows = [f'"{day}":' + json.dumps(curves[day], separators=(",", ":"), allow_nan=False) for day in days]
    temp = ARCHIVE.with_suffix(".tmp")
    temp.write_text(header[:-1] + ',"days":{\n' + ",\n".join(rows) + "\n}}\n", encoding="utf-8", newline="\n")
    temp.replace(ARCHIVE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--backfill", action="store_true", help="向通达信分页请求全部可用分钟 K 线")
    mode.add_argument("--verify-latest", action="store_true", help="仅从腾讯和日线复核归档末日")
    args = parser.parse_args()
    board = json.loads(DATA_FILE.read_text(encoding="utf-8").removeprefix(PREFIX).strip().removesuffix(";"))
    codes = sorted(x["code"] for x in board["meta"]["basket"])
    times = board["init"]["times"]
    if len(set(codes)) != 20 or len(codes) != 20 or len(times) != 240 or times != sorted(set(times)):
        raise ValueError("看板未提供 20 只独立成分和 240 个分钟")
    existing = read_archive(codes, times)
    if not existing and not args.backfill:
        raise ValueError("请先用 --backfill 创建历史归档")
    now = datetime.now(EAST_ASIA)
    end = (now.date() if now.strftime("%H:%M") >= "15:15" else now.date() - timedelta(days=1)).isoformat()
    if args.verify_latest:
        end = max(existing)
    if args.backfill:
        def fetch(code):
            return retry(lambda: tdx_curves(code, times, end))
    else:
        def fetch(code):
            return tencent_curves(code, times, end)

    with ThreadPoolExecutor(max_workers=3) as pool:
        if not args.backfill:
            latest = max(existing)
            calendar = sorted(kline("1.000001", latest, end))
            if not calendar or calendar[0] != latest:
                raise ValueError("上证交易日历缺少归档末日")
            target = [latest] if args.verify_latest else calendar[1:]
            if not target:
                print(f"分钟归档已是最新，截至 {latest}")
                return
        funds = dict(zip(codes, pool.map(fetch, codes)))
        if args.backfill:
            if not all(funds.values()):
                raise ValueError("部分基金没有完整分钟记录")
            start = max(min(days) for days in funds.values())
            calendar = sorted(kline("1.000001", min([start, *existing]), end))
            target = [d for d in calendar if d not in existing]
            if not target:
                print("现有归档已涵盖可回补交易日")
                return
        def daily(code):
            prefix = "1." if mkt(code) == "sh" else "0."
            return kline(prefix + code, target[0], target[-1])
        totals = dict(zip(codes, pool.map(daily, codes)))

    additions = {}
    max_error = 0
    for day in target:
        for code in codes:
            if day not in funds[code] or day not in totals[code]:
                raise ValueError(f"{code} 缺少 {day} 的完整分钟或日线。超出腾讯窗口可用 --backfill 补齐")
            values = funds[code][day]
            check_curve(values, times, f"{code} {day}")
            daily_amount = totals[code][day][1]
            error = abs(daily_amount - values[-1])
            if daily_amount <= 0 or error > max(1000, daily_amount * 0.000002):
                raise ValueError(f"{day} {code} 分钟与日线相差 {error:,.2f} 元")
            max_error = max(max_error, error)
        additions[day] = [round(sum(slot) / YI, 6) for slot in zip(*(funds[c][day] for c in codes))]
    print(f"逐只核对 {len(target)} 天 × {len(codes)} 只 × {len(times)} 分钟，收盘与日线最大差 {max_error:,.2f} 元")
    if args.verify_latest:
        day = target[0]
        deltas = [abs(a - b) for a, b in zip(additions[day], existing[day])]
        print(f"{day} 腾讯与归档收盘差 {deltas[-1]:.6f} 亿，盘中最大差 {max(deltas):.6f} 亿")
        # 两个供应商的分钟切分可能不同，但收盘总额应收敛。
        if deltas[-1] > max(0.0002, existing[day][-1] * 0.000002):
            raise ValueError("腾讯收盘金额与归档不符")
        return
    merged = {**existing, **additions}
    if args.backfill and any(day not in merged for day in calendar):
        raise ValueError("归档期间有缺失的交易日")
    save(codes, times, merged)
    print(f"新增 {len(additions)} 天，累计 {len(merged)} 天，{min(merged)} 至 {max(merged)}")


if __name__ == "__main__":
    main()

"""归档 13 类主题 ETF 真实 5 分钟累计成交额，并以日线成交额逐只校验。"""
import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from itertools import accumulate

from market_common import ROOT, SITE, YI, read_json, save_json, stamp
from update_broad import sz_report
from update_daily import EAST_ASIA, kline, mkt, request, retry
from update_minute_history import check_curve, tencent_curves

PATH = SITE / 'themes.json'
TIMES = [f'{h:02}:{m:02}' for h in range(9,16) for m in range(0,60,5)
         if '09:35' <= f'{h:02}:{m:02}' <= '11:30' or '13:05' <= f'{h:02}:{m:02}' <= '15:00']


def _catalogue():
    sh = request('https://query.sse.com.cn/commonQuery.do', {
        'sqlId':'COMMON_JJZWZ_JJLB_L','CATEGORY':'F100','type':'inParams',
        'isPagination':'true','pageHelp.pageNo':1,'pageHelp.pageSize':2000}, 'https://etf.sse.com.cn/')['pageHelp']
    if len(sh['data']) != int(sh['total']) or len(sh['data']) < 500:
        raise ValueError('沪市 ETF 目录不完整')
    sz = sz_report('fund_etf',['证券代码','证券简称','拟合指数'])
    listed = {c:d for c,k,d in sz_report('1000_lf',['基金代码','基金类别','上市日期']) if k == 'ETF'}
    rows = [{'code':r['FUND_CODE'],'name':r['FUND_EXPANSION_ABBR'],'benchmark':''.join(r['INDEX_NAME'].split()),
             'listed':r['LISTING_DATE'][:10]} for r in sh['data']]
    rows.extend({'code':c,'name':n,'benchmark':b.split()[0] if b else '', 'listed':listed[c][:10]} for c,n,b in sz)
    if len(rows) != len({r['code'] for r in rows}) or len(sz) < 500:
        raise ValueError('ETF 目录缺失或重复')
    return rows


def catalogue():
    from catalogue_cache import cached_catalogue
    return cached_catalogue(_catalogue)


def tdx_history(code, first, last):
    from eltdx import TdxClient
    cache = ROOT / 'pipeline/cache/theme-bootstrap' / f'{code}-{first}-{last}.json'
    if cache.exists():
        return read_json(cache)
    points = {}
    with TdxClient(host=os.environ.get('TDX_HOST','119.29.19.242:7709'), timeout=15) as client:
        for offset in range(0,64000,800):
            bars = client.bars.get(mkt(code)+code,period='5m',start=offset,count=800).bars
            for bar in bars:
                day, clock = bar.time.date().isoformat(), bar.time.strftime('%H:%M')
                if first <= day <= last:
                    points.setdefault(day,{})[clock] = bar.amount
            if not bars or len(bars)<800 or bars[0].time.date().isoformat() < first:
                break
        else:
            raise ValueError(f'{code} 历史超过公开分页范围')
        daily = client.bars.get(mkt(code)+code,period='day',start=0,count=800).bars
        totals = {b.time.date().isoformat():b.amount for b in daily}
    curves = {}
    for day, values in points.items():
        if set(values) != set(TIMES):
            continue
        curve = list(accumulate(values[t] for t in TIMES))
        check_curve(curve,TIMES,code+' '+day)
        total = totals.get(day)
        if total is None or abs(curve[-1]-total)>max(5000,total*.00002):
            raise ValueError(f'{code} {day} 5 分钟合计和日线成交额不符')
        curves[day] = curve
    cache.parent.mkdir(parents=True,exist_ok=True)
    save_json(cache,curves)
    return curves


def update(bootstrap=False, days=60):
    old = read_json(PATH, {})
    rules = read_json(ROOT/'reference/data/theme_rules.json')
    all_members = catalogue()
    groups = [{**r,'members':[m for m in all_members if m['benchmark'] in r['benchmarks']]} for r in rules]
    if len(groups)!=13 or any(not g['members'] for g in groups):
        raise ValueError('13 类主题未完整匹配')
    members = {m['code']:m for g in groups for m in g['members']}
    previous = {m['code'] for g in old.get('groups',[]) for m in g['members']}
    if previous-set(members):
        raise ValueError('已发布成分从目录消失，须先核实退市或指数变更')
    old_signature = [(g['name'], sorted(m['code'] for m in g['members'])) for g in old.get('groups',[])]
    signature = [(g['name'], sorted(m['code'] for m in g['members'])) for g in groups]
    changed = old_signature != signature
    now = datetime.now(EAST_ASIA)
    end = (now.date() if now.strftime('%H:%M') >= '15:20' else now.date()-timedelta(days=1)).isoformat()
    if not old or bootstrap:
        board = json.loads((SITE/'data.js').read_text(encoding='utf-8').removeprefix('window.__DATA = ').strip().removesuffix(';'))
        calendar = sorted(set(old.get('calendar',[])) | set([d for d in board['daily']['dates'] if d<=end][-days:]))
    else:
        calendar = old['calendar'][:]
        if (datetime.fromisoformat(end)-datetime.fromisoformat(calendar[-1])).days > 5:
            calendar = sorted(set(calendar) | set(kline('1.000001',calendar[-1],end)))
    # 上证指数不适用基金代码判断；用指数接口核实最近交易日。
    index = request('https://web.ifzq.gtimg.cn/appstock/app/day/query',{'code':'sh000001'},'https://gu.qq.com/')
    recent = [datetime.strptime(r['date'],'%Y%m%d').date().isoformat() for r in index['data']['sh000001']['data']
              if r['data'] and r['data'][-1].split()[0]=='1500']
    calendar = sorted(set(calendar) | {d for d in recent if d<=end and d>=calendar[0]})
    target = calendar if changed else [d for d in calendar if d not in old['calendar']]
    if not target:
        print(f'主题归档已是最新：{calendar[-1]}',flush=True)
        return old
    use_tdx = bootstrap or changed or target[0] < min(recent)
    print(f'主题 {len(members)} 只，回补 {len(target)} 日 {target[0]}—{target[-1]}',flush=True)
    def fetch(code):
        active = [d for d in target if d >= members[code]['listed']]
        if not active:
            return {}
        if use_tdx:
            return retry(lambda:tdx_history(code, active[0],target[-1]),n=3,wait=3)
        curves = tencent_curves(code,TIMES,end)
        totals = kline(('1.' if mkt(code)=='sh' else '0.')+code,target[0],target[-1])
        for day in active:
            if day not in curves or day not in totals or abs(curves[day][-1]-totals[day][1])>max(5000,totals[day][1]*.00002):
                raise ValueError(f'{code} {day} 腾讯分时与日线不一致或未齐')
        return curves
    codes = sorted(members)
    funds = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for code, result in zip(codes,pool.map(fetch,codes)):
            funds[code] = result
            if len(funds)%25==0:
                print(f'主题逐只校验 {len(funds)}/{len(codes)}',flush=True)
    halts = read_json(ROOT/'reference/data/theme_halts.json',[])
    for halt in halts:
        if halt['date'] in target and halt['code'] in funds and halt['kind']=='full-day':
            present = funds[halt['code']].get(halt['date'])
            if present and any(present):
                raise ValueError('已核实停牌日出现成交记录，须重新核对公告')
            funds[halt['code']][halt['date']] = [0.0]*len(TIMES)
    archives = {} if changed else old['history']
    for g in groups:
        archive = archives.setdefault(g['name'],{})
        for day in target:
            active = [m['code'] for m in g['members'] if m['listed']<=day]
            missing = [c for c in active if day not in funds[c]]
            if missing:
                raise ValueError(f'{g["name"]} {day} 缺少 {missing}，不以零替代')
            curve = [round(sum(funds[c][day][i] for c in active)/YI,6) for i in range(len(TIMES))]
            check_curve(curve,TIMES,g['name']+' '+day)
            archive[day] = {'values':curve,'count':len(active)}
    result = {'version':1,'updatedAt':stamp(),'times':TIMES,'calendar':calendar,'groups':groups,'history':archives,
              'source':'沪深交易所 ETF 目录；通达信 5 分钟成交额回补、腾讯分时增量归档',
              'halts':halts,
              'note':'现行主题篮子按上市日期回溯；各类可重叠，不能直接加总。使用真实 5 分钟节点，不线性补造分钟。公告核实的全天停牌日成交额为零。'}
    save_json(PATH,result)
    print(f'13 类主题：{calendar[0]}—{calendar[-1]}，{len(calendar)} 日，{len(members)} 只；逐只日线校验通过',flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bootstrap',action='store_true',help='从公开通达信 5 分钟 K 线回补')
    parser.add_argument('--days',type=int,default=60,help='首次归档的交易日数，默认 60')
    args = parser.parse_args()
    update(args.bootstrap,args.days)

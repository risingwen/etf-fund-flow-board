"""按已核实的宽基指数目录聚合 ETF 融资融券，历史回补至 2026 年初。"""
from collections import defaultdict

from market_common import ROOT, SITE, YI, merge, numeric, overlap, read_json, report, save_json, stamp
from update_broad import read_members

PATH = SITE / 'etf-margin.json'
CATEGORIES = ['科创50', '创业板指', '中证A500', '沪深300']


def update():
    old = read_json(PATH, {})
    members = {c:m for c,m in read_members().items() if m['category'] in CATEGORIES}
    if set(m['category'] for m in members.values()) != set(CATEGORIES):
        raise ValueError('ETF 两融分类缺失')
    codes = sorted(members)
    start = overlap(old.get('daily', []), '2026-01-01')
    summaries = report('RPTA_WEB_RZRQ_LSSH', 'DIM_DATE,SCDM',
                       f'(DIM_DATE>=\'{start}\')(SCDM in ("007","001"))', 'DIM_DATE,SCDM')
    markets = defaultdict(set)
    for r in summaries:
        markets[r['DIM_DATE'][:10]].add(r['SCDM'])
    complete = sorted(d for d, m in markets.items() if m == {'007','001'})
    if not complete:
        raise ValueError('两市尚无共同的两融披露日')
    rows = []
    columns = 'DATE,SCODE,RZYE,RQYE,RZMRE,RZCHE,RZJME'
    for offset in range(0,len(codes),40):
        subset = ','.join('"'+c+'"' for c in codes[offset:offset+40])
        rows.extend(report('RPTA_WEB_RZRQ_GGMX', columns,
                    f'(DATE>=\'{start}\')(DATE<=\'{complete[-1]}\')(SCODE in ({subset}))', 'DATE,SCODE'))
    grouped = defaultdict(dict)
    fields = {'balance':'RZYE','shortBalance':'RQYE','buy':'RZMRE','repay':'RZCHE','net':'RZJME'}
    for r in rows:
        day, code = r['DATE'][:10], r['SCODE']
        if code in grouped[day] or code not in members:
            raise ValueError('两融明细重复或出现未请求代码')
        if any(r.get(f) is None for f in fields.values()):
            raise ValueError(f'{day} {code} 两融字段缺失')
        if abs(r['RZMRE'] - r['RZCHE'] - r['RZJME']) > 1:
            raise ValueError(f'{day} {code} 融资净买入校验失败')
        grouped[day][code] = r
    daily = []
    for day in complete:
        if day not in grouped:
            raise ValueError(f'{day} 缺少 ETF 明细')
        cats = {}
        for cat in CATEGORIES:
            funds = [r for c,r in grouped[day].items() if members[c]['category'] == cat]
            if not funds:
                raise ValueError(f'{day} 缺少 {cat}')
            cats[cat] = {k:numeric(sum(r[f] for r in funds),YI) for k,f in fields.items()}
            cats[cat]['count'] = len(funds)
        daily.append({'date':day,'categories':cats})
    daily = merge(old.get('daily',[]), daily)
    import json
    broad = json.loads((SITE/'broad.js').read_text(encoding='utf-8').removeprefix('window.__BROAD = ').strip().removesuffix(';'))
    flow = [{'date':d, **{c:broad['byCategory'][c][i] for c in CATEGORIES}} for i,d in enumerate(broad['dates'])]
    result = {'version':1,'updatedAt':stamp(),'categories':CATEGORIES,'daily':daily,'flow':flow,
              'members':list(members.values()), 'reportedCodes':sorted(grouped[complete[-1]]),
              'source':'东方财富逐券两融明细；沪深交易所 ETF 目录分类',
              'note':'两融仅加总有公开记录的标的 ETF；日度净申赎为该类全部 ETF，二者成分范围不同。'}
    save_json(PATH,result)
    print(f'ETF 两融：{daily[0]["date"]}—{daily[-1]["date"]}，{len(daily)} 日；末日 {len(result["reportedCodes"])} 只有记录',flush=True)
    return result


if __name__ == '__main__':
    update()

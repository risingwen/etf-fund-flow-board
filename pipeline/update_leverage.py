"""更新沪深两融长期序列、账户担保指标与行业分布；所有金额转为亿元。"""
from collections import defaultdict

from market_common import SITE, YI, merge, numeric, overlap, read_json, report, save_json, stamp

PATH = SITE / 'leverage.json'


def update():
    old = read_json(PATH, {})
    start = overlap(old.get('daily', []), '2010-03-31')
    raw = report('RPTA_WEB_RZRQ_LSSH', where=f'(DIM_DATE>=\'{start}\')(SCDM in ("007","001"))', sort='DIM_DATE,SCDM')
    grouped = defaultdict(dict)
    latest = {}
    for r in raw:
        day, market = r['DIM_DATE'][:10], r['SCDM']
        if market in grouped[day]:
            raise ValueError(f'两融汇总重复 {day} {market}')
        grouped[day][market] = r
        latest[market] = max(day, latest.get(market, ''))
    if set(latest) != {'007','001'}:
        raise ValueError('最近窗口未返回沪深两市汇总，保留原数据')
    new = []
    fields = {'balance':'RZYE', 'shortBalance':'RQYE', 'buy':'RZMRE', 'repay':'RZCHE', 'net':'RZJME'}
    for day, markets in sorted(grouped.items()):
        if set(markets) != {'007', '001'}:
            continue
        row = {'date':day}
        for key, field in fields.items():
            values = [r.get(field) for r in markets.values()]
            row[key] = numeric(sum(values), YI) if None not in values else None
        row['shBalance'] = numeric(markets['007']['RZYE'], YI)
        row['szBalance'] = numeric(markets['001']['RZYE'], YI)
        row['index'] = numeric(markets['007'].get('NEW'))
        cap = [r.get('LTSZ') for r in markets.values()]
        row['balanceFloatRatio'] = numeric(row['balance'] * YI / sum(cap) * 100) if all(cap) else None
        if row['net'] is not None and row['repay'] is not None and abs(row['buy']-row['repay']-row['net']) > .00001:
            raise ValueError(f'{day} 融资买入减偿还与净买入不一致')
        new.append(row)
    daily = merge(old.get('daily', []), new)
    if not daily:
        raise ValueError('沪深两市没有完整汇总')
    start = overlap(old.get('accounts', []), '2010-01-01')
    raw = report('RPTA_WEB_MARGIN_DAILYTRADE', where=f'(STATISTICS_DATE>=\'{start}\')', sort='STATISTICS_DATE')
    fields = {'guarantee':'TOTAL_GUARANTEE','guaranteeRatio':'AVG_GUARANTEE_RATIO',
              'activity':'TRADE_AMT_RATIO','participants':'INVESTOR_NUM','debtors':'MARGINLIAB_INVESTOR_NUM',
              'cashCollateral':'FUND_MARKET_CAP','balance':'FIN_BALANCE'}
    accounts = merge(old.get('accounts', []), [{'date':r['STATISTICS_DATE'][:10],
                    **{k:numeric(r.get(v)) for k,v in fields.items()}} for r in raw])
    # 此接口只提供最新行业快照，不能把它冒充为上一完整日的数据。
    raw = report('RPTA_WEB_BKJYMXN', where='(BOARD_TYPE_CODE="005")', sort='TRADE_DATE,BOARD_CODE')
    industries = []
    for r in raw:
        industries.append({'date':r['TRADE_DATE'][:10], 'name':r['BOARD_NAME'], 'code':r['BOARD_CODE'],
                           'balance':numeric(r['FIN_BALANCE'],YI), 'net':numeric(r['FIN_NETBUY_AMT'],YI)})
    if not industries:
        raise ValueError('行业两融快照为空')
    result = {'version':1,'updatedAt':stamp(),'scope':'沪深交易所两融汇总（含基金，不含北交所）',
              'source':'东方财富公开两融数据，交易所汇总口径；账户统计口径单列',
              'marketLatest':latest,'daily':daily,'accounts':accounts,'industries':industries,
              'industryComplete':all(r['date']<=daily[-1]['date'] for r in industries)}
    save_json(PATH,result)
    print(f'杠杆：{daily[0]["date"]}—{daily[-1]["date"]}，{len(daily)} 日；账户 {len(accounts)} 日；行业 {len(industries)}', flush=True)
    return result


if __name__ == '__main__':
    update()

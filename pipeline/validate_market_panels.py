"""检查扩展资金看板的日期覆盖、单位恒等式和主题成交曲线完整性。"""
import math

from market_common import SITE, read_json


def dates(rows):
    values = [r['date'] for r in rows]
    assert values and values == sorted(set(values)), '日期为空、重复或乱序'


def validate():
    margin = read_json(SITE/'etf-margin.json')
    leverage = read_json(SITE/'leverage.json')
    themes = read_json(SITE/'themes.json')
    status = read_json(SITE/'market-status.json')
    assert all(d['version']==1 for d in (margin,leverage,themes,status))
    assert len(margin['categories'])==4 and len(themes['groups'])==13
    dates(margin['daily']); dates(leverage['daily']); dates(leverage['accounts'])
    for day in margin['daily']:
        for cat in margin['categories']:
            r = day['categories'][cat]
            assert r['count']>0 and r['balance']>=0 and r['shortBalance']>=0
            assert abs(r['buy']-r['repay']-r['net']) < .00001
    for r in leverage['daily']:
        assert abs(r['shBalance']+r['szBalance']-r['balance']) < .00001
        if r['net'] is not None and r['repay'] is not None:
            assert abs(r['buy']-r['repay']-r['net']) < .00001
    calendar = themes['calendar']
    assert calendar == sorted(set(calendar)) and len(themes['times'])==48
    for group in themes['groups']:
        members = group['members']
        assert len(members)==len({m['code'] for m in members})
        assert group['representative'] in {m['code'] for m in members}
        history = themes['history'][group['name']]
        assert sorted(history)==calendar
        for day in calendar:
            r = history[day]
            assert r['count']==sum(m['listed']<=day for m in members)
            v = r['values']
            assert len(v)==48 and all(math.isfinite(x) and x>=0 for x in v)
            assert all(a<=b for a,b in zip(v,v[1:]))
    assert set(status['modules'])=={'themes','margin','leverage'}
    print(f'数据校验通过：ETF 两融 {len(margin["daily"])} 日，杠杆 {len(leverage["daily"])} 日，主题 {len(calendar)} 日 × 13 类 × 48 点')


if __name__ == '__main__':
    validate()

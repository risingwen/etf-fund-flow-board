"""逐只 ETF 日度归档：交易所份额、单位净值、真实成交额和可复算的净申赎。"""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta

from market_common import ROOT,SITE,read_json,save_json,stamp
from update_daily import EAST_ASIA,nav_values,szse_shares,mkt
from build_data import _sse_one
from public_quotes import tdx_daily
from update_broad import read_members
from update_minute_history import tencent_curves
from corporate_actions import ACTIONS,share_factor,close_factor

PATH=SITE/'funds.json'


def universe():
    result={c:{**m,'groups':[m['category']],'kind':'宽基'} for c,m in read_members().items()}
    for g in read_json(SITE/'themes.json')['groups']:
        for m in g['members']:
            if m['code'] not in result:
                result[m['code']]={**m,'groups':[],'kind':'主题'}
            result[m['code']]['groups'].append(g['name'])
    return result


def update():
    old=read_json(PATH,{'funds':{},'dates':[]})
    members=universe()
    end=(datetime.now(EAST_ASIA).date()-timedelta(days=1)).isoformat()
    calendar=sorted(tdx_daily('1.000001','2025-01-01',end))
    if not calendar or calendar[-1] < end and (datetime.fromisoformat(end)-datetime.fromisoformat(calendar[-1])).days>7:
        raise ValueError('交易日历尚未更新')
    new_codes=set(members)-set(old['funds'])
    target=calendar[-23:] if not old['dates'] or new_codes else calendar[max(0,calendar.index(old['dates'][-1])-2):]
    # 每次重算最近三日，覆盖披露修订；首次至少有 20 日排名及其前一日份额。
    print(f'逐券档案：{len(members)} 只，{target[0]}—{target[-1]}',flush=True)
    shares=szse_shares({c for c in members if mkt(c)=='sz'},target[0],target[-1])
    cache=ROOT/'pipeline/cache/fund-shares';cache.mkdir(parents=True,exist_ok=True)
    def sh(day):
        path=cache/(day+'.json')
        if day<target[-3] and path.exists():
            values=read_json(path)
        else:
            values=_sse_one(day)
            if len(values)<500: raise ValueError(f'{day} 沪市份额表疑似截断')
            save_json(path,values)
        return day,values
    with ThreadPoolExecutor(max_workers=3) as pool:
        for day,values in pool.map(sh,target):
            shares.update({(day,c):r[0] for c,r in values.items() if c in members and mkt(c)=='sh'})
    cache=ROOT/'pipeline/cache/fund-history';cache.mkdir(parents=True,exist_ok=True)
    def fetch(code):
        m=members[code]; path=cache/(code+'-'+target[0]+'-'+target[-1]+'.json')
        # 本地首次回补允许断点续跑；定时增量始终重新读取以纳入修订。
        if not old['dates'] and path.exists():return code,read_json(path)
        active=[d for d in target if d>=m['listed']]
        if not active:return code,[]
        prices=tdx_daily(('1.' if mkt(code)=='sh' else '0.')+code,active[0],target[-1])
        navs=nav_values(code,active[0],target[-1])
        output=[]
        for i,day in enumerate(target):
            if day<m['listed']:continue
            if (day,code) not in shares:
                raise ValueError(f'{code} {day} 缺少交易所份额，不填零')
            # 停牌或行情源缺记录时仍可由官方份额/净值计算申赎；价格保持空值。
            close,amount=prices.get(day,(None,None));nav=navs.get(day);q=shares[day,code]
            prev=target[i-1] if i else None
            delta=q-shares[prev,code]*share_factor(code,day) if prev and (prev,code) in shares and m['listed']<=prev else None
            if nav is None and delta not in (None,0):raise ValueError(f'{code} {day} 份额发生变动但缺少净值')
            # 已核实份额不变时净申赎为零；净值/规模仍留空，绝不沿用旧净值。
            flow=None if delta is None else 0 if delta==0 else delta*nav/1e8
            output.append({'date':day,'close':close,'amount':None if amount is None else round(amount/1e8,6),'nav':nav,
                           'shares':round(q/1e8,8),'aum':None if nav is None else round(q*nav/1e8,6),
                           'flow':None if flow is None else round(flow,6),
                           'premium':None if close is None or nav is None else round((close/close_factor(code,day)/nav-1)*100,4)})
        if not old['dates']:save_json(path,output)
        return code,output
    funds={}
    with ThreadPoolExecutor(max_workers=5) as pool:
        for code,rows in pool.map(fetch,sorted(members)):
            previous=old['funds'].get(code,{}).get('daily',[])
            merged={r['date']:r for r in previous}
            for r in rows:
                # 首个取数日没有上一日份额，不能覆盖已有的净流入。
                if r['flow'] is None and r['date'] in merged:r['flow']=merged[r['date']]['flow']
                merged[r['date']]=r
            daily=[merged[d] for d in sorted(merged)[-260:]]
            # 新核实的拆分事件也回算保留历史，不能只修正以后新增的行。
            for i,r in enumerate(daily):
                if i:
                    delta=r['shares']-daily[i-1]['shares']*share_factor(code,r['date'])
                    if r['nav'] is None and delta!=0:raise ValueError(f'{code} 历史份额变化缺少净值')
                    r['flow']=0 if delta==0 else round(delta*r['nav'],6)
                r['premium']=None if r['close'] is None or r['nav'] is None else round((r['close']/close_factor(code,r['date'])/r['nav']-1)*100,4)
            funds[code]={**members[code],'daily':daily}
            if len(funds)%50==0: print(f'逐券档案已计算 {len(funds)}/{len(members)}',flush=True)
    dates=sorted(set(old['dates'])|set(target))[-260:]
    result={'version':1,'updatedAt':stamp(),'dates':dates,'funds':funds,'actions':ACTIONS,
            'source':'沪深交易所份额 × 东方财富单位净值；通达信未复权日线成交额',
            'note':'净申赎=(当日份额−前一交易日份额×已核实折算比例)×当日单位净值。收盘折溢价按公告对齐同日收盘价与净值的份额单位，并非盘中 IOPV。'}
    # 完整计算之后才替换；规则和跨模块核对还会在统一发布流程再执行。
    save_json(PATH,result)
    print(f'逐券档案完整写入：{len(funds)} 只，{dates[0]}—{dates[-1]}',flush=True)
    return result


if __name__=='__main__':update()

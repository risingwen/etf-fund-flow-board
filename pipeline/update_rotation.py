"""归档东方财富行业/概念的 1、3、5、10、20 日融资快照。"""
from concurrent.futures import ThreadPoolExecutor
from market_common import SITE,read_json,save_json,report,numeric,stamp,YI


def update():
    path=SITE/'rotation.json';old=read_json(path,{'archives':{}})
    def fetch(item):
        kind,period=item;code='005' if kind=='industry' else '006'
        multi=period!=1
        raw=report('RPTA_WEB_BKQJYMXN' if multi else 'RPTA_WEB_BKJYMXN',
                   where=f'(BOARD_TYPE_CODE="{code}")'+(f'(INTERVAL_TYPE="{period}日")' if multi else ''),
                   sort=('END_DATE' if multi else 'TRADE_DATE')+',BOARD_CODE')
        rows=[{'code':r['BOARD_CODE'],'name':r['BOARD_NAME'],'date':r['END_DATE' if multi else 'TRADE_DATE'][:10],
               'balance':numeric(r['FIN_BALANCE'],YI),'net':numeric(r['FIN_NETBUY_AMT'],YI)} for r in raw]
        if not rows or len({r['code'] for r in rows})!=len(rows):raise ValueError(f'{kind} {period} 日快照为空或重复')
        return kind,str(period),rows
    data={'industry':{},'concept':{}}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for kind,period,rows in pool.map(fetch,[(k,p) for k in data for p in [1,3,5,10,20]]):data[kind][period]=rows
    day=max(r['date'] for by in data.values() for rows in by.values() for r in rows)
    archives=old['archives'];archives[day]=data
    result={'version':1,'updatedAt':stamp(),'latest':day,'data':data,
            'archives':{d:archives[d] for d in sorted(archives)[-22:]},
            'note':'东方财富行业/概念融资口径，板块存在重叠，不能相加。区间为源站滚动统计，逐行标出截止日期。首次采集起归档快照，不冒充完整历史。'}
    save_json(path,result);print(f'行业/概念融资快照截至 {day}；已归档 {len(result["archives"])} 日',flush=True)


if __name__=='__main__':update()

"""采集同指数比较所需的基金费率、跟踪标的；缺失费率保持空值。"""
import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta

import requests
from market_common import SITE,read_json,save_json,stamp
from update_daily import EAST_ASIA
from update_funds import universe


def parse(text,code):
    plain=re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',text)))
    if code not in plain or '管理费率' not in plain:raise ValueError('基金资料页不完整')
    result={}
    for key,label in [('managementFee','管理费率'),('custodyFee','托管费率')]:
        match=re.search(label+r'\s+(\d+(?:\.\d+)?)%',plain)
        result[key]=float(match[1]) if match else None
        if result[key] is not None and not 0<=result[key]<=3:raise ValueError('费率单位异常')
    match=re.search(r'跟踪标的\s+(.+?)\s*[◆◇]',plain)
    result['indexName']=match[1].strip() if match else None
    if result['indexName'] and ('本基金无跟踪标的' in result['indexName'] or len(result['indexName'])>80):result['indexName']=None
    return result


def update():
    path=SITE/'fund-facts.json';old=read_json(path,{'funds':{}});funds=old['funds'].copy()
    now=datetime.now(EAST_ASIA); members=universe()
    missing=sorted(set(members)-set(funds))
    # 提前两天分批复核，避免全部资料同日到期后连续多日显示过期。
    stale=sorted((c for c in members if c in funds and now-datetime.fromisoformat(funds[c]['checkedAt'])>timedelta(days=5)),key=lambda c:funds[c]['checkedAt'])
    todo=missing+stale[:120]
    def fetch(code):
        url=f'https://fundf10.eastmoney.com/jbgk_{code}.html'
        for _ in range(2):
            try:
                r=requests.get(url,timeout=12);r.raise_for_status();r.encoding='utf-8'
                return code,{**parse(r.text,code),'checkedAt':stamp(),'source':url}
            except (requests.RequestException,ValueError):pass
        return code,None
    failed=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for code,value in pool.map(fetch,todo):
            if value:funds[code]=value
            else:failed.append(code)
    result={'version':1,'updatedAt':stamp(),'funds':funds,'failed':failed,'pending':len(stale[120:])}
    save_json(path,result)
    print(f'基金资料 {len(funds)}/{len(members)} 只，更新失败 {len(failed)}；按公开资料核对，空值不等于免费',flush=True)
    return result


if __name__=='__main__':update()

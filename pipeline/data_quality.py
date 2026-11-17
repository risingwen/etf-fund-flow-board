"""发布前数据门禁。独立于网络采集，只使用明确校验通过的文件。"""
import hashlib
import csv
import json
import math
from datetime import datetime,timezone,timedelta
from pathlib import Path
from corporate_actions import ACTIONS,share_factor,close_factor

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'site'
ZONE=timezone(timedelta(hours=8))
MODULES={
 'daily':['site/data.js'], 'broad':['site/broad.js','reference/data/broad_members.csv'],
 'minute':['site/minute-history.json'], 'margin':['site/etf-margin.json','site/audit/market-coverage.json'],
 'leverage':['site/leverage.json'], 'themes':['site/themes.json'],
 'funds':['site/funds.json','reference/data/fund_actions.json'], 'facts':['site/fund-facts.json'], 'rotation':['site/rotation.json']}


def read(name):
    path=ROOT/name if '/' in name else SITE/name
    text=path.read_text(encoding='utf-8').strip()
    if name.endswith('.js'):text=text.split(' = ',1)[1].removesuffix(';')
    return json.loads(text)


def require(value,message):
    if not value:raise ValueError(message)


def finite(v,nullable=False):
    return (v is None and nullable) or (isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v))


def dates(values):
    require(bool(values) and values==sorted(set(values)),'日期为空、重复或倒序')
    for d in values:datetime.strptime(d,'%Y-%m-%d')


def numbers(values,nullable=False):
    require(all(finite(v,nullable) for v in values),'数值缺失、NaN 或无限值')


def curve(values,size):
    numbers(values);require(len(values)==size and min(values)>=0 and all(a<=b for a,b in zip(values,values[1:])),'累计曲线缺点、为负或倒退')


def latest(name):
    x=read(MODULES[name][0])
    if name=='daily':return x['daily']['dates'][-1]
    if name in ('minute','themes'):return x['calendar'][-1]
    if name in ('margin','leverage'):return x['daily'][-1]['date']
    if name=='facts':return min((v['checkedAt'][:10] for v in x['funds'].values()),default='')
    if name=='rotation':return x['latest']
    return x['dates'][-1]


def validate(name,previous=None):
    x=read(MODULES[name][0]); points=0
    if name=='daily':
        d=x['daily'];dates(d['dates']);n=len(d['dates'])
        for k in ('amount','netflow','idx','nfCov','amtCov'):
            require(len(d[k])==n,'日度字段长度不一致');numbers(d[k]);points+=n
        require(len(x['meta']['basket'])==20 and len({r['code'] for r in x['meta']['basket']})==20,'重点篮子成分缺失')
        require(d['dates'][-1]==x['meta']['latestDay'],'日度元数据日期不一致')
        require(d['nfCov'][-1]==20 and d['amtCov'][-1]==20,'末日成分不全')
        require(all(v>=0 for v in d['amount']),'成交额为负')
    elif name=='broad':
        dates(x['dates']);require(len(x['categories'])==12,'宽基分类缺失')
        for c in x['categories']:
            v=x['byCategory'][c];numbers(v);require(len(v)==len(x['dates']),'宽基曲线长度错误')
            require(v[-22:]==x['heat']['byCategory'][c],'热力表与历史不一致');points+=len(v)
        require(x['dates'][-22:]==x['heat']['dates'],'热力表日期不一致')
        require(x['meta']['dateLast']==x['dates'][-1],'宽基末日不一致')
        numbers(x['cumulative']);require(len(x['cumulative'])==len(x['dates']),'累计轴错位')
        for i,day in enumerate(x['dates']):
            if i and day>='2026-10-26':require(abs(x['cumulative'][i]-x['cumulative'][i-1]-sum(x['byCategory'][c][i] for c in x['categories']))<.001,'宽基累计额不能由日度净申赎复算')
    elif name=='minute':
        dates(x['calendar']);require(len(x['codes'])==20 and len(set(x['codes']))==20,'分钟篮子有误')
        require(len(x['times'])==240 and sorted(x['days'])==x['calendar'],'分钟日期或时间轴不完整')
        for v in x['days'].values():curve(v,240);points+=240
    elif name=='themes':
        dates(x['calendar']);require(len(x['groups'])==13 and len(x['times'])==48,'主题或时间轴缺失')
        for g in x['groups']:
            require(len(g['members'])==len({m['code'] for m in g['members']}),'主题成分重复')
            require(sorted(x['history'][g['name']])==x['calendar'],'主题归档日期缺失')
            for day,r in x['history'][g['name']].items():
                curve(r['values'],48);require(r['count']==sum(m['listed']<=day for m in g['members']),'上市成分数不符');points+=48
    elif name=='margin':
        dates([r['date'] for r in x['daily']]);require(len(x['categories'])==4,'两融分类缺失')
        for r in x['daily']:
            for c in x['categories']:
                v=r['categories'][c];numbers([v[k] for k in ('balance','shortBalance','buy','repay','net')])
                require(v['count']>0 and min(v[k] for k in ('balance','shortBalance','buy','repay'))>=0,'两融余额或覆盖异常')
                require(abs(v['buy']-v['repay']-v['net'])<.00001,'融资净买入恒等式失败');points+=5
        require(x.get('details'),'缺少逐券两融明细')
        for code,rows in x['details'].items():
            dates([r['date'] for r in rows])
            for r in rows:
                numbers([r[k] for k in ('balance','shortBalance','buy','repay','net')])
                require(min(r[k] for k in ('balance','shortBalance','buy','repay'))>=0 and abs(r['buy']-r['repay']-r['net'])<.00001,f'{code} 两融逐券恒等式失败');points+=5
        for c in x['categories']:
            codes=[m['code'] for m in x['members'] if m['category']==c]
            for field in ('balance','buy','repay','net','shortBalance'):
                expected=sum(x['details'][code][-1][field] for code in codes if code in x['details'] and x['details'][code][-1]['date']==x['daily'][-1]['date'])
                require(abs(expected-x['daily'][-1]['categories'][c][field])<.0001,'两融汇总与逐券明细不符')
        audit=read('site/audit/market-coverage.json')
        require(audit['date']==x['daily'][-1]['date'] and audit['count']==len(x['reportedCodes']),'末日交易所交叉校验未完成')
        require(all(abs(v)<1 for r in audit['rows'] for v in r['differenceYuan'].values()),'两融交易所核对差异')
        require({r['code'] for r in audit['rows']}==set(x['reportedCodes']),'两融交叉校验覆盖不一致')
        for r in audit['rows']:
            for field in ('balance','buy'):
                require(abs(x['details'][r['code']][-1][field]*1e8-r[field+'Yuan'])<101,'两融发布明细与交易所核对凭据不一致')
    elif name=='leverage':
        dates([r['date'] for r in x['daily']]);dates([r['date'] for r in x['accounts']])
        for r in x['daily']:
            numbers([r[k] for k in ('balance','shortBalance','buy','shBalance','szBalance')]);points+=5
            require(abs(r['balance']-r['shBalance']-r['szBalance'])<.00001,'沪深合计不等于两市加总')
            if r['repay'] is not None and r['net'] is not None:require(abs(r['buy']-r['repay']-r['net'])<.00001,'两融市场净买入恒等式失败')
        require(x['industries'],'行业快照为空')
    elif name=='funds':
        dates(x['dates']);require(len(x['funds'])>=500,'逐券覆盖异常减少')
        require(x.get('actions')==ACTIONS,'份额事件未纳入复算')
        with (ROOT/'reference/data/broad_members.csv').open(encoding='utf-8',newline='') as stream:expected_codes={r['code'] for r in csv.DictReader(stream)}
        expected_codes.update(m['code'] for g in read('themes.json')['groups'] for m in g['members'])
        require(set(x['funds'])==expected_codes,'逐券档案与宽基/主题目录覆盖不一致')
        for code,f in x['funds'].items():
            rows=f['daily'];dates([r['date'] for r in rows])
            expected=[d for d in x['dates'] if d>=f['listed']]
            require([r['date'] for r in rows]==expected,f'{code} 日度覆盖不齐')
            for i,r in enumerate(rows):
                numbers([r['shares']]);numbers([r[k] for k in ('nav','aum','close','amount','premium','flow')],True)
                require(r['shares']>=0 and all(r[k] is None or r[k]>0 for k in ('nav','close')) and all(r[k] is None or r[k]>=0 for k in ('amount','aum')),f'{code} 单位或金额为负')
                require((r['nav'] is None and r['aum'] is None) or r['nav'] is not None and r['aum'] is not None and abs(r['shares']*r['nav']-r['aum'])<.00001,f'{code} 规模不等于份额乘净值')
                if i:
                    delta=r['shares']-rows[i-1]['shares']*share_factor(code,r['date'])
                    require(r['flow'] is not None and ((delta==0 and r['flow']==0) or r['nav'] is not None and abs(delta*r['nav']-r['flow'])<.00001),f'{code} 净申赎无法由相邻份额复算')
                    if r['nav'] and rows[i-1]['nav']:
                        ratio=r['nav']/rows[i-1]['nav']*share_factor(code,r['date'])
                        require(.67<ratio<1.5,f'{code} 单日净值倍数异常，需核实拆分/分红或数据单位')
                require(((r['close'] is None or r['nav'] is None) and r['premium'] is None) or r['close'] is not None and r['nav'] is not None and r['premium'] is not None and abs((r['close']/close_factor(code,r['date'])/r['nav']-1)*100-r['premium'])<.0001,f'{code} 折溢价单位异常');points+=7
    elif name=='rotation':
        dates(sorted(x['archives']))
        require(x['data']==x['archives'][x['latest']],'板块快照与归档不一致')
        for data in x['archives'].values():
            require(set(data)=={'industry','concept'},'板块类型缺失')
            for periods in data.values():
                require(set(periods)=={'1','3','5','10','20'},'板块窗口缺失')
                for rows in periods.values():
                    require(len(rows)>100 and len(rows)==len({r['code'] for r in rows}),'板块缺行或重复')
                    for r in rows:numbers([r['balance'],r['net']]);require(r['balance']>=0,'板块融资余额为负');points+=2
    elif name=='facts':
        require(x['funds'],'基金资料为空')
        for f in x['funds'].values():
            for k in ('managementFee','custodyFee'):
                require(f[k] is None or finite(f[k]) and 0<=f[k]<=3,'费率单位错误');points+=1
    if previous and name!='facts':require(latest(name)>=previous,'拒绝数据日期倒退')
    return {'checkedValues':points,'rules':'日期唯一、覆盖、数值单位、金额恒等式、逐券汇总；适用项逐项检查'}


def cross_validate():
    """仅比较同日同口径，不把公布时差或历史口径分界误判成错误。"""
    board=read('data.js');broad=read('broad.js');archive=read('minute-history.json')
    for i,day in enumerate(board['daily']['dates']):
        if day>='2026-10-26' and day in archive['days']:
            require(abs(board['daily']['amount'][i]-archive['days'][day][-1])<.03,f'{day} 日成交额与分钟收盘额不一致')
    if not (SITE/'funds.json').exists():return
    f=read('funds.json'); rows={c:{r['date']:r for r in v['daily']} for c,v in f['funds'].items()}
    basket=[r['code'] for r in board['meta']['basket']]
    for i,day in enumerate(board['daily']['dates']):
        if day<'2026-10-26' or day not in f['dates'][1:]:continue
        require(all(day in rows[c] for c in basket),'重点篮子逐只核对缺行')
        for field,target in [('flow','netflow'),('amount','amount')]:
            require(abs(sum(rows[c][day][field] for c in basket)-board['daily'][target][i])<.03,f'{day} 20 只 {target} 与逐券档案不符')
    for i,day in enumerate(broad['dates']):
        if day<'2026-10-26' or day not in f['dates'][1:]:continue
        for cat in broad['categories']:
            codes=[c for c,v in f['funds'].items() if v['kind']=='宽基' and cat in v['groups'] and v['listed']<=day]
            total=sum(rows[c][day]['flow'] or 0 for c in codes)
            require(abs(total-broad['byCategory'][cat][i])<.02,f'{day} {cat} 与逐只份额净值复算不符：{total:.4f}/{broad["byCategory"][cat][i]}')
    themes=read('themes.json')
    for day in f['dates'][-3:]:
        if day not in themes['calendar']:continue
        for g in themes['groups']:
            total=sum(rows[m['code']][day]['amount'] for m in g['members'] if m['listed']<=day)
            require(abs(total-themes['history'][g['name']][day]['values'][-1])<.02,f'{day} {g["name"]} 分时与逐券日线不符')


def hashes(name):
    return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in MODULES[name]}


def validate_release():
    health=read('data-quality.json')
    for name in MODULES:
        validate(name)
        require(health['modules'][name]['latest']==latest(name),f'{name} 健康报告日期与文件不一致')
        require(hashes(name)==health['modules'][name]['hashes'],f'{name} 文件已变更，尚未完成校验签署')
    cross_validate()
    print('发布门禁通过：所有文件校验、金额复算、同口径模块对账与签署版本一致')


if __name__=='__main__':validate_release()

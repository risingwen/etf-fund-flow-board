"""隔离采集失败、回滚不合格候选、记录数据健康状态，统一供定时任务使用。"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime,timedelta

import data_quality as q
from market_common import save_json,stamp
from public_quotes import tdx_daily

COMMANDS={
 'daily':['update_daily.py'], 'broad':['update_broad.py'], 'minute':['update_minute_history.py'],
 'themes':['update_themes.py'], 'funds':['update_funds.py'],
 'margin':['update_etf_margin.py','verify_market_sources.py'],
 'leverage':['update_leverage.py'], 'rotation':['update_rotation.py'], 'facts':['update_fund_facts.py']}


def snapshot(paths):
    return {p:(q.ROOT/p).read_bytes() if (q.ROOT/p).exists() else None for p in paths}


def restore(saved):
    for name,value in saved.items():
        path=q.ROOT/name
        if value is None:path.unlink(missing_ok=True)
        else:path.write_bytes(value)


def transaction(name,collect,check_cross=True):
    """文件级事务：采集或任何门禁失败，都恢复上一个可发布版本。"""
    saved=snapshot(q.MODULES[name]); previous=q.latest(name) if saved[q.MODULES[name][0]] else None
    stage='source'
    try:
        collect()
        stage='validation';result=q.validate(name,previous)
        if check_cross:q.cross_validate()
        return {'ok':True,'validation':result,'lastSuccessAt':stamp()}
    except Exception as error:
        restore(saved)
        message=str(error).replace(str(q.ROOT),'工作目录')[:700]
        return {'ok':False,'failureType':stage,'error':message}


def freshness(name,actual,calendar,now):
    today=now.date().isoformat()
    if name=='facts':
        age=(now.date()-datetime.fromisoformat(actual).date()).days
        return {'expected':'每周核对','lag':max(0,age-7),'freshness':'资料待复核' if age>7 else '已核对'}
    cutoff=today if name in ('minute','themes') and (now.hour,now.minute)>=(15,20) else (now.date()-timedelta(days=1)).isoformat()
    expected=max((d for d in calendar if d<=cutoff),default=actual)
    lag=sum(actual<d<=expected for d in calendar)
    waiting=lag==1 and name not in ('minute','themes') and (now.hour,now.minute)<(8,50)
    return {'expected':expected,'lag':lag,'freshness':'等待披露' if waiting else '滞后' if lag else '已到预期交易日'}


def warnings(name):
    x=q.read(q.MODULES[name][0]); result=[]
    if name=='funds':
        gaps=[f'{code}/{r["date"]}' for code,f in x['funds'].items() for r in f['daily'] if r['amount'] is None]
        if gaps:result.append(f'{len(gaps)} 条日行情缺失，成交额/收盘折溢价留空；净申赎按完整份额和净值计算。'+', '.join(gaps[:5]))
        navs=[f'{code}/{r["date"]}' for code,f in x['funds'].items() for r in f['daily'] if r['nav'] is None]
        if navs:result.append(f'{len(navs)} 条净值未披露，规模/折溢价留空；仅在交易所确认相邻份额完全不变时净申赎记零。'+', '.join(navs[:5]))
    if name=='facts' and (x.get('failed') or x.get('pending')):
        result.append(f'资料获取失败 {len(x.get("failed",[]))} 只；待补 {x.get("pending",0)} 只，费率空值不等于免费。')
    if name in ('broad','themes'):
        c=q.read('reference/data/etf_catalogue.json')
        age=datetime.now(q.ZONE)-datetime.fromisoformat(c['checkedAt'])
        if age.total_seconds()>8*3600:result.append(f'使用 {c["checkedAt"][:16]} 核实的交易所目录，新上市基金可能尚未纳入。')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--modules',nargs='*',choices=COMMANDS,default=list(COMMANDS))
    args=parser.parse_args()
    now=datetime.now(q.ZONE); health_path=q.SITE/'data-quality.json'
    old=q.read('data-quality.json') if health_path.exists() else {'modules':{}}
    calendar_error=None
    try:
        calendar=sorted(tdx_daily('1.000001','2025-01-01',now.date().isoformat()))
        q.require(calendar and (now.date()-datetime.fromisoformat(calendar[-1]).date()).days<12,'交易日历未更新')
        calendar_at=stamp()
    except Exception as error:
        calendar=old.get('calendar',{}).get('dates',[])
        if not calendar:raise
        calendar_at=old['calendar']['checkedAt'];calendar_error=str(error)[:300]
    os.environ['ETF_REUSE_CATALOGUE']='1'
    related=['daily','broad','minute','themes','funds']
    original=snapshot([p for n in related for p in q.MODULES[n]])
    state={}
    for name,scripts in COMMANDS.items():
        previous=old.get('modules',{}).get(name,{})
        if name in args.modules:
            print(f'\n[{name}] 开始采集与发布前校验',flush=True)
            def collect():
                for script in scripts:
                    run=subprocess.run([sys.executable,str(q.ROOT/'pipeline'/script)],cwd=q.ROOT,
                                       capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=1500)
                    print(run.stdout[-5000:],flush=True)
                    if run.returncode:raise RuntimeError(script+'：'+(run.stderr or run.stdout).strip().splitlines()[-1][-550:])
            status=transaction(name,collect,check_cross=False)
            status['checkedAt']=stamp()
            if not status['ok']:print(f'[{name}] 拦截并保留旧数据：{status["error"]}',flush=True)
        else:
            status={k:v for k,v in previous.items() if k not in ('hashes','warnings','latest','expected','lag','freshness')}
            status.setdefault('ok',True);status.setdefault('checkedAt',stamp())
        # 对保留的文件也重新校验，损坏旧文件不能通过降级绕过门禁。
        status['validation']=q.validate(name)
        actual=q.latest(name)
        state[name]={**status,'lastSuccessAt':status.get('lastSuccessAt',previous.get('lastSuccessAt')),
                     'latest':actual,**freshness(name,actual,calendar,now),
                     'warnings':warnings(name),'hashes':q.hashes(name)}
    try:q.cross_validate()
    except Exception as error:
        # 同一批新增目录、逐券与汇总须一起核对；不拿旧目录误拦新上市基金。
        restore(original)
        for name in related:
            s=state[name];s.update(ok=False,failureType='validation',error='跨模块对账失败，相关数据整体回滚：'+str(error)[:400])
            s['validation']=q.validate(name);s['latest']=q.latest(name);s['hashes']=q.hashes(name)
            s.update(freshness(name,s['latest'],calendar,now));s['lastSuccessAt']=old.get('modules',{}).get(name,{}).get('lastSuccessAt')
        q.cross_validate()
    clean=not calendar_error and all(s['ok'] and (not s['lag'] or s['freshness']=='等待披露') for s in state.values())
    health={'version':1,'checkedAt':stamp(),'clean':clean,
            'calendar':{'dates':calendar,'checkedAt':calendar_at,'error':calendar_error},'modules':state,
            'note':'采集失败或校验失败保留上个有效版本。字段缺失保持空值。通过校验不代表上游数据绝无错误；页面显示各模块实际日期。'}
    save_json(health_path,health)
    save_json(q.SITE/'market-status.json',{'version':1,'checkedAt':stamp(),'modules':{n:{'ok':s['ok'],'error':s.get('error')} for n,s in state.items() if n in ('margin','leverage','themes')}})
    q.validate_release()
    print('全部更新正常' if clean else '安全数据和异常状态已生成；部分模块需重试')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as out:out.write(f'clean={str(clean).lower()}\n')
    return 0


if __name__=='__main__':sys.exit(main())

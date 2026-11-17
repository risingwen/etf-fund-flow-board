"""交易所目录共享缓存；缓存回退有有效期，且必须对外显示降级状态。"""
import json
import os
from datetime import datetime, timedelta,timezone
from pathlib import Path

PATH = Path(__file__).resolve().parents[1]/'reference/data/etf_catalogue.json'


def cached_catalogue(fetch):
    now=datetime.now(timezone(timedelta(hours=8)))
    old=json.loads(PATH.read_text(encoding='utf-8')) if PATH.exists() else None
    if old and os.environ.get('ETF_REUSE_CATALOGUE')=='1':
        age=now-datetime.fromisoformat(old['checkedAt'])
        if age<timedelta(hours=8):
            return old['members']
    try:
        members=fetch()
        if len(members)<1500 or len(members)!=len({m['code'] for m in members}):
            raise ValueError('交易所目录数量或唯一性校验失败')
        value={'checkedAt':now.isoformat(timespec='seconds'),'members':members}
        temp=PATH.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8',newline='\n');temp.replace(PATH)
        return members
    except Exception:
        if not old or now-datetime.fromisoformat(old['checkedAt'])>timedelta(days=3):
            raise
        print(f'目录降级：使用 {old["checkedAt"]} 已验证目录，本次新增基金可能尚未纳入',flush=True)
        return old['members']

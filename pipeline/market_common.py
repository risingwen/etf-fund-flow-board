"""扩展看板共用的公开数据读取、分页及原子写入。"""
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

from update_daily import EAST_ASIA, request

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'
YI = 100_000_000


def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def save_json(path, data):
    text = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n'
    if path.exists() and path.read_text(encoding='utf-8') == text:
        return
    temp = path.with_suffix('.tmp')
    temp.write_text(text, encoding='utf-8', newline='\n')
    temp.replace(path)


def stamp():
    return datetime.now(EAST_ASIA).isoformat(timespec='seconds')


def overlap(rows, default, key='date'):
    return (datetime.fromisoformat(rows[-1][key]) - timedelta(days=10)).date().isoformat() if rows else default


def numeric(value, divisor=1):
    if value is None:
        return None
    value = float(value) / divisor
    if not math.isfinite(value):
        raise ValueError('非有限数值')
    return round(value, 6)


def merge(old, new):
    rows = {r['date']: r for r in old}
    rows.update({r['date']: r for r in new})
    return [rows[d] for d in sorted(rows)]


def report(name, columns='ALL', where='', sort='DATE'):
    """按总数校验所有页，避免接口截断后悄悄少算。"""
    params = dict(reportName=name, columns=columns, filter=where, sortColumns=sort,
                  sortTypes=','.join('1' for _ in sort.split(',')), pageSize=500, pageNumber=1, source='WEB')
    rows = []
    expected = None
    while True:
        payload = request('https://datacenter-web.eastmoney.com/api/data/v1/get', params,
                          'https://data.eastmoney.com/rzrq/')
        if payload.get('code') == 9201 and not rows:
            return []
        if not payload.get('success') or not payload.get('result'):
            raise ValueError(f'{name} 返回异常：{payload.get("message")}')
        result = payload['result']
        if expected is None:
            expected = result['count']
        if expected != result['count']:
            raise ValueError(f'{name} 分页期间数据变化，请重试')
        rows.extend(result['data'])
        if params['pageNumber'] >= result['pages']:
            break
        params['pageNumber'] += 1
    if len(rows) != expected:
        raise ValueError(f'{name} 分页缺失 {len(rows)}/{expected}')
    return rows

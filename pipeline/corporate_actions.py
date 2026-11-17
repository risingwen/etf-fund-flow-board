"""只采用公告已核实的份额事件；未知净值跳变由校验门禁阻断。"""
import json
from pathlib import Path

ACTIONS=json.loads((Path(__file__).resolve().parents[1]/'reference/data/fund_actions.json').read_text(encoding='utf-8'))


def action(code,day):
    return next((r for r in ACTIONS.get(code,[]) if r['date']==day),{})


def share_factor(code,day):return action(code,day).get('shareFactor',1)


def close_factor(code,day):return action(code,day).get('closeFactor',1)

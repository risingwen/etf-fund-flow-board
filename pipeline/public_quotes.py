"""真实日线成交额的公开备用源；不以收盘价乘成交量替代成交额。"""
import math
import os
import time


def tdx_daily(secid, start, end):
    from eltdx import TdxClient
    market, code = secid.split('.')
    symbol = ('sh' if market == '1' else 'sz') + code
    result = {}
    errors = []
    for host in [os.environ.get('TDX_HOST','119.29.19.242:7709'), '119.29.19.242:7709']:
        try:
            with TdxClient(host=host, timeout=12) as client:
                for offset in range(0,64000,800):
                    bars = client.bars.get(symbol,period='day',start=offset,count=800).bars
                    for b in bars:
                        day = b.time.date().isoformat()
                        if start<=day<=end:
                            if not all(math.isfinite(v) and v>=0 for v in (b.close,b.amount)):
                                raise ValueError('日线含非法数值')
                            result[day]=(b.close,b.amount)
                    if not bars or len(bars)<800 or bars[0].time.date().isoformat()<start:
                        break
            return result
        except Exception as e:
            errors.append(type(e).__name__)
            time.sleep(1)
    raise RuntimeError(f'{symbol} 公开日线均未返回：{errors}')

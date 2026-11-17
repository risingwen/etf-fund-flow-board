"""用沪深交易所原始披露逐只复核末日 ETF 两融余额与融资买入额。"""
import io

from openpyxl import load_workbook
from market_common import SITE, read_json, report, save_json, stamp
from update_daily import request


def main():
    board = read_json(SITE/'etf-margin.json')
    day = board['daily'][-1]['date']
    codes = board['reportedCodes']
    raw = []
    for i in range(0,len(codes),40):
        subset=','.join('"'+c+'"' for c in codes[i:i+40])
        raw.extend(report('RPTA_WEB_RZRQ_GGMX','DATE,SCODE,RZYE,RZMRE',
                          f'(DATE=\'{day}\')(SCODE in ({subset}))','DATE,SCODE'))
    em = {r['SCODE']:r for r in raw}
    sh = request('https://query.sse.com.cn/marketdata/tradedata/queryMargin.do',
                 {'isPagination':'true','tabType':'mxtype','detailsDate':day.replace('-',''),
                  'pageHelp.pageSize':5000,'pageHelp.pageNo':1},'https://www.sse.com.cn/')
    assert len(sh['result'])==int(sh['pageHelp']['total'])
    official = {r['stockCode'].strip():{'balance':float(r['rzye']),'buy':float(r['rzmre'])} for r in sh['result']}
    blob = request('https://www.szse.cn/api/report/ShowReport',
                    {'SHOWTYPE':'xlsx','CATALOGID':'1837_xxpl','txtDate':day,'TABKEY':'tab2'},
                    'https://www.szse.cn/disclosure/margin/margin/index.html',binary=True)
    book=load_workbook(io.BytesIO(blob),read_only=True,data_only=True)
    try:
        book.active.reset_dimensions(); rows=book.active.values; header=list(next(rows))
        code=header.index('证券代码'); balance=header.index('融资余额(元)'); buy=header.index('融资买入额(元)')
        num=lambda v:float(str(v).replace(',',''))
        official.update({str(r[code]).strip():{'balance':num(r[balance]),'buy':num(r[buy])} for r in rows})
    finally:
        book.close()
    audit=[]
    expected = {m['code'] for m in board['members']} & set(official)
    assert expected == set(codes), f'交易所标的覆盖差异：缺少 {sorted(expected-set(codes))}，多出 {sorted(set(codes)-expected)}'
    for code in codes:
        assert code in official and code in em, f'{code} 交易所或行情源缺记录'
        diff={key:em[code][field]-official[code][key] for key,field in [('balance','RZYE'),('buy','RZMRE')]}
        assert all(abs(v)<1 for v in diff.values()), f'{code} 两源数值不符 {diff}'
        detail=board['details'][code][-1]
        assert detail['date']==day
        for key in ('balance','buy'):
            assert abs(detail[key]*1e8-official[code][key])<101, f'{code} 发布明细与官方披露不符'
        audit.append({'code':code,'balanceYuan':official[code]['balance'],'buyYuan':official[code]['buy'],'differenceYuan':diff})
    result={'checkedAt':stamp(),'date':day,'count':len(audit),'rows':audit,
            'sources':['https://www.sse.com.cn/market/othersdata/margin/detail/','https://www.szse.cn/disclosure/margin/margin/index.html','https://data.eastmoney.com/rzrq/']}
    save_json(SITE/'audit/market-coverage.json',result)
    print(f'{day} {len(audit)} 只 ETF 融资余额和买入额，与沪深交易所原始披露逐只一致')


if __name__ == '__main__':
    main()

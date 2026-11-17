"""本地浏览器验收：排名复算、同指数比较、状态保留和错误版本拒收。"""
import hashlib
import json
import threading
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[2];SITE=ROOT/'site'
names=json.loads((SITE/'history-manifest.json').read_text())['files']
original={n:(SITE/n).read_bytes() for n in names}
changed=dict(original)
x=json.loads(changed['funds.json']);x['funds']['588000']['name']+='（刷新测试）'
changed['funds.json']=json.dumps(x,ensure_ascii=False).encode()
health=json.loads(changed['data-quality.json']);health['modules']['broad'].update(ok=False,failureType='validation',error='测试：分类汇总与逐券不一致')
changed['data-quality.json']=json.dumps(health,ensure_ascii=False).encode()
state={'files':original,'broken':False,'offline':False}


class Server(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        n=urlsplit(self.path).path.strip('/')
        if n=='history-manifest.json':
            if state['offline']:self.send_error(503);return
            h={k:hashlib.sha256(v).hexdigest() for k,v in state['files'].items()}
            content=json.dumps({'version':hashlib.sha256(json.dumps(h,sort_keys=True).encode()).hexdigest(),'files':h}).encode()
        elif n in original:content=original[n] if state['broken'] and n=='funds.json' else state['files'][n]
        else:return super().do_GET()
        self.send_response(200);self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)


server=ThreadingHTTPServer(('127.0.0.1',0),partial(Server,directory=str(SITE)))
threading.Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{server.server_port}/'
with sync_playwright() as p:
    b=p.chromium.launch()
    for width in [1280,390]:
        state.update(files=original,broken=False,offline=False)
        page=b.new_page(viewport={'width':width,'height':900});errors=[];navigations=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('framenavigated',lambda f:navigations.append(f.url) if f==page.main_frame else None)
        page.clock.install();page.goto(base+'research.html',wait_until='domcontentloaded')
        expect(page.locator('#researchStatus')).to_contain_text('592',timeout=30000)
        # 以原始份额变动与净值独立复算选定基金各个窗口，不只比较页面内部函数。
        fund=json.loads(original['funds.json'])['funds']['510300']
        for period in [1,3,5,10,20]:
            expected=sum((a['shares']-fund['daily'][i-1]['shares'])*a['nav'] for i,a in enumerate(fund['daily']) if i>=len(fund['daily'])-period)
            actual=page.evaluate('(n)=>ETFResearch.rankings("funds",n).rows.find(r=>r.code==="510300").value',period)
            assert abs(actual-expected)<.0001,(period,actual,expected)
        assert page.evaluate('ETFResearch.windowSum([{date:"2026-11-16",flow:null}],["2026-11-16"],"flow")') is None
        page.select_option('#rankScope','themes');page.select_option('#rankPeriod','20');assert page.locator('#rankTable tbody tr').count()==13
        page.select_option('#rankScope','broad');assert page.locator('#rankTable tbody tr').count()==12
        page.select_option('#rankScope','margin');expect(page.locator('#rankMeta')).to_contain_text('两融覆盖')
        page.select_option('#rankScope','funds');page.locator('#rankSearch').fill('510300');assert page.locator('#rankTable tbody tr').count()==1
        page.locator('#rankTable [data-fund="510300"]').click();expect(page.locator('#fundCode')).to_have_text('510300')
        assert page.evaluate('ETFResearch.peers("510300").length')>10
        page.evaluate('ETFResearch.choose("588000",false)');expect(page.locator('#fundMarginWrap')).to_be_visible()
        page.evaluate('echarts.getInstanceByDom(document.getElementById("fundChart")).dispatchAction({type:"dataZoom",start:30,end:85})')
        page.select_option('#rotationKind','concept');page.select_option('#rotationPeriod','20');page.locator('#rotationSearch').fill('半导体')
        assert page.locator('#rotationTable tbody tr').count()>=1
        page.evaluate('scrollTo(0,450)');y=page.evaluate('scrollY')
        state.update(files=changed,broken=True)
        page.evaluate('ETFResearch.refresh()');expect(page.locator('#researchStatus')).to_contain_text('保留现有画面')
        assert '刷新测试' not in page.locator('#fundName').inner_text()
        state['broken']=False;page.clock.fast_forward(60001)
        expect(page.locator('#fundName')).to_contain_text('刷新测试',timeout=30000)
        assert page.locator('#rankPeriod').input_value()=='20' and page.locator('#rankSearch').input_value()=='510300'
        assert page.locator('#rotationKind').input_value()=='concept' and page.locator('#rotationSearch').input_value()=='半导体'
        assert abs(page.evaluate('scrollY')-y)<3
        assert page.evaluate('echarts.getInstanceByDom(document.getElementById("fundChart")).getOption().dataZoom[0].start')==30
        expect(page.locator('#dataHealth')).to_contain_text('校验失败，已拦截')
        assert len(navigations)==1 and not errors,errors
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        state['offline']=True;page.evaluate('ETFResearch.refresh()');expect(page.locator('#researchStatus')).to_contain_text('保留现有画面')
        assert '刷新测试' in page.locator('#fundName').inner_text()
        print(f'PASS {width}px：多窗口复算、分类/两融、同指数、校验失败、60秒同步、状态/缩放/滚动保留、离线回退')
        page.close()
    state.update(files=original,broken=False,offline=False)
    for path,status,ready in [('index.html','historyUpdate','历史数据自动同步'),('markets.html','marketUpdate','自动同步已启用')]:
        page=b.new_page(viewport={'width':390,'height':850});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.route('**/appstock/**',lambda r:r.abort())
        page.goto(base+path,wait_until='domcontentloaded');expect(page.locator('#'+status)).to_contain_text(ready,timeout=30000)
        expect(page.locator('#dataHealth summary')).to_be_visible();assert not errors,errors
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        print('PASS 原页面回归',path);page.close()
    b.close()
server.shutdown()

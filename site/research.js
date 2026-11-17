(() => {
  'use strict';
  const $=id=>document.getElementById(id), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=(x,n=2)=>Number.isFinite(x)?x.toLocaleString('zh-CN',{minimumFractionDigits:n,maximumFractionDigits:n}):'—';
  const signed=x=>Number.isFinite(x)?(x>0?'+':'')+fmt(x):'—';
  const cell=x=>`<td class="num ${x>0?'up':x<0?'down':''}">${signed(x)}</td>`;
  const link=(code,name)=>`<button class="fund-link" data-fund="${esc(code)}">${esc(name)}</button>`;
  const table=(headers,rows)=>`<table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')||`<tr><td colspan="${headers.length}">当前筛选没有完整数据</td></tr>`}</tbody></table>`;
  const charts={};let data,version='',busy=false,selected='510300',lookups={};
  const names=['funds.json','fund-facts.json','etf-margin.json','themes.json','rotation.json'];
  const groups=kind=>kind==='broad'?[...new Set(Object.values(data.funds.funds).filter(f=>f.kind==='宽基').flatMap(f=>f.groups))]:data.themes.groups.map(g=>g.name);
  const fundEntries=()=>Object.entries(data.funds.funds);
  function validate(b) {
    const f=b['funds.json'];
    if(!f?.dates?.length||Object.keys(f.funds||{}).length<500||!b['etf-margin.json']?.details||b['themes.json']?.groups?.length!==13||!b['rotation.json']?.archives)throw Error('研究数据覆盖不完整');
    for(const [code,v] of Object.entries(f.funds)){
      if(!/^\d{6}$/.test(code)||!v.daily.length)throw Error('基金代码或日期无效');
      v.daily.forEach((r,i)=>{if(i&&r.date<=v.daily[i-1].date||!Number.isFinite(r.shares)||r.flow!==null&&!Number.isFinite(r.flow))throw Error('基金明细格式异常');});
    }
  }
  function windowSum(rows,days,field) {
    const by=Object.fromEntries(rows.map(r=>[r.date,r]));
    if(!days.length||days.some(d=>!Number.isFinite(by[d]?.[field])))return null;
    return days.reduce((n,d)=>n+by[d][field],0);
  }
  function groupFlow(group,day) {
    let total=0,count=0;
    for(const [code,f] of fundEntries())if(f.groups.includes(group)&&f.listed<=day){
      const row=lookups[code][day];if(!row)return null;
      if(row.flow===null){if(f.listed===day)continue;return null;}
      total+=row.flow;count++;
    }
    return count?total:null;
  }
  function rankings(scope,period) {
    const dates=(scope==='margin'?data.margin.daily.map(r=>r.date):data.funds.dates).slice(-period);
    if(dates.length!==period)return {dates,rows:[],missing:0};
    const rows=[];let missing=0;
    if(scope==='funds'||scope==='margin'){
      const entries=scope==='funds'?fundEntries():Object.entries(data.margin.details).map(([code,daily])=>[code,{...data.margin.members.find(m=>m.code===code),daily}]);
      for(const [code,f] of entries){
        const flow=windowSum(f.daily,dates,scope==='margin'?'net':'flow');
        if(flow===null){missing++;continue;}
        rows.push({code,name:f.name,label:scope==='margin'?f.category:f.groups.join(' / '),value:flow,latest:f.daily.at(-1)});
      }
    }else for(const name of groups(scope)){
      const values=dates.map(d=>groupFlow(name,d));
      if(values.some(v=>v===null)){missing++;continue;}
      rows.push({name,label:scope==='broad'?'宽基净申赎':'主题净申赎',value:values.reduce((a,b)=>a+b,0)});
    }
    return {dates,rows,missing};
  }
  function renderRank(){
    const scope=$('rankScope').value,p=+$('rankPeriod').value,r=rankings(scope,p),query=$('rankSearch').value.trim().toLowerCase();
    const rows=r.rows.filter(x=>[x.code,x.name,x.label].join(' ').toLowerCase().includes(query)).sort((a,b)=>($('rankOrder').value==='asc'?1:-1)*(a.value-b.value));
    $('rankMeta').textContent=`${r.dates[0]}—${r.dates.at(-1)} · ${p} 个交易日 · 单位亿元 · ${rows.length} 项${r.missing?`；${r.missing} 项缺少完整窗口，未排名`:''}${scope==='margin'?'。两融覆盖 4 类宽基中有公开记录的标的 ETF。':''}`;
    $('rankTable').innerHTML=table(['排名','代码 / 分类','名称','归属','区间净额（亿）'],rows.map((r,i)=>`<tr><td>${i+1}</td><td>${esc(r.code||'分类')}</td><td>${r.code?link(r.code,r.name):esc(r.name)}</td><td>${esc(r.label)}</td>${cell(r.value)}</tr>`));
  }
  function renderHeat(){
    const dates=data.funds.dates.slice(1).slice(-22),gs=groups('themes');
    const maxima=Object.fromEntries(gs.map(g=>[g,Math.max(...dates.map(d=>Math.abs(groupFlow(g,d)||0)),.001)]));
    $('themeFlowMeta').textContent=`${dates[0]}—${dates.at(-1)} · 最近 ${dates.length} 个可复算交易日 · ${new Set(data.themes.groups.flatMap(g=>g.members.map(m=>m.code))).size} 只主题 ETF（去重）`;
    $('themeFlowTable').innerHTML=table(['日期',...gs],[...dates].reverse().map(d=>`<tr><td>${d}</td>${gs.map(g=>{const v=groupFlow(g,d),alpha=Number.isFinite(v)?(.05+.4*Math.abs(v)/maxima[g]):0;return `<td class="num ${v>0?'up':v<0?'down':''}" style="background:rgba(${v>=0?'191,70,55':'24,126,87'},${alpha})">${signed(v)}</td>`;}).join('')}</tr>`));
  }
  function plot(id,rows,barKey,lineKey,barName,lineName){
    const chart=charts[id]||(charts[id]=echarts.init($(id)));const zoom=chart.getOption()?.dataZoom?.map(z=>({start:z.start,end:z.end}));
    chart.setOption({animation:false,tooltip:{trigger:'axis',valueFormatter:v=>fmt(v)},legend:{data:[barName,lineName],top:0},grid:{left:62,right:65,top:42,bottom:64},
      xAxis:{type:'category',data:rows.map(r=>r.date)},yAxis:[{type:'value',name:'亿元'},{type:'value',name:'亿元',scale:true}],
      dataZoom:[{type:'inside',...zoom?.[0]},{type:'slider',height:18,bottom:8,...zoom?.[1]}],series:[
      {name:barName,type:'bar',data:rows.map(r=>({value:r[barKey],itemStyle:{color:r[barKey]>=0?'#b95145':'#24816a'}}))},
      {name:lineName,type:'line',yAxisIndex:1,showSymbol:false,connectNulls:false,lineStyle:{color:'#365d86',width:2},itemStyle:{color:'#365d86'},data:rows.map(r=>r[lineKey])}]},true);
  }
  function indexName(code){return data.facts.funds[code]?.indexName||data.funds.funds[code]?.benchmark||'';}
  function peers(code){const name=indexName(code);return fundEntries().filter(([c])=>name&&indexName(c)===name);}
  function renderFund(){
    const f=data.funds.funds[selected];if(!f)return;
    const r=f.daily.at(-1),fact=data.facts.funds[selected],mr=data.margin.details[selected];
    $('fundName').textContent=f.name;$('fundCode').textContent=selected;$('fundSearch').value=selected;
    $('fundMeta').textContent=`${f.groups.join(' / ')} · 上市 ${f.listed} · 数据截至 ${r.date} · 跟踪 ${indexName(selected)||'资料待补'}`;
    const actions=data.funds.actions?.[selected]||[];
    $('fundActions').hidden=!actions.length;$('fundActions').innerHTML=actions.map(a=>`${esc(a.date)}：${esc(a.note)} <a href="${esc(a.source)}" target="_blank" rel="noopener">核实公告</a>`).join('<br>');
    $('fundMetrics').innerHTML=[['净申赎',signed(r.flow),'亿元'],['基金规模',fmt(r.aum),'亿元'],['收盘折溢价',signed(r.premium),'%']].map(([a,b,c])=>`<div><h2>${a}</h2><p><strong>${b}</strong> ${c}</p><small>${r.date}</small></div>`).join('');
    const absent=['close','amount','nav'].filter(k=>r[k]===null);
    $('fundMissing').hidden=!absent.length;$('fundMissing').textContent='该日存在未披露或未获取字段，相关指标显示“—”。净值缺失时，只有交易所确认相邻份额完全不变，净申赎才记零；规模和折溢价不沿用旧值。';
    plot('fundChart',f.daily,'flow','aum','日度净申赎','基金规模');
    $('fundMarginWrap').hidden=!mr;if(mr)plot('fundMarginChart',mr,'net','balance','融资净买入','融资余额');
    const peer=peers(selected).sort((a,b)=>(b[1].daily.at(-1).amount??-1)-(a[1].daily.at(-1).amount??-1));
    $('peerMeta').textContent=`${indexName(selected)||'跟踪标的资料待补'} · 本看板收录 ${peer.length} 只同标的基金。费率为年费率，按各行资料核对日期显示。${mr?'':'该基金不在当前两融明细覆盖内，不代表融资额为零。'}`;
    $('peerTable').innerHTML=table(['代码','名称','数据日','规模（亿）','成交额（亿）','净申赎（亿）','收盘折溢价','管理费/年','托管费/年','资料核对'],peer.map(([code,v])=>{const a=v.daily.at(-1),b=data.facts.funds[code];return `<tr><td>${code}</td><td>${link(code,v.name)}</td><td>${a.date}</td><td class="num">${fmt(a.aum)}</td><td class="num">${fmt(a.amount)}</td>${cell(a.flow)}<td class="num">${fmt(a.premium)}%</td><td class="num">${fmt(b?.managementFee)}%</td><td class="num">${fmt(b?.custodyFee)}%</td><td>${esc(b?.checkedAt.slice(0,10)||'待补')}</td></tr>`;}));
    $('fundDaily').innerHTML=table(['日期','收盘价','单位净值','份额（亿份）','规模（亿）','成交额（亿）','净申赎（亿）','收盘折溢价'],[...f.daily].reverse().map(a=>`<tr><td>${a.date}</td><td class="num">${fmt(a.close,3)}</td><td class="num">${fmt(a.nav,4)}</td><td class="num">${fmt(a.shares,6)}</td><td class="num">${fmt(a.aum,4)}</td><td class="num">${fmt(a.amount,4)}</td>${cell(a.flow)}<td class="num">${fmt(a.premium)}%</td></tr>`));
  }
  function choose(code,scroll=true){
    if(!data.funds.funds[code])return;
    if(selected!==code){for(const id of ['fundChart','fundMarginChart']){charts[id]?.dispose();delete charts[id];}}
    selected=code;renderFund();if(scroll)$('fundDetail').scrollIntoView({behavior:'smooth',block:'start'});
  }
  function renderRotation(){
    const date=$('rotationDate').value,k=$('rotationKind').value,p=$('rotationPeriod').value,query=$('rotationSearch').value.trim();
    const rows=data.rotation.archives[date][k][p].filter(r=>r.name.includes(query)).sort((a,b)=>b.net-a.net);
    const last=rows.reduce((d,r)=>r.date>d?r.date:d,'');
    $('rotationMeta').textContent=`归档 ${date} · ${p} 日融资净买入 · ${rows.length} 项 · 统计最新截止 ${last||'—'}；较旧分类按各行日期判断。`;
    $('rotationTable').innerHTML=table(['排名','板块','统计截止日','融资净买入（亿）','融资余额（亿）'],rows.map((r,i)=>`<tr><td>${i+1}</td><td>${esc(r.name)}</td><td>${r.date}${r.date<last?' · 较旧':''}</td>${cell(r.net)}<td class="num">${fmt(r.balance)}</td></tr>`));
  }
  function render(){
    const x=scrollX,y=scrollY,oldDate=$('rotationDate').value,dates=Object.keys(data.rotation.archives).sort().reverse();
    $('rotationDate').innerHTML=dates.map(d=>`<option>${d}</option>`).join('');
    if(dates.includes(oldDate))$('rotationDate').value=oldDate;
    $('fundOptions').innerHTML=fundEntries().map(([c,f])=>`<option value="${c}">${esc(f.name)}</option>`).join('');
    renderRank();renderHeat();renderFund();renderRotation();scrollTo(x,y);
  }
  async function refresh(){
    if(busy||document.hidden)return;busy=true;
    try{
      const m=await VerifiedData.manifest(),key=names.map(n=>m.files[n]).join('|');
      if(key!==version){
        const b=await VerifiedData.bundle(names,m);validate(b);
        data={funds:b['funds.json'],facts:b['fund-facts.json'],margin:b['etf-margin.json'],themes:b['themes.json'],rotation:b['rotation.json']};
        lookups=Object.fromEntries(fundEntries().map(([c,f])=>[c,Object.fromEntries(f.daily.map(r=>[r.date,r]))]));
        render();version=key;
      }
      $('researchStatus').textContent=`${Object.keys(data.funds.funds).length} 只 ETF · 日度截至 ${data.funds.dates.at(-1)} · 页面已核对发布版本（${new Date().toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai'})}）`;
    }catch(e){$('researchStatus').textContent='新数据未加载，保留现有画面：'+e.message;}finally{busy=false;}
  }
  for(const id of ['rankScope','rankPeriod','rankOrder'])$(id).addEventListener('change',()=>data&&renderRank());
  $('rankSearch').addEventListener('input',()=>data&&renderRank());
  for(const id of ['rotationKind','rotationPeriod','rotationDate'])$(id).addEventListener('change',()=>data&&renderRotation());
  $('rotationSearch').addEventListener('input',()=>data&&renderRotation());
  function searchFund(){if(!data)return;const s=$('fundSearch').value.trim(),f=fundEntries().find(([c,v])=>c===s||v.name===s);if(f)choose(f[0],false);else $('fundMeta').textContent='未找到收录的基金，请选择下拉提示中的代码。';}
  $('openFund').addEventListener('click',searchFund);$('fundSearch').addEventListener('keydown',e=>{if(e.key==='Enter')searchFund();});
  document.addEventListener('click',e=>{const a=e.target.closest('[data-fund]');if(a)choose(a.dataset.fund);});
  addEventListener('resize',()=>Object.values(charts).forEach(c=>c.resize()));addEventListener('online',refresh);document.addEventListener('visibilitychange',refresh);
  setInterval(refresh,60000);refresh();
  window.ETFResearch={refresh,rankings,windowSum,groupFlow,peers,getData:()=>data,choose};
})();

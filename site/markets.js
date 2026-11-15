/* 公开资金模块：发布版本校验、历史无刷新更新、所选主题分时。 */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const files = ['etf-margin.json', 'leverage.json', 'themes.json', 'market-status.json'];
  const charts = new Map();
  const colors = ['#186453', '#b34e41', '#327fba', '#b38329'];
  let data, version = '', loading = false, selectedTheme = '芯片', live = null, liveTask = 0;
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = (v, digits=2) => Number.isFinite(v) ? v.toLocaleString('zh-CN', {minimumFractionDigits:digits, maximumFractionDigits:digits}) : '—';
  const last = rows => rows.at(-1);
  const clock = () => new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit'}).format(new Date());
  const table = (headers, rows) => '<table><thead><tr>' + headers.map(h=>'<th>'+esc(h)+'</th>').join('') + '</tr></thead><tbody>' + rows.map(r=>'<tr>'+r.map((v,i)=>'<td'+(i?' class="num"':'')+'>'+esc(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table>';
  const cards = rows => rows.map(([title,value,note])=>'<div><h2>'+esc(title)+'</h2><p><strong class="compact">'+esc(value)+'</strong></p><small>'+esc(note)+'</small></div>').join('');

  function chart(id, dates, specs, units=['亿元','亿元']) {
    let c = charts.get(id);
    if (!c) {c=echarts.init($(id)); charts.set(id,c);}
    const existing = c.getOption();
    const option = {
      animation:false, color:colors,
      tooltip:{trigger:'axis',valueFormatter:v=>fmt(v)},
      legend:{type:'scroll',top:3,textStyle:{fontSize:11}},
      grid:{left:12,right:18,top:55,bottom:60,containLabel:true},
      xAxis:{type:'category',data:dates,axisLabel:{fontSize:10},boundaryGap:false},
      yAxis:units.map((name,i)=>({type:'value',name,position:i?'right':'left',scale:true,
        axisLabel:{fontSize:10},splitLine:{show:i===0,lineStyle:{color:'#e6edee'}}})),
      series:specs.map(s=>({name:s.name,type:s.type||'line',yAxisIndex:s.axis||0,
        data:s.values,showSymbol:false,connectNulls:false,lineStyle:{width:1.7,type:s.dashed?'dashed':'solid'},
        ...(s.type==='bar'?{itemStyle:{color:p=>p.value>=0?'#b34e41':'#258667'}}:{})})),
      dataZoom:existing?.dataZoom?.length ? existing.dataZoom : [{type:'inside'},{type:'slider',height:18,bottom:5,start:0,end:100}]
    };
    // 复用图表对象，保留图例选择和缩放，避免自动更新打断阅读。
    if (existing?.legend?.[0]?.selected) option.legend.selected=existing.legend[0].selected;
    c.setOption(option, {replaceMerge:['series','xAxis','yAxis']});
  }

  function assert(condition, message) {if(!condition) throw new Error(message);}
  function series(rows, fields) {
    assert(Array.isArray(rows)&&rows.length,'历史序列为空');
    rows.forEach((r,i)=>{
      assert(/^\d{4}-\d{2}-\d{2}$/.test(r.date)&&(!i||r.date>rows[i-1].date),'日期重复或倒序');
      fields.forEach(f=>assert(r[f]===null||Number.isFinite(r[f]),'数值无效 '+f));
    });
  }
  function validate(next) {
    const {margin,leverage,themes,status}=next;
    assert([margin,leverage,themes].every(d=>d.version===1),'版本格式无效');
    assert(margin.categories.length===4,'两融分类缺失');
    series(margin.daily,[]);
    margin.daily.forEach(r=>margin.categories.forEach(c=>{
      const v=r.categories[c]; assert(v&&v.count>0,'缺少两融分类');
      ['balance','shortBalance','buy','repay','net'].forEach(k=>assert(Number.isFinite(v[k]),'两融字段无效'));
      assert(Math.abs(v.buy-v.repay-v.net)<0.00001,'两融恒等式失败');
    }));
    series(leverage.daily,['balance','shortBalance','buy','repay','net','shBalance','szBalance','index','balanceFloatRatio']);
    series(leverage.accounts,['guarantee','guaranteeRatio','activity','participants','debtors','balance','cashCollateral']);
    assert(leverage.industries.length>0,'缺少行业快照');
    leverage.industries.forEach(r=>assert(Number.isFinite(r.balance)&&Number.isFinite(r.net)&&r.name,'行业字段无效'));
    assert(themes.groups.length===13&&themes.times.length===48,'主题分类或时间轴缺失');
    series(themes.calendar.map(date=>({date})),[]);
    themes.groups.forEach(g=>{
      assert(g.members.length>0&&g.members.some(m=>m.code===g.representative),'主题成分无效');
      themes.calendar.forEach(d=>{
        const r=themes.history[g.name]?.[d];
        assert(r&&r.count>=0&&r.values.length===48,'主题归档缺失');
        assert(r.values.every((v,i)=>Number.isFinite(v)&&v>=0&&(!i||v>=r.values[i-1])),'主题累计额无效');
      });
    });
    assert(status.modules&&status.checkedAt,'缺少更新状态');
    if(data) {
      assert(last(margin.daily).date>=last(data.margin.daily).date&&last(leverage.daily).date>=last(data.leverage.daily).date&&last(themes.calendar)>=last(data.themes.calendar),'拒绝较旧的数据版本');
      assert(themes.groups.some(g=>g.name===selectedTheme),'所选主题消失');
      const selected=$('themeDate').value;
      assert(selected==='latest'||themes.calendar.includes(selected),'归档缺少所选日期');
    }
  }

  async function fetchText(url) {
    const r=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(30000)});
    if(!r.ok) throw new Error('请求失败 '+r.status);
    return r.text();
  }
  async function verifiedFile(name, hash) {
    assert(/^[a-f0-9]{64}$/.test(hash),'无效文件校验值');
    const text=await fetchText('./'+name+'?v='+hash);
    const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));
    assert(Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('')===hash,'文件尚未同步');
    return JSON.parse(text);
  }
  async function refresh() {
    if(loading||document.hidden) return;
    loading=true;
    try {
      const manifest=JSON.parse(await fetchText('./history-manifest.json?t='+Date.now()));
      assert(/^[a-f0-9]{64}$/.test(manifest.version),'发布版本无效');
      if(version!==manifest.version) {
        const [margin,leverage,themes,status]=await Promise.all(files.map(n=>verifiedFile(n,manifest.files[n])));
        const next={margin,leverage,themes,status}; validate(next);
        const y=scrollY, initial=!data;
        data=next; version=manifest.version;
        render(); scrollTo({top:y,behavior:'instant'});
        if(initial) refreshLive();
      }
      $('marketUpdate').textContent='自动同步已启用 · 每 60 秒检查发布版本 · 最近核对 '+clock();
    } catch(e) {
      $('marketUpdate').textContent=data?'更新暂不可用，保留已显示数据，稍后自动重试。':'数据暂时未能加载，稍后自动重试。';
      console.warn('资金数据更新失败',e);
    } finally {loading=false;}
  }

  function options(select, pairs) {
    const value=select.value;
    select.innerHTML=pairs.map(([v,t])=>'<option value="'+esc(v)+'">'+esc(t)+'</option>').join('');
    if(pairs.some(([v])=>v===value)) select.value=value;
  }
  function render() {
    options($('marginCategory'),data.margin.categories.map(c=>[c,c]));
    options($('themeDate'),[['latest','跟随最新行情'],...data.themes.calendar.slice().reverse().map(d=>[d,d])]);
    renderTheme(); renderMargin(); renderLeverage(); renderIndustry();
    const names={themes:'主题分时',margin:'ETF 两融',leverage:'杠杆资金'};
    $('sourceStatus').textContent='最近采集检查：'+data.status.checkedAt.replace('T',' ').slice(0,19)+'（北京时间）。'+
      Object.entries(data.status.modules).map(([k,v])=>names[k]+'：'+(v.ok?'检查成功':'本次失败，保留最近可用数据')).join('；')+'。';
  }
  function selectedGroup(){return data.themes.groups.find(g=>g.name===selectedTheme);}
  function themeBaseline(themes,name,date) {
    const dates=themes.calendar.filter(d=>d<date).slice(-20);
    return {dates,values:dates.length===20?themes.times.map((_,i)=>dates.reduce((s,d)=>s+themes.history[name][d].values[i],0)/20):null};
  }
  function renderTheme() {
    const t=data.themes, g=selectedGroup(), archiveDate=last(t.calendar);
    $('themeMeta').textContent=t.calendar[0]+'—'+archiveDate+' · '+t.calendar.length+' 个归档交易日 · '+new Set(t.groups.flatMap(g=>g.members.map(m=>m.code))).size+' 只独立 ETF · 历史 5 分钟节点';
    $('themeButtons').innerHTML=t.groups.map(g=>'<button type="button" data-theme="'+esc(g.name)+'" aria-pressed="'+(g.name===selectedTheme)+'">'+esc(g.name)+'<small>'+g.members.length+' 只 · '+fmt(t.history[g.name][archiveDate].values.at(-1))+' 亿</small></button>').join('');
    const pick=$('themeDate').value;
    const current=pick==='latest'&&live?.name===g.name&&live.date>=archiveDate ? live : null;
    const date=current?.date||(pick==='latest'?archiveDate:pick);
    const curve=current?.values||t.history[g.name][date].values;
    const baseline=themeBaseline(t,g.name,date);
    const halted=(t.halts||[]).filter(h=>h.date===date&&g.members.some(m=>m.code===h.code));
    $('themeDefinition').textContent=g.note+' 当前 '+g.members.length+' 只；图示日 '+(current?current.count:t.history[g.name][date].count)+' 只已上市。卡片金额为 '+archiveDate+' 收盘归档。'+(halted.length?' 已核实全天停牌、成交为零：'+halted.map(h=>h.code).join('、')+'。':'');
    const lines=[{name:date+' 累计成交额',values:curve}];
    if(baseline.values) lines.push({name:'此前 20 日同时段均值',values:baseline.values,dashed:true});
    chart('themeChart',t.times,lines,['亿元']);
    const i=curve.findLastIndex(v=>v!==null), base=baseline.values?.[i];
    $('themeCompare').textContent=date+' '+t.times[i]+'：累计 '+fmt(curve[i])+' 亿。'+(base>0?
      '此前 20 日（'+baseline.dates[0]+'—'+last(baseline.dates)+'）同时段均值 '+fmt(base)+' 亿，当前为 '+fmt(curve[i]/base)+' 倍。':
      '此前仅有 '+baseline.dates.length+' 个完整交易日，暂不计算 20 日均值。')+(current?.repPct!==null&&current?.repPct!==undefined?' 代表 ETF '+g.representative+' 涨跌 '+fmt(current.repPct)+'%（并非主题指数）。':'');
    if(!current) $('themeLive').textContent='归档 '+date+' 15:00';
    $('themeMembers').innerHTML=table(['代码','基金名称','标的指数','上市日期'],g.members.map(m=>[m.code,m.name,m.benchmark,m.listed]));
  }
  function trading() {
    const d=new Date(Date.now()+8*3600000), hm=d.getUTCHours()*100+d.getUTCMinutes();
    return d.getUTCDay()>0&&d.getUTCDay()<6&&((hm>=935&&hm<=1131)||(hm>=1305&&hm<=1505));
  }
  async function quote(code) {
    const symbol=(/^[56]/.test(code)?'sh':'sz')+code;
    const payload=JSON.parse(await fetchText('https://web.ifzq.gtimg.cn/appstock/app/day/query?code='+symbol));
    assert(payload.code===0&&payload.data?.[symbol]?.data?.length,'缺少成分行情 '+code);
    const r=payload.data[symbol].data.slice().sort((a,b)=>b.date.localeCompare(a.date))[0];
    const points=new Map(r.data.map(row=>{const [hm,price,,amount]=row.split(/\s+/);return [hm.slice(0,2)+':'+hm.slice(2),{price:Number(price),amount:Number(amount)}];}));
    return {date:r.date.replace(/^(....)(..)(..)$/,'$1-$2-$3'),points,prev:Number(r.prec)};
  }
  async function refreshLive() {
    if(!data||document.hidden||$('themeDate').value!=='latest') return;
    const token=++liveTask, group=selectedGroup(), revision=version;
    $('themeLive').textContent='正在读取 '+group.members.length+' 只成分…';
    $('themeRefresh').disabled=true;
    try {
      const results=new Map(); let cursor=0;
      await Promise.all(Array.from({length:4},async()=>{
        while(cursor<group.members.length) {if(token!==liveTask)return; const code=group.members[cursor++].code; results.set(code,await quote(code));}
      }));
      if(token!==liveTask)return;
      assert(revision===version,'采集期间历史版本已更新，稍后重试');
      assert(results.size===group.members.length,'主题行情不完整');
      const values=[...results.values()], date=values[0].date;
      assert(values.every(v=>v.date===date)&&date>=last(data.themes.calendar),'行情日期不一致或落后于归档');
      const curve=data.themes.times.map(time=>{
        const points=values.map(v=>v.points.get(time));
        return points.every(v=>v&&Number.isFinite(v.amount)&&v.amount>=0)?points.reduce((sum,v)=>sum+v.amount,0)/1e8:null;
      });
      const i=curve.findLastIndex(v=>v!==null); assert(i>=0,'尚无完整 5 分钟节点');
      assert(curve.slice(0,i+1).every((v,j)=>v!==null&&(!j||v>=curve[j-1])),'分时缺口或累计额倒退');
      const rep=results.get(group.representative), price=rep?.points.get(data.themes.times[i])?.price;
      live={name:group.name,date,values:curve,count:results.size,repPct:rep?.prev>0&&price>0?(price/rep.prev-1)*100:null};
      renderTheme(); $('themeLive').textContent='行情 '+date+' '+data.themes.times[i]+' · '+results.size+' 只齐全';
    } catch(e) {
      if(token===liveTask) {$('themeLive').textContent='行情未齐，保留已有曲线 · '+clock(); console.warn('主题行情',e);}
    } finally {if(token===liveTask)$('themeRefresh').disabled=false;}
  }

  function renderMargin() {
    const m=data.margin, cat=$('marginCategory').value, tail=last(m.daily), v=tail.categories[cat];
    $('marginMeta').textContent=m.daily[0].date+'—'+tail.date+' · '+m.daily.length+' 个交易日 · '+cat+' 两融有记录 '+v.count+' 只 / 目录 '+m.members.filter(x=>x.category===cat).length+' 只';
    $('marginMetrics').innerHTML=cards([['融资余额',fmt(v.balance)+' 亿',tail.date],['融资净买入',fmt(v.net)+' 亿','买入 '+fmt(v.buy)+' / 偿还 '+fmt(v.repay)],['融券余额',fmt(v.shortBalance)+' 亿',v.count+' 只公开标的记录']]);
    const dates=m.daily.map(r=>r.date), values=k=>m.daily.map(r=>r.categories[cat][k]);
    chart('marginBalance',dates,[{name:'融资余额',values:values('balance')},{name:'融券余额（右轴）',values:values('shortBalance'),axis:1}]);
    const flows=new Map(m.flow.map(r=>[r.date,r[cat]]));
    chart('marginNet',dates,[{name:'融资净买入',values:values('net'),type:'bar'},{name:'全类别 ETF 净申赎',values:dates.map(d=>flows.get(d)??null),axis:1}],['两融净买入（亿）','净申赎（亿）']);
    $('marginTable').innerHTML=table(['日期','融资余额','融资买入','融资偿还','融资净买入','融券余额','记录数'],m.daily.slice(-22).reverse().map(r=>{
      const c=r.categories[cat];return [r.date,...['balance','buy','repay','net','shortBalance'].map(k=>fmt(c[k])),c.count];
    }));
    $('marginMembers').textContent='末日有记录的 '+cat+' ETF：'+m.members.filter(r=>r.category===cat&&m.reportedCodes.includes(r.code)).map(r=>r.code+' '+r.name).join('；')+'。无记录的基金不假定为零余额。';
  }

  function aggregate(rows, frequency) {
    if(frequency==='day')return rows;
    const groups=new Map();
    rows.forEach(r=>{
      const d=new Date(r.date+'T00:00:00Z');
      if(frequency==='week')d.setUTCDate(d.getUTCDate()-((d.getUTCDay()+6)%7));
      const key=frequency==='month'?r.date.slice(0,7):d.toISOString().slice(0,10);
      if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r);
    });
    return [...groups.values()].map(group=>{
      const r={...last(group)};
      ['net','buy','repay'].forEach(k=>r[k]=group.every(v=>Number.isFinite(v[k]))?group.reduce((s,v)=>s+v[k],0):null);
      ['activity','balanceFloatRatio','guaranteeRatio'].forEach(k=>r[k]=group.every(v=>Number.isFinite(v[k]))?group.reduce((s,v)=>s+v[k],0)/group.length:null);
      return r;
    });
  }
  function average(values,n) {
    if(n===1)return values;
    return values.map((_,i)=>{const p=values.slice(Math.max(0,i-n+1),i+1);return p.length===n&&p.every(Number.isFinite)?p.reduce((a,b)=>a+b,0)/n:null;});
  }
  function renderLeverage() {
    const l=data.leverage, a=new Map(l.accounts.map(r=>[r.date,r]));
    const all=l.daily.map(r=>({...r,...Object.fromEntries(['guarantee','guaranteeRatio','activity','participants','debtors'].map(k=>[k,a.get(r.date)?.[k]??null]))}));
    const range=$('levRange').value, frequency=$('levFrequency').value, n=Number($('levAverage').value);
    // 先按全历史计算均线，再截取可视区间，避免每次切区间丢掉均线预热数据。
    const grouped=aggregate(all,frequency), min=range==='all'?all[0].date:all[Math.max(0,all.length-Number(range))].date;
    const index=grouped.findIndex(r=>r.date>=min), rows=grouped.slice(index), dates=rows.map(r=>r.date);
    const values=k=>average(grouped.map(r=>r[k]),n).slice(index);
    const tail=last(l.daily), acc=last(l.accounts);
    $('leverageMeta').textContent=l.scope+' · '+l.daily[0].date+'—'+tail.date+'（'+l.daily.length+' 日）。账户指标 '+l.accounts[0].date+'—'+acc.date+'；早期缺项留空。沪市最新 '+l.marketLatest['007']+'，深市最新 '+l.marketLatest['001']+'。';
    $('leverageMetrics').innerHTML=cards([['沪深融资余额',fmt(tail.balance)+' 亿',tail.date+' 完整汇总'],['融资净买入',fmt(tail.net)+' 亿',tail.date],['维持担保比例',fmt(acc.guaranteeRatio)+'%',acc.date+' 账户统计']]);
    chart('levBalance',dates,[{name:'融资余额',values:values('balance')},{name:'融资净买入（右轴）',values:values('net'),axis:1,type:'bar'}]);
    chart('levMarkets',dates,[{name:'沪市融资余额',values:values('shBalance')},{name:'深市融资余额',values:values('szBalance')}],['亿元']);
    chart('levActivity',dates,[{name:'两融交易额占成交额比',values:values('activity')},{name:'融资余额占流通市值比',values:values('balanceFloatRatio')}],['%']);
    chart('levGuarantee',dates,[{name:'担保物总价值',values:values('guarantee')},{name:'维持担保比例（右轴）',values:values('guaranteeRatio'),axis:1}],['亿元','%']);
    chart('levAccounts',dates,[{name:'参与交易投资者',values:values('participants').map(v=>v===null?null:v/10000)},{name:'有负债投资者',values:values('debtors').map(v=>v===null?null:v/10000)}],['万人']);
  }
  function renderIndustry() {
    const l=data.leverage, key=$('industrySort').value, search=$('industrySearch').value.trim();
    $('industryMeta').textContent='源日期 '+l.industries[0].date+' · 东方财富行业 '+l.industries.length+' 项。'+(l.industryComplete?'沪深同日汇总已齐全。':'该日沪深汇总尚未齐全，以下为暂定快照，可能继续变化；不用于计算市场合计。')+'公开接口仅提供最新快照。';
    $('industryMeta').classList.toggle('up',!l.industryComplete);
    const rows=l.industries.filter(r=>r.name.includes(search)).slice().sort((a,b)=>b[key]-a[key]);
    $('industryTable').innerHTML=table(['行业','融资余额（亿）','融资净买入（亿）'],rows.map(r=>[r.name,fmt(r.balance),fmt(r.net)]));
  }

  $('themeButtons').addEventListener('click',e=>{const b=e.target.closest('button[data-theme]');if(!b||!data)return; selectedTheme=b.dataset.theme;liveTask++;live=null;renderTheme();refreshLive();});
  $('themeDate').addEventListener('change',()=>{liveTask++;$('themeRefresh').disabled=false;renderTheme();refreshLive();});
  $('themeRefresh').addEventListener('click',refreshLive);
  $('marginCategory').addEventListener('change',()=>data&&renderMargin());
  ['levRange','levFrequency','levAverage'].forEach(id=>$(id).addEventListener('change',()=>data&&renderLeverage()));
  $('industrySort').addEventListener('change',()=>data&&renderIndustry());
  $('industrySearch').addEventListener('input',()=>data&&renderIndustry());
  window.addEventListener('resize',()=>charts.forEach(c=>c.resize()));
  const wake=()=>{refresh();if(trading())refreshLive();};
  document.addEventListener('visibilitychange',wake);window.addEventListener('focus',wake);window.addEventListener('online',wake);
  setInterval(wake,60000);refresh();
  window.MarketBoard={validate,themeBaseline,aggregate,average,refresh,getData:()=>data};
})();

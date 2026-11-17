/* 数据的披露日期与网页轮询时间分开显示；旧页面每分钟自动获取新校验结果。 */
(() => {
  const host=document.getElementById('dataHealth');if(!host)return;
  const names={daily:'重点 20 只日度',broad:'12 类宽基',minute:'历史分钟',themes:'13 类主题分时',funds:'逐只 ETF 档案',margin:'ETF 两融',leverage:'沪深杠杆',rotation:'行业 / 概念融资',facts:'基金费率资料'};
  let version='',busy=false,last;
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function render(x) {
    const age=Date.now()-Date.parse(x.checkedAt),stale=age>36*3600000;
    const problematic=Object.values(x.modules).filter(s=>!s.ok||s.lag||s.warnings?.length);
    const status=stale?'自动任务超过 36 小时未完成检查':problematic.length?`${problematic.length} 个模块有提示`:'发布前校验通过';
    host.classList.toggle('health-warning',stale||problematic.length>0);
    host.innerHTML=`<details ${stale?'open':''}><summary><span class="health-dot"></span>${esc(status)}<small>查看数据日期与检查结果</small></summary><p class="sub">最近检查 ${esc(x.checkedAt.replace('T',' ').slice(0,19))} 北京时间。每天 08:50、16:10、20:50 尝试更新；页面每 60 秒检查已发布版本。</p>${stale?'<p class="health-error">自动更新心跳超时，当前展示的是最近有效数据。</p>':''}${x.calendar.error?'<p class="health-error">交易日历获取失败，预期日期沿用旧记录。</p>':''}<div class="tscroll"><table><thead><tr><th>模块</th><th>数据日期</th><th>预期日期</th><th>状态</th><th>校验数值</th></tr></thead><tbody>${Object.entries(x.modules).map(([k,s])=>`<tr><td>${names[k]||esc(k)}</td><td>${esc(s.latest)}</td><td>${esc(s.expected)}</td><td>${!s.ok?`<span class="health-error">${s.failureType==='validation'?'校验失败，已拦截':'采集失败，保留旧数据'}</span>`:s.freshness==='等待披露'?'等待披露（08:50 后复查）':s.lag?`<span class="health-error">滞后 ${s.lag} ${k==='facts'?'天':'个交易日'}</span>`:'通过'}${s.warnings?.length?' · 有备注':''}</td><td class="num">${Number(s.validation?.checkedValues||0).toLocaleString()}</td></tr>`).join('')}</tbody></table></div>${Object.entries(x.modules).filter(([,s])=>s.error||s.warnings?.length).map(([k,s])=>`<p class="sub"><b>${names[k]}</b>：${esc([s.error,...s.warnings||[]].filter(Boolean).join('；'))}</p>`).join('')}<p class="sub">检查包括日期、成分覆盖、缺失值、份额与净值复算、分时与日线对账、两融交易所逐只核对。异常候选不能覆盖有效数据。<a href="./data-quality.json">完整校验记录</a> · <a href="https://github.com/risingwen/etf-fund-flow-board/actions">自动任务状态</a></p></details>`;
  }
  async function refresh() {
    if(busy||document.hidden)return;busy=true;
    try {
      const m=await VerifiedData.manifest();
      if(m.files['data-quality.json']!==version){
        const x=await VerifiedData.file('data-quality.json',m.files['data-quality.json']);
        if(x.version!==1||!x.modules||!x.checkedAt)throw Error('校验报告格式无效');
        const open=host.querySelector('details')?.open;last=x;render(x);if(open)host.querySelector('details').open=true;
        version=m.files['data-quality.json'];
      } else if(last&&Date.now()-Date.parse(last.checkedAt)>36*3600000)render(last);
      host.querySelector('.health-network')?.remove();
    }catch(e){
      if(!host.querySelector('.health-network')){const p=document.createElement('p');p.className='health-network sub';p.textContent='校验状态暂时无法更新，保留现有数据：'+e.message;host.appendChild(p);}
    }finally{busy=false;}
  }
  refresh();setInterval(refresh,60000);addEventListener('online',refresh);document.addEventListener('visibilitychange',refresh);
  window.DataHealth={refresh};
})();

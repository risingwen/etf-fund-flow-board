(function () {
  "use strict";
  var D = window.__DATA;
  if (!D) { document.getElementById("tagUpdate").textContent = "数据未加载"; return; }
  var BASKET = D.meta.basket;
  function $(id) { return document.getElementById(id); }
  function fmt(v, n) { return v === null || v === undefined ? "--" : Number(v).toFixed(n === undefined ? 2 : n); }
  var charts = [];
  function mk(id) { var c = echarts.init($(id)); charts.push(c); return c; }
  window.addEventListener("resize", function () { charts.forEach(function (c) { if (c.getDom().clientWidth) c.resize(); }); });

  /* ---------- 第一部分：分钟 ---------- */
  var SLOTS = D.init.times;
  function minuteOption(bars, closes, preClose) {
    return {
      title: { text: "分钟成交额与上证综指", textStyle: { fontSize: 14, color: "#12355c" } },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { data: ["分钟成交额(亿)", "上证综指"], top: 26, left: 0, textStyle: { fontSize: 12 } },
      grid: { left: 58, right: 64, top: 88, bottom: 30 },
      xAxis: { type: "category", data: SLOTS, axisLabel: { interval: 29, hideOverlap: true, fontSize: 11 } },
      yAxis: [
        { type: "value", name: "亿元", nameGap: 14, nameTextStyle: { align: "left", padding: [0, 0, 6, 0] }, min: 0 },
        { type: "value", name: "上证(点)", scale: true,
          min: preClose ? ({min}) => Math.floor(Math.min(min, preClose)) : undefined,
          max: preClose ? ({max}) => Math.ceil(Math.max(max, preClose)) : undefined,
          nameGap: 14, nameTextStyle: { align: "right", padding: [0, 0, 6, 0] } }
      ],
      series: [
        { name: "分钟成交额(亿)", type: "bar", data: bars, itemStyle: { color: "#24507e" } },
        { name: "上证综指", type: "line", yAxisIndex: 1, data: closes, showSymbol: false,
          lineStyle: { width: 1.6, color: "#c0392b" },
          markLine: preClose ? { silent: true, symbol: "none", lineStyle: { type: "dashed", color: "#888" },
            label: { position: "insideEndBottom", distance: 4, formatter: "昨收 " + preClose }, data: [{ yAxis: preClose }] } : undefined }
      ]
    };
  }
  var chMin = mk("chartMin");
  chMin.setOption(minuteOption(D.init.bars, D.init.closes, D.init.preClose));

  const updateComparison = ETFMinuteHistory.mount(mk("chartCum"), BASKET, SLOTS, {date: D.init.date, cum: D.cum});
  $("tagDate").textContent = "分钟数据日：" + D.init.date;

  function typOption(title, amt, idx) {
    return {
      title: { text: title, textStyle: { fontSize: 13, color: "#12355c" } },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 54, right: 58, top: 56, bottom: 26 },
      xAxis: { type: "category", data: D.typ.slots, axisLabel: { interval: 39, hideOverlap: true, fontSize: 11 } },
      yAxis: [ { type: "value", name: "亿/分钟", nameGap: 12, nameTextStyle: { padding: [0, 0, 6, 0] }, min: 0 }, { type: "value", name: "指数%", scale: true, nameGap: 12, nameTextStyle: { padding: [0, 0, 6, 0] } } ],
      series: [
        { name: "平均分钟成交额", type: "bar", data: amt, itemStyle: { color: "#7fa6c9" } },
        { name: "上证相对开盘%", type: "line", yAxisIndex: 1, data: idx, showSymbol: false, lineStyle: { width: 1.4, color: "#c0392b" } }
      ]
    };
  }
  var typNote = D.typ.mode.indexOf("netflow>100") === 0 ? "净流入>100亿日" : "窗口内净流入居前日（窗口无>100亿日时的替代分组）";
  $("typMeta").textContent = typNote + "：" + D.typ.supDays.join("、") + "。对照日期：" + D.typ.norDays.join("、") + "。";
  let samplesReady = false;
  document.querySelector(".samples").addEventListener("toggle", function () {
    if (!this.open) return;
    if (!samplesReady) {
      mk("chartTypSup").setOption(typOption("放量样本日均值（" + D.typ.supDays.length + " 日）", D.typ.supAmt, D.typ.supIdx));
      mk("chartTypNor").setOption(typOption("常态日均值（" + D.typ.norDays.length + " 日）", D.typ.norAmt, D.typ.norIdx));
      samplesReady = true;
    }
    charts.forEach(c => c.resize());
  });

  function renderTable(table) {
    var total = table.reduce(function (s, r) { return s + (r.amount || 0); }, 0);
    var max = Math.max.apply(null, table.map(function (r) { return r.amount || 0; }));
    $("etfTable").innerHTML = table.map(function (r) {
      var cls = r.pct === null ? "" : (r.pct >= 0 ? "up" : "down");
      var pct = r.pct === null ? "--" : (r.pct >= 0 ? "+" : "") + fmt(r.pct) + "%";
      var share = total ? (r.amount / total * 100).toFixed(1) + "%" : "--";
      var w = max ? (r.amount / max * 100).toFixed(1) : 0;
      return "<tr><td>" + r.code + "</td><td>" + r.name + "</td>" +
        "<td class='num'><div class='bar-bg' style='width:" + w + "%'></div><span class='v'>" + fmt(r.amount) + "</span></td>" +
        "<td class='num'>" + share + "</td><td class='num " + cls + "'>" + pct + "</td></tr>";
    }).join("");
  }
  renderTable(D.init.table);
  $("tagUpdate").textContent = "静态数据生成于 " + D.meta.generated;

  let paused = false, loading = false;
  let displayed = D.init.date + " " + (SLOTS[D.init.bars.findLastIndex(v => v !== null)] || "");
  function summary(amount, close, dateTime) {
    $("summaryAmount").textContent = fmt(amount);
    $("summaryIndex").textContent = fmt(close);
    $("amountTime").textContent = $("indexTime").textContent = dateTime;
  }
  const lastSlot = D.init.bars.findLastIndex(v => v !== null);
  summary(D.cum.today[lastSlot], D.init.closes[lastSlot], displayed);
  $("tagDate").textContent = "分钟行情 · " + displayed;
  async function refresh() {
    if (loading) return;
    loading = true;
    $("btnRefresh").disabled = true;
    $("tagUpdate").textContent = "正在读取分钟行情…";
    try {
      const live = await ETFQuotes.load(BASKET, SLOTS);
      const stamp = live.date + " " + live.time;
      if (stamp < displayed) throw new Error("行情时间早于当前画面");
      chMin.setOption(minuteOption(live.bars, live.closes, live.preClose), true);
      updateComparison(live);
      renderTable(live.table);
      const i = SLOTS.indexOf(live.time);
      summary(live.cum.today[i], live.closes[i], stamp);
      displayed = stamp;
      $("tagDate").textContent = "分钟行情 · " + stamp;
      $("tagUpdate").textContent = "腾讯行情 · " + BASKET.length + " 只齐全";
    } catch (error) {
      $("tagUpdate").textContent = "刷新未完成，保留 " + displayed + " 行情";
      console.warn("分钟行情刷新失败", error);
    } finally {
      loading = false;
      $("btnRefresh").disabled = false;
    }
  }
  $("btnRefresh").addEventListener("click", refresh);
  $("btnPause").addEventListener("click", function () {
    paused = !paused;
    this.textContent = paused ? "恢复自动刷新" : "暂停自动刷新";
    this.setAttribute("aria-pressed", String(paused));
  });
  if (location.protocol.startsWith("http")) {
    refresh();
    setInterval(() => { if (!document.hidden && !paused && ETFQuotes.isTrading()) refresh(); }, 60000);
  }

  /* ---------- 第二部分：托底信号 ---------- */
  var sup = D.support, rec = D.recent;
  $("tagSupCount").textContent = "托底日共 " + sup.length + " 天（合计净流入>100亿）";
  var lastNf = null; for (var i = D.daily.netflow.length - 1; i >= 0; i--) { if (D.daily.netflow[i] !== null) { lastNf = { d: D.daily.dates[i], v: D.daily.netflow[i] }; break; } }
  $("tagLatest").textContent = "最新净流入：" + (lastNf ? lastNf.d + " · " + fmt(lastNf.v) + " 亿" : "--");
  $("summaryFlow").textContent = lastNf ? (lastNf.v > 0 ? "+" : "") + fmt(lastNf.v) : "--";
  $("flowTime").textContent = lastNf ? lastNf.d + " 已披露" : "待披露";
  function supChart(id, field, colorSup, title, latestVal) {
    var xs = sup.map(function (r) { return r.date.slice(2); }).concat(rec.map(function (r) { return r.date.slice(2) + "·近"; }));
    var vals = sup.map(function (r) { return { value: r[field], itemStyle: { color: colorSup } }; })
      .concat(rec.map(function (r) { return { value: r[field], itemStyle: { color: "#e8a33d" } }; }));
    var opt = {
      title: { text: title, textStyle: { fontSize: 14, color: "#12355c" } },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 56, right: 28, top: 56, bottom: 56 },
      xAxis: { type: "category", data: xs, axisLabel: { rotate: 38, fontSize: 10.5, interval: "auto" } },
      yAxis: { type: "value", name: "亿元", nameGap: 12, nameTextStyle: { padding: [0, 0, 6, 0] } },
      series: [{ type: "bar", data: vals,
        markLine: latestVal !== null && latestVal !== undefined ? { silent: true, symbol: "none",
          lineStyle: { type: "dashed", color: "#b02a24" }, label: { position: "insideEndTop", distance: 6, formatter: "最新 " + fmt(latestVal) }, data: [{ yAxis: latestVal }] } : undefined }]
    };
    mk(id).setOption(opt);
  }
  supChart("chartSupAmt", "amount", "#24507e", "成交额 · 托底日与近期（黄）", rec.length ? rec[rec.length - 1].amount : null);
  supChart("chartSupNf", "netflow", "#c0392b", "净流入 · 托底日与近期（黄）", lastNf ? lastNf.v : null);

  /* ---------- 第三部分：日度全景 ---------- */
  var dy = D.daily;
  $("dailyMeta").textContent = "区间：" + dy.dates[0] + " ~ " + dy.dates[dy.dates.length - 1] + "（" + dy.dates.length + " 个交易日）｜柱：20只ETF日度成交额 / 净流入（申赎口径）｜线：上证综指收盘";
  function dailyChart(id, field, title, colorFn) {
    var data = dy[field].map(function (v, i) {
      return { value: v, itemStyle: { color: colorFn ? colorFn(v) : "#24507e" } };
    });
    mk(id).setOption({
      title: { text: title, textStyle: { fontSize: 14, color: "#12355c" } },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { data: ["上证综指"], top: 26, left: 0, textStyle: { fontSize: 12 } },
      grid: { left: 58, right: 62, top: 88, bottom: 64 },
      dataZoom: [{ type: "slider", start: 55 }, { type: "inside" }],
      xAxis: { type: "category", data: dy.dates, axisLabel: { fontSize: 11 } },
      yAxis: [ { type: "value", name: "亿元", nameGap: 14, nameTextStyle: { padding: [0, 0, 6, 0] } }, { type: "value", name: "上证(点)", scale: true, nameGap: 14, nameTextStyle: { padding: [0, 0, 6, 0] } } ],
      series: [
        { name: title, type: "bar", data: data },
        { name: "上证综指", type: "line", yAxisIndex: 1, data: dy.idx, showSymbol: false, lineStyle: { width: 1.2, color: "#666" } }
      ]
    });
  }
  dailyChart("chartDAmt", "amount", "日度成交额（亿元）", null);
  dailyChart("chartDNf", "netflow", "日度净流入（亿元）", function (v) {
    if (v === null || v === undefined) return "#ccc"; if (v > 100) return "#c0392b"; if (v < 0) return "#1e8e4f"; return "#7fa6c9";
  });
})();

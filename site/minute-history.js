// 所选交易日的前 20 个交易日构成唯一的比较窗口。只对齐同一交易分钟。
globalThis.ETFMinuteHistory = (() => {
  const WINDOW = 20;

  function comparison(archive, date, previousDay) {
    const calendar = archive.calendar;
    let end = calendar.indexOf(date);
    if (end < 0) {
      // 最新行情可能领先定时归档。只有行情源确认的前一交易日才能衔接。
      if (date <= calendar.at(-1) || calendar.at(-1) !== previousDay) return {gap: true};
      end = calendar.length;
    }
    const prior = calendar.slice(Math.max(0, end - WINDOW), end);
    const rows = prior.map(day => archive.days[day]).filter(Boolean);
    if (rows.length < WINDOW) return {count: rows.length};
    const mean = archive.times.map((_, i) => rows.reduce((sum, curve) => sum + curve[i], 0) / WINDOW);
    return {count: WINDOW, first: prior[0], last: prior.at(-1), mean};
  }

  function mount(chart, basket, times, snapshot) {
    const get = id => document.getElementById(id);
    const select = get("minuteDate");
    const status = get("minuteStatus");
    const range = get("minuteRange");
    const signal = get("tagS1");
    let archive, failed = false, latest = snapshot;

    function line(name, values, color, width, dashed = false) {
      return {name, type: "line", data: values, showSymbol: false, itemStyle: {color},
        lineStyle: {color, width, type: dashed ? "dashed" : "solid"}};
    }

    function render() {
      const follow = select.value === "latest";
      const archiveEnd = archive?.calendar.at(-1);
      const latestDate = archiveEnd > latest.date ? archiveEnd : latest.date;
      const date = follow ? latestDate : select.value;
      const values = archive?.days[date] ?? latest.cum.today;
      const base = archive ? comparison(archive, date, latest.cum.previousTradingDay) : {};
      const series = [line(date, values, "#ba4233", 2.4)];
      if (base.mean) series.push(line("前20日同时段均值", base.mean, "#24507e", 1.8, true));
      let overlay;
      if (!follow && date < latestDate) {
        overlay = "最新 " + latestDate;
        series.push(line(overlay, archive?.days[latestDate] ?? latest.cum.today, "#aa762c", 1.4));
      } else if (follow && archive) {
        const prev = archive.calendar[archive.calendar.indexOf(date) - 1] ?? latest.cum.previousTradingDay;
        if (archive.days[prev]) series.push(line("前日 " + prev, archive.days[prev], "#aa762c", 1.4));
      }
      const selected = {...chart.getOption()?.legend?.[0]?.selected};
      if (overlay && !(overlay in selected)) selected[overlay] = false;
      chart.setOption({
        tooltip: {trigger: "axis", confine: true, valueFormatter: v => v == null ? "—" : Number(v).toFixed(2) + " 亿"},
        legend: {type: "scroll", top: 2, left: 0, right: 6, textStyle: {fontSize: 12},
          selected},
        grid: {left: 56, right: 18, top: 42, bottom: 30},
        xAxis: {type: "category", boundaryGap: false, data: times,
          axisLabel: {interval: 29, hideOverlap: true, fontSize: 11, showMaxLabel: true}},
        yAxis: {type: "value", min: 0}, series
      }, true);
      const i = values.findLastIndex(Number.isFinite);
      const amount = i >= 0 ? date + " " + times[i] + " 累计 " + values[i].toFixed(2) + " 亿元。" : "";
      let details;
      if (base.mean && i >= 0) {
        details = "前 20 日同时段均值 " + base.mean[i].toFixed(2) + " 亿元（" + base.first + " 至 " + base.last + "）。";
      } else if (base.gap) {
        details = "前一交易日尚未归档，待补齐后显示均线。";
      } else if (archive) {
        details = "此前有 " + base.count + " 个完整交易日，距 20 日均线还差 " + (WINDOW - base.count) + " 天。";
      } else {
        details = failed ? "历史归档未能载入，请重新加载页面。" : "正在读取历史归档…";
      }
      status.textContent = amount + details;
      chart.getDom().setAttribute("aria-label", "20 只 ETF 累计成交额。" + status.textContent);
      signal.hidden = true;
      if (base.mean) {
        const ratios = values.flatMap((v, j) => Number.isFinite(v) && base.mean[j] > 0.5 ? [v / base.mean[j]] : []);
        if (ratios.length) {
          const peak = Math.max(...ratios);
          signal.textContent = date + " 盘中累计成交额最高为同时段均值的 " + peak.toFixed(2) + " 倍" +
            (peak >= 2 ? "，触及 2 倍放量线。" : "。");
          signal.className = peak >= 2 ? "tag warn" : "tag";
          signal.hidden = false;
        }
      }
    }

    select.addEventListener("change", render);
    render();
    fetch("./minute-history.json", {signal: AbortSignal.timeout(20000)}).then(async response => {
      if (!response.ok) throw new Error("HTTP " + response.status);
      const data = await response.json();
      const codes = basket.map(row => row.code).sort();
      if (data.version !== 1 || JSON.stringify(codes) !== JSON.stringify(data.codes) ||
          JSON.stringify(times) !== JSON.stringify(data.times) || !data.calendar.length ||
          JSON.stringify(data.calendar) !== JSON.stringify(Object.keys(data.days).sort()) ||
          data.calendar.some(day => data.days[day].length !== times.length)) throw new Error("分钟归档结构不匹配");
      archive = data;
      const dates = archive.calendar;
      for (const date of dates.slice().reverse()) select.add(new Option(date, date));
      select.disabled = false;
      range.textContent = "已归档 " + dates.length + " 个交易日 · " + dates[0] + " 至 " + dates.at(-1);
      render();
    }).catch(error => {
      failed = true;
      range.textContent = "历史归档暂不可用";
      render();
      console.warn("分钟归档加载失败", error);
    });
    return live => { latest = live; render(); };
  }

  return {mount, comparison};
})();

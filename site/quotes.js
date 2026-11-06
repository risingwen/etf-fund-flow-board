// 腾讯五日分时。每条记录依次为时刻、价格、累计成交量、累计成交额（元）。
globalThis.ETFQuotes = (() => {
  const YI = 1e8;
  const rounded = (v, digits) => Number(v.toFixed(digits));

  async function fetchDays(symbol) {
    const url = "https://web.ifzq.gtimg.cn/appstock/app/day/query?code=" + symbol;
    const response = await fetch(url, {signal: AbortSignal.timeout(12000), cache: "no-store"});
    if (!response.ok) throw new Error("行情请求失败 " + symbol);
    const payload = await response.json();
    const records = payload.data?.[symbol]?.data;
    if (payload.code !== 0 || !Array.isArray(records) || !records.length) throw new Error(symbol + " 无分钟数据");
    const days = new Map();
    for (const {date, data, prec} of records) {
      if (!/^\d{8}$/.test(date)) continue;
      const quotes = new Map();
      for (const row of data) {
        const [time, priceText, , amountText] = row.split(/\s+/);
        const price = Number(priceText), amount = Number(amountText);
        if (price > 0 && Number.isFinite(amount) && amount >= 0) {
          quotes.set(time.slice(0, 2) + ":" + time.slice(2), {price, amount});
        }
      }
      if (quotes.size) days.set(date.replace(/^(....)(..)(..)$/, "$1-$2-$3"), {quotes, prev: Number(prec)});
    }
    return days;
  }

  function cumulative(funds, date, times) {
    return times.map(time => {
      let total = 0;
      for (const days of funds) {
        const point = days.get(date)?.quotes.get(time);
        if (!point) return null;
        total += point.amount;
      }
      return total / YI;
    });
  }

  async function load(basket, times) {
    const symbols = basket.map(({code}) => (/^[56]/.test(code) ? "sh" : "sz") + code);
    const results = await Promise.allSettled(["sh000001", ...symbols].map(fetchDays));
    const failures = results.filter(result => result.status === "rejected").length;
    if (failures) throw new Error(failures + " 路行情未返回");
    const [index, ...funds] = results.map(result => result.value);
    const dates = [...index.keys()].sort().reverse();
    const date = dates[0];
    if (!date || funds.some(days => !days.has(date))) throw new Error("成分行情日期未对齐");

    const indexDay = index.get(date);
    const current = cumulative(funds, date, times);
    const last = current.findLastIndex((value, i) => value !== null && indexDay.quotes.has(times[i]));
    if (last < 0) throw new Error("等待首个完整分钟");
    // 全部曲线和成分使用同一个截止时刻。集合竞价计入 09:31；盘后时段排除。
    const time = times[last];
    const today = current.map((value, i) => i > last || value === null ? null : rounded(value, 4));
    const bars = current.map((value, i) => {
      const previous = i === 0 ? 0 : current[i - 1];
      return i > last || value === null || previous === null || value < previous
        ? null : rounded(value - previous, 4);
    });
    const closes = times.map((t, i) => i <= last ? indexDay.quotes.get(t)?.price ?? null : null);
    const history = dates.slice(1).map(day => ({day, values: cumulative(funds, day, times)}))
      .filter(row => row.values.every(v => v !== null));
    const base = times.map((_, i) => history.length
      ? rounded(history.reduce((sum, row) => sum + row.values[i], 0) / history.length, 4) : null);
    const deviations = today.flatMap((v, i) => v !== null && base[i] > 0.5 ? [v / base[i]] : []);
    const peak = deviations.length ? Math.max(...deviations) : null;
    const table = basket.map((item, i) => {
      const day = funds[i].get(date), point = day.quotes.get(time);
      return {...item, amount: point.amount / YI, price: point.price,
        pct: day.prev > 0 ? (point.price / day.prev - 1) * 100 : null};
    }).sort((a, b) => b.amount - a.amount);
    return {date, time, bars, closes, preClose: indexDay.prev, table,
      cum: {times, today, base, prev: history[0]?.values, prevDate: history[0]?.day,
        s1: {devMax: peak === null ? null : rounded(peak, 2), baseDays: history.length, flag: peak >= 2}}};
  }

  function isTrading(now = new Date()) {
    // 上交所和深交所使用北京时间，不受访问者设备时区影响。
    const local = new Date(now.getTime() + 8 * 3600000);
    const day = local.getUTCDay(), hm = local.getUTCHours() * 100 + local.getUTCMinutes();
    return day > 0 && day < 6 && ((hm >= 930 && hm <= 1130) || (hm >= 1300 && hm <= 1501));
  }
  return {load, isTrading};
})();

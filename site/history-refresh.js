// 发布清单只含校验值。全部文件属于同一版本时，才一起更新画面。
(function () {
  "use strict";
  const status = document.getElementById("historyUpdate");
  const files = ["data.js", "broad.js", "minute-history.json"];
  let version = "", loading = false, lastArchiveDay = "";
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  async function fetchText(path) {
    const response = await fetch(path, {cache: "no-store", signal: AbortSignal.timeout(20000)});
    if (!response.ok) throw new Error("历史数据请求失败 " + response.status);
    return response.text();
  }

  async function loadFile(name, hash) {
    if (!/^[a-f0-9]{64}$/.test(hash)) throw new Error("发布清单无效");
    const text = await fetchText("./" + name + "?v=" + hash);
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    const actual = Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, "0")).join("");
    if (actual !== hash) throw new Error("发布中的文件版本尚未一致");
    if (name.endsWith(".json")) return JSON.parse(text);
    const prefix = name === "data.js" ? "window.__DATA = " : "window.__BROAD = ";
    const source = text.trim();
    if (!source.startsWith(prefix) || !source.endsWith(";")) throw new Error("数据文件格式异常");
    return JSON.parse(source.slice(prefix.length, -1));
  }

  function validateSeries(dates, series) {
    if (!Array.isArray(dates) || !dates.length ||
        dates.some((day, i) => !/^\d{4}-\d{2}-\d{2}$/.test(day) || (i > 0 && day <= dates[i - 1])) ||
        series.some(values => !Array.isArray(values) || values.length !== dates.length ||
          values.some(value => value !== null && !Number.isFinite(value)))) {
      throw new Error("历史序列不完整");
    }
  }

  function validate(board, broad, archive) {
    const current = window.__DATA;
    if (!same(board.meta.basket.map(row => row.code), current.meta.basket.map(row => row.code)) ||
        !same(board.init.times, current.init.times)) throw new Error("成分或时间轴变更，请重新打开看板");
    validateSeries(board.daily.dates, ["amount", "netflow", "idx", "nfCov", "amtCov"].map(k => board.daily[k]));
    if (!Array.isArray(board.support) || !Array.isArray(board.recent) || !board.typ) throw new Error("日度数据不完整");
    if (!same(broad.categories, window.__BROAD.categories) ||
        !same(broad.legendOrder, window.__BROAD.legendOrder)) throw new Error("宽基分类结构变更");
    validateSeries(broad.dates, [...broad.categories.map(c => broad.byCategory[c]), broad.cumulative]);
    validateSeries(broad.heat.dates, broad.categories.map(c => broad.heat.byCategory[c]));
    if (broad.meta.dateLast !== broad.dates.at(-1) ||
        !same(broad.heat.dates, broad.dates.slice(-22)) ||
        broad.categories.some(c => !same(broad.heat.byCategory[c], broad.byCategory[c].slice(-22)))) {
      throw new Error("宽基表格与曲线日期不一致");
    }
    ETFMinuteHistory.validate(archive, board.meta.basket, board.init.times);
    if (board.daily.dates.at(-1) < current.daily.dates.at(-1) ||
        broad.dates.at(-1) < window.__BROAD.dates.at(-1) || archive.calendar.at(-1) < lastArchiveDay) {
      throw new Error("收到较早的历史版本");
    }
    const selected = document.getElementById("minuteDate").value;
    if (selected !== "latest" && !archive.days[selected]) throw new Error("归档缺少所选日期");
  }

  async function refresh() {
    if (loading || document.hidden) return;
    loading = true;
    try {
      const manifest = JSON.parse(await fetchText("./history-manifest.json?t=" + Date.now()));
      if (!/^[a-f0-9]{64}$/.test(manifest.version)) throw new Error("发布版本无效");
      if (manifest.version !== version) {
        const [board, broad, archive] = await Promise.all(files.map(name => loadFile(name, manifest.files[name])));
        validate(board, broad, archive);
        const y = window.scrollY;
        ETFBoard.updateHistory(board);
        ETFBroad.updateHistory(broad);
        ETFBoard.updateArchive(archive);
        window.scrollTo({top: y, behavior: "instant"});
        lastArchiveDay = archive.calendar.at(-1);
        version = manifest.version;
      }
      const time = new Intl.DateTimeFormat("zh-CN", {timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit"}).format(new Date());
      status.textContent = "历史数据自动同步 · 每 60 秒检查 · 最近核对 " + time;
    } catch (error) {
      status.textContent = "历史更新暂不可用，稍后自动重试";
      ETFBoard.archiveUnavailable();
      console.warn("历史数据更新失败", error);
    } finally {
      loading = false;
    }
  }

  if (location.protocol.startsWith("http")) {
    refresh();
    setInterval(refresh, 60000);
    document.addEventListener("visibilitychange", refresh);
    window.addEventListener("focus", refresh);
    window.addEventListener("online", refresh);
  } else {
    status.textContent = "通过本地 HTTP 服务打开后，可自动同步历史数据";
    ETFBoard.archiveUnavailable();
  }
})();

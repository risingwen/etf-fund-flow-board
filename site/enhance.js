/* ============================================================
   增强层：图表导出 / 十字准星 / 表格排序 / 回到顶部
   以叠加方式工作，不改动各页原有渲染逻辑
   ============================================================ */
(function () {
  "use strict";

  // 等业务脚本绑定 toggle 后再展开，首次显示时两张图即可初始化。
  document.addEventListener("DOMContentLoaded", function () {
    var samples = document.querySelector("details.samples");
    if (samples) samples.open = true;
  });

  /* ---------- 1. 图表增强：导出 PNG + 十字准星 ---------- */
  function patchECharts() {
    if (!window.echarts || window.echarts.__enhanced) return;
    var origInit = window.echarts.init;
    window.echarts.init = function (dom, theme, opts) {
      var inst = origInit.call(window.echarts, dom, theme, opts);
      if (inst && !inst.__enhanced) {
        inst.__enhanced = true;
        var origSet = inst.setOption.bind(inst);
        inst.setOption = function (option, notMerge) {
          try {
            if (option && typeof option === "object" && !option.__enhanced) {
              option.__enhanced = true;

              /* 导出图片 */
              if (!option.toolbox) {
                option.toolbox = {
                  show: true,
                  right: 6,
                  top: 2,
                  itemSize: 13,
                  itemGap: 8,
                  iconStyle: { borderColor: "#8ba0a8", borderWidth: 1 },
                  emphasis: { iconStyle: { borderColor: "#186453" } },
                  feature: {
                    saveAsImage: {
                      title: "保存为图片",
                      name: "etf-chart",
                      pixelRatio: 2,
                      backgroundColor: "#ffffff"
                    }
                  }
                };
              }

              /* 十字准星：只对坐标轴触发的 tooltip 生效 */
              if (option.tooltip && option.tooltip.trigger === "axis") {
                option.tooltip.axisPointer = Object.assign({
                  type: "cross",
                  crossStyle: { color: "#9fb0b6", width: 1, type: "dashed" },
                  label: { backgroundColor: "#4a6068" }
                }, option.tooltip.axisPointer || {});
              }
            }
          } catch (e) { /* 增强失败不影响原图 */ }
          return origSet(option, notMerge);
        };
      }
      return inst;
    };
    window.echarts.__enhanced = true;
  }

  /* ECharts 是 defer 加载，等它出现再打补丁 */
  if (window.echarts) patchECharts();
  else {
    var tries = 0;
    var timer = setInterval(function () {
      if (window.echarts) { clearInterval(timer); patchECharts(); }
      else if (++tries > 200) clearInterval(timer);
    }, 30);
  }

  /* ---------- 2. 表格点击表头排序 ---------- */
  function cellValue(tr, idx) {
    var cell = tr.cells[idx];
    if (!cell) return "";
    var text = (cell.innerText || "").trim();
    if (!text) return "";
    var num = parseFloat(text.replace(/[,\s]/g, "").replace(/[^\d.\-+]/g, ""));
    return isNaN(num) ? text : num;
  }

  function sortTable(table, th, idx) {
    var tbody = table.tBodies[0];
    if (!tbody || tbody.rows.length < 2) return;
    var dir = th.getAttribute("data-sort") === "asc" ? -1 : 1;

    Array.prototype.forEach.call(table.querySelectorAll("thead th"), function (h) {
      h.removeAttribute("data-sort");
      h.removeAttribute("aria-sort");
    });
    th.setAttribute("data-sort", dir === 1 ? "asc" : "desc");
    th.setAttribute("aria-sort", dir === 1 ? "ascending" : "descending");

    var rows = Array.prototype.slice.call(tbody.rows);
    rows.sort(function (a, b) {
      var x = cellValue(a, idx), y = cellValue(b, idx);
      var xNum = typeof x === "number", yNum = typeof y === "number";
      if (xNum && yNum) return (x - y) * dir;
      if (xNum !== yNum) return xNum ? -1 : 1;          // 有数字的排前面
      return String(x).localeCompare(String(y), "zh-Hans-CN") * dir;
    });
    rows.forEach(function (r) { tbody.appendChild(r); });
  }

  function markSortable() {
    document.querySelectorAll("table").forEach(function (table) {
      var thead = table.tHead;
      if (!thead || !table.tBodies[0]) return;
      Array.prototype.forEach.call(thead.rows[0].cells, function (th) {
        if (th.hasAttribute("data-no-sort") || th.colSpan > 1 || th.hasAttribute("data-sortable")) return;
        th.setAttribute("data-sortable", "1");
        th.setAttribute("title", (th.innerText || "").trim() + " · 点击排序");
      });
    });
  }

  document.addEventListener("click", function (e) {
    var th = e.target.closest && e.target.closest("th[data-sortable]");
    if (!th) return;
    var table = th.closest("table");
    if (!table) return;
    var idx = Array.prototype.indexOf.call(th.parentNode.cells, th);
    if (idx < 0) return;
    sortTable(table, th, idx);
  });

  /* 表格会被各处 innerHTML 重写，定期补标记（轻量，只处理未标记的表） */
  markSortable();
  setInterval(markSortable, 1500);

  /* ---------- 3. 回到顶部 ---------- */
  var top = document.createElement("button");
  top.type = "button";
  top.className = "enh-top";
  top.setAttribute("aria-label", "回到顶部");
  top.textContent = "↑";
  top.addEventListener("click", function () {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  document.body.appendChild(top);

  var onScroll = function () {
    top.classList.toggle("show", window.scrollY > 640);
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* ---------- 4. 历史分钟：100 个交易日，加「上一个 / 下一个」快捷切换 ---------- */
  function enhanceDatePicker() {
    var sel = document.getElementById("minuteDate");
    if (!sel || sel.__enhDate) return;
    sel.__enhDate = true;
    var isTiny = window.matchMedia("(max-width: 600px)").matches;
    function mkBtn(label, aria, delta) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "enh-nav-btn secondary";
      b.textContent = label;
      b.setAttribute("aria-label", aria);
      b.title = aria;
      b.addEventListener("click", function () {
        var i = sel.selectedIndex + delta;
        if (i < 0 || i >= sel.options.length) return;
        sel.selectedIndex = i;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
      });
      return b;
    }
    /* 选项顺序：latest 在最前，其余从新到旧；所以 ‹ 更早=+1，› 更新=-1 */
    var older = mkBtn(isTiny ? "‹" : "‹ 更早", "上一个交易日", 1);
    var newer = mkBtn(isTiny ? "›" : "更新 ›", "下一个交易日", -1);
    sel.parentNode.insertBefore(older, sel);
    sel.parentNode.insertBefore(newer, sel.nextSibling);
  }

  /* ---------- 5. 托底信号：汇总指标 ---------- */
  function kpi(title, value, note) {
    return '<div><h3>' + title + '</h3><p><strong>' + value + '</strong></p><small>' + note + '</small></div>';
  }
  function addSupportKpis() {
    var D = window.__DATA;
    if (!D || !Array.isArray(D.support) || !D.support.length) return;
    if (document.getElementById("enhSupKpi")) return;
    var part = document.getElementById("part2");
    if (!part) return;

    var sup = D.support;
    var dates = (D.daily && D.daily.dates) || [];
    var lastSup = sup[sup.length - 1];
    var gap = -1;
    if (dates.length && lastSup && dates.indexOf(lastSup.date) >= 0) {
      gap = dates.length - 1 - dates.indexOf(lastSup.date);
    }
    var vals = sup.map(function (r) { return r.netflow; })
                  .filter(function (v) { return typeof v === "number"; });
    var avg = vals.length ? vals.reduce(function (a, b) { return a + b; }, 0) / vals.length : null;

    var box = document.createElement("div");
    box.id = "enhSupKpi";
    box.className = "enh-kpis";
    box.innerHTML =
      kpi("托底日合计", sup.length + " 天", "单日净流入 > 100 亿") +
      kpi("最近托底日", lastSup.date, gap === 0 ? "即最新披露日" : gap > 0 ? "距今 " + gap + " 个交易日" : "已归档") +
      kpi("托底日均值", avg === null ? "—" : (avg > 0 ? "+" : "") + avg.toFixed(1) + " 亿", vals.length + " 个托底日平均");

    var status = part.querySelector(".status");
    part.insertBefore(box, status ? status.nextSibling : null);
  }

  function boot() {
    enhanceDatePicker();
    addSupportKpis();
  }
  if (document.readyState === "complete") setTimeout(boot, 300);
  else window.addEventListener("load", function () { setTimeout(boot, 300); });

  /* 数据异步刷新后会重写 DOM，补一次 */
  setTimeout(function () { enhanceDatePicker(); addSupportKpis(); }, 2500);
})();

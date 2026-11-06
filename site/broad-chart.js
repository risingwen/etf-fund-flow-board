/* 第三部分 · 全市场宽基资金全景（自包含，不依赖 app.js）
   数据：window.__BROAD（broad.js）— 12 类宽基 ETF 日净流入（亿元）+ 累计线 + 最近22日热力矩阵。
   2026-10-26 起使用交易所份额变动 × 单位净值；此前为上游历史序列。 */
(function () {
  "use strict";
  var B = window.__BROAD;
  if (!B) return;

  var COLORS = {
    "沪深300": "#d93630", "中证1000": "#e8862e", "中证500": "#e8b90f",
    "科创50": "#4c7bf3", "中证A500": "#3aa655", "创业板指": "#8e44ad",
    "上证50": "#16a085", "其他宽基": "#a0522d", "创业板50": "#5b8db8",
    "双创50": "#95a5a6", "中证2000": "#27ae60", "国证2000": "#d35400"
  };
  var CATS = B.legendOrder.filter(function (c) { return c !== "累计净流入"; });

  function fmt(v, dec) {
    if (v === null || v === undefined || isNaN(v)) return "--";
    var s = Number(v).toFixed(dec === undefined ? 1 : dec);
    return (v > 0 ? "+" : "") + s;
  }

  function buildOption() {
    var series = CATS.map(function (c) {
      return {
        name: c, type: "bar", stack: "nf", yAxisIndex: 0,
        itemStyle: { color: COLORS[c] || "#7a8a99" },
        emphasis: { focus: "series" },
        data: B.byCategory[c]
      };
    });
    series.push({
      name: "累计净流入", type: "line", yAxisIndex: 1, z: 10,
      showSymbol: false, smooth: false,
      lineStyle: { width: 1.8, color: "#1c2733" },
      itemStyle: { color: "#1c2733" },
      data: B.cumulative
    });
    return {
      title: { text: "宽基分类净流入与累计值", textStyle: { fontSize: 14, color: "#12355c" }, left: 0, top: 0 },
      legend: { data: B.legendOrder, type: "scroll", top: 26, left: 0, textStyle: { fontSize: 12 } },
      tooltip: {
        trigger: "axis", axisPointer: { type: "shadow" },
        formatter: function (ps) {
          var out = [ps[0].axisValue];
          var dayTotal = CATS.reduce((sum, c) => sum + B.byCategory[c][ps[0].dataIndex], 0);
          ps.forEach(function (p) {
            if (p.seriesName === "累计净流入") {
              out.push(p.marker + "累计净流入：" + fmt(p.value) + " 亿");
            } else {
              out.push(p.marker + p.seriesName + "：" + fmt(p.value) + " 亿");
            }
          });
          out.splice(1, 0, "当日合计：" + fmt(dayTotal) + " 亿");
          return out.join("<br>");
        }
      },
      grid: { left: 6, right: 6, top: 88, bottom: 72, containLabel: true },
      xAxis: {
        type: "category", data: B.dates, boundaryGap: true,
        axisLabel: { fontSize: 11, formatter: function (v) { return v.slice(5); } },
        axisTick: { alignWithLabel: true }
      },
      yAxis: [
        {
          type: "value", name: B.axisLeft, nameGap: 12, scale: true,
          nameTextStyle: { fontSize: 12, color: "#5a6b7d" },
          axisLabel: { fontSize: 11 },
          splitLine: { lineStyle: { color: "#e6ecf2" } }
        },
        {
          type: "value", name: B.axisRight, nameGap: 12, scale: true,
          nameTextStyle: { fontSize: 12, color: "#5a6b7d" },
          axisLabel: { fontSize: 11 },
          splitLine: { show: false }
        }
      ],
      dataZoom: [{ type: "slider", height: 18, bottom: 10, start: 0, end: 100 }, { type: "inside" }],
      series: series
    };
  }

  function heatCell(v, maxAbs) {
    if (v === null || v === undefined) return "<td class=\"num\">--</td>";
    var a = (0.05 + 0.5 * Math.abs(v) / (maxAbs || 1)).toFixed(3);
    var bg = v > 0 ? "rgba(192,57,43," + a + ")" : (v < 0 ? "rgba(30,142,79," + a + ")" : "transparent");
    return "<td class=\"num\" style=\"background:" + bg + "\">" + fmt(v, 2) + "</td>";
  }

  function renderHeat() {
    var el = document.getElementById("broadHeat");
    if (!el || !B.heat) return;
    const H = B.heat;
    const maxAbs = Object.fromEntries(CATS.map(c => [c, Math.max(...H.byCategory[c].map(Math.abs))]));
    let html = "<table><thead><tr><th>日期</th><th class='num'>合计</th>";
    CATS.forEach(c => { html += "<th class='num'>" + c + "</th>"; });
    html += "</tr></thead><tbody>";
    for (let i = H.dates.length - 1; i >= 0; i--) {
      const total = CATS.reduce((sum, c) => sum + H.byCategory[c][i], 0);
      html += "<tr><td>" + H.dates[i] + "</td><td class='num'><strong>" + fmt(total, 2) + "</strong></td>";
      CATS.forEach(c => { html += heatCell(H.byCategory[c][i], maxAbs[c]); });
      html += "</tr>";
    }
    html += "</tbody></table>";
    el.innerHTML = html;
  }

  function fillMeta() {
    var el = document.getElementById("broadMeta");
    if (!el || !B.meta) return;
    el.textContent = B.meta.dateFirst + " 至 " + B.meta.dateLast + " · " + B.dates.length +
      " 个交易日。最新日纳入 " + B.meta.broadCount + " 只宽基 ETF，按跟踪指数分 12 类。区间累计 " +
      fmt(B.meta.cumLast, 1) + " 亿元。";
  }

  function init() {
    fillMeta();
    renderHeat();
    var dom = document.getElementById("chartBroad");
    if (dom && window.echarts) {
      var ch = window.echarts.init(dom);
      ch.setOption(buildOption());
      window.addEventListener("resize", function () { ch.resize(); });
    }
  }

  window.__broadBuildOption = buildOption;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();

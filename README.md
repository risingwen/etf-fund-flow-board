# 重点 ETF 资金看板

[打开看板](https://risingwen.github.io/etf-fund-flow-board/) · [部署和定时更新记录](https://github.com/risingwen/etf-fund-flow-board/actions/workflows/pages.yml)

公开静态看板，跟踪 20 只宽基 ETF 的分钟成交、日度申赎和净流入超过 100 亿元的历史交易日。站点部署到 GitHub Pages，图表库随站点提供，行情和历史更新使用公开数据接口。

## 数据怎样更新

| 模块 | 数据来源与计算 | 更新方式 |
| --- | --- | --- |
| 盘中行情及成交排名 | 腾讯证券五日分时，按 20 只 ETF 与上证综指共同有数据的最后一分钟对齐。单只涨跌幅按当日价格和昨收计算。09:31 包含开盘集合竞价，剔除 15:00 后的盘后成交 | 打开页面时读取。北京时间周一至周五交易时段，每 60 秒刷新可见页面。失败时继续显示上一次成功行情，页面标出行情日期 |
| 日度资金、托底日 | 保留上游历史，2026-10-23 之后使用东方财富日线成交额、基金单位净值、沪深交易所 ETF 份额。逐只计算相邻交易日份额差乘当日单位净值。20 只全部齐备才追加 | GitHub Actions 计划每周一至周六北京时间 08:43 增量补齐至前一自然日，节假日无新交易日便跳过。实际运行时间以 Actions 为准 |
| 全市场 12 类宽基 | 上交所基金目录的标的指数、深交所 ETF 目录的拟合指数按规则精确匹配。自 2026-10-26 起将每只 ETF 的相邻交易日交易所份额差乘以当日单位净值，单位为亿元 | 与日度资金同一计划更新。首页展示最新覆盖数、最近 22 个交易日及各日合计 |
| 典型日内走势 | 上游历史样本 | 展示各自的样本日期 |

页面中的成交额和净流入均以亿元计。净流入为申赎估算，“托底日”为金额阈值筛选。部分数据商会修订历史数据；程序保留已发布历史，增量补齐后续日期。

## 11 月 4 日的成交额对账

2026-11-04 的 20 只 ETF，东方财富未复权日线的实际成交额合计 **1,303.4013 亿元**。把每只 ETF 的全天成交量（手）乘以 100 份，再乘当日收盘价，得到 **1,339.3837 亿元**。后一算法复现了对照看板显示的 1,339.38 亿元，和实际成交额相差 **35.9825 亿元**。当天全部 20 只的收盘价都高于按成交金额、成交份额计算的全天均价。单只差额最大的三项是 588000、159915 和 512100。腾讯分时 15:00 的累计额提供第二个核对值。每只 ETF 两个行情源的实际成交额差异均小于 210 元。

[下载 20 只基金的逐只对账 CSV](site/audit/turnover-2026-11-04.csv)。复算脚本为 `pipeline/audit_turnover.py`，示例为 `py pipeline/audit_turnover.py 2026-11-04 turnover.csv`。新输出中的腾讯列只在对应交易日尚处五日分时窗口时可用，原始核对结果随站保存。

## 12 类宽基的覆盖

增量管线先读取[上交所基金目录](https://etf.sse.com.cn/fundlist/)和[深交所 ETF 目录](https://fund.szse.cn/marketdata/etf/index.html)，再按[指数名称或代码](reference/data/broad_benchmarks.json)匹配分类。跟踪同一指数的新增 ETF 随目录自动纳入。其他宽基采用明确列出的境内股票宽基指数，新出现的跟踪指数需要审核后加入规则。[基金清单](reference/data/broad_members.csv)记录代码、跟踪指数、分类和上市日期。首次更新以当时可核实的交易所目录回溯，2026-11-05 匹配到 379 只。

份额取交易所披露数据，单位净值取东方财富历史净值。首个上市日没有可比的上一交易日，下一交易日起计。份额缺失、份额变动但净值未披露或既有基金分类消失时，本次任务报错，站点保留已发布数据。上游快照保留至 2026-10-23，含 193 个交易日；当时使用收盘价口径。区间累计线在原快照累计值上接续新口径，跨口径比较时请同时查看分界日期。

宽基脚本 **`pipeline/update_broad.py`** 沿用下面的 Python 依赖。`py pipeline/update_broad.py` 补到北京时间昨天，`--through 2026-11-05` 可限制结束日期。`py pipeline/update_broad.py --verify-latest` 从原始公开源复算末日全部分类与累计额，仅校验。手动触发补数工作流时会额外执行此校验。

## 发布和预览

在仓库 **Settings → Pages → Source** 选择 **GitHub Actions**。站点和静态资源均从 `site/` 发布。推送到 `main` 会自动部署。手动补数可在 **Actions → Publish ETF board → Run workflow** 运行，勾选补数选项。定时更新如遇上游错误，查看 update 步骤日志并重新运行。

本地预览命令（在仓库根目录执行）：

```powershell
py -m http.server 8000 --bind 127.0.0.1 --directory site
```

打开 <http://127.0.0.1:8000/>。在 Linux/macOS 上将 `py` 换为 `python3`。

增量脚本 **`pipeline/update_daily.py`** 可手动运行：

```powershell
py -m pip install requests openpyxl
py pipeline/update_daily.py
```

脚本从已发布日开始核对交易日历，分批查询交易所份额和当日净值，完整数据写入 `site/data.js`。重复运行会从最后一天续跑。分钟快照脚本 **`pipeline/update_snapshot.mjs`** 使用同一套前端行情计算逻辑，在 Node.js 22 或以上运行 `node pipeline/update_snapshot.mjs` 即可更新内置分钟快照，供实时接口不可用时展示。定时任务也会尝试更新这份快照。复核后提交并推送即可发布。原仓库的全量研究管线和可选 Supabase 工具仍在 `pipeline/`、`deploy/` 和 `supabase/`，日常更新使用上述增量脚本。

本项目 fork 自 [sina-west4angle/etf-fund-flow-board](https://github.com/sina-west4angle/etf-fund-flow-board)。Apache ECharts 5.5.1 随站点分发，许可文件见 `site/vendor/echarts/`。

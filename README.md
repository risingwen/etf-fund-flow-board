# 重点 ETF 资金看板

[打开看板](https://risingwen.github.io/etf-fund-flow-board/) · [部署和定时更新记录](https://github.com/risingwen/etf-fund-flow-board/actions/workflows/pages.yml)

公开静态看板，跟踪 20 只宽基 ETF 的分钟成交、日度申赎和净流入超过 100 亿元的历史交易日。站点部署到 GitHub Pages，图表库随站点提供，行情和历史更新使用公开数据接口。

## 数据怎样更新

| 模块 | 数据来源与计算 | 更新方式 |
| --- | --- | --- |
| 盘中行情及成交排名 | 腾讯证券五日分时，按 20 只 ETF 与上证综指共同有数据的最后一分钟对齐。单只涨跌幅按当日价格和昨收计算。09:31 包含开盘集合竞价，剔除 15:00 后的盘后成交 | 打开页面时读取。北京时间周一至周五交易时段，每 60 秒刷新可见页面。失败时继续显示上一次成功行情，页面标出行情日期 |
| 日度资金、托底日 | 保留上游历史，2026-10-23 之后使用东方财富日线成交额、基金单位净值、沪深交易所 ETF 份额。逐只计算相邻交易日份额差乘当日单位净值。20 只全部齐备才追加 | GitHub Actions 计划每周一至周六北京时间 08:43 增量补齐至前一自然日，节假日无新交易日便跳过。实际运行时间以 Actions 为准 |
| 典型日内走势、全市场宽基分类 | 上游样本与历史快照。全市场分类按份额变动乘收盘价汇总 | 显示各自的样本日期，目前为 2026 年 10 月的快照 |

页面中的成交额和净流入均以亿元计。净流入为申赎估算，“托底日”为金额阈值筛选。部分数据商会修订历史数据；程序保留已发布历史，增量补齐后续日期。

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

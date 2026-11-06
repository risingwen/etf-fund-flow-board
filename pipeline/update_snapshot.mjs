// 保存已对齐的分钟行情，让行情接口暂时不可用的访客也能看到最近一次快照。
import {readFile, writeFile, rename} from "node:fs/promises";
import "../site/quotes.js";

const file = new URL("../site/data.js", import.meta.url);
const prefix = "window.__DATA = ";
const source = (await readFile(file, "utf8")).trim();
if (!source.startsWith(prefix) || !source.endsWith(";")) throw new Error("无法识别 data.js");
const board = JSON.parse(source.slice(prefix.length, -1));
const times = board.init.times;
const live = await globalThis.ETFQuotes.load(board.meta.basket, times);
const stamp = live.date + " " + live.time;
const last = board.cum.today.findLastIndex(v => v !== null);
if (stamp > board.init.date + " " + times[last]) {
  const {date, bars, closes, preClose, table, cum} = live;
  board.init = {date, times, bars, closes, preClose, table};
  board.cum = cum;
  board.meta.minuteDay = date;
  board.meta.generated = stamp;
  const temp = new URL("./data.minute.tmp", file);
  await writeFile(temp, prefix + JSON.stringify(board) + ";\n");
  await rename(temp, file);
  console.log("已保存分钟快照", stamp);
} else {
  console.log("沿用已有分钟快照");
}

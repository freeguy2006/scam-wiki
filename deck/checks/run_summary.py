"""把一次執行的 events 整理成 logs/run_<id>.md。

用法：python checks/run_summary.py [run_id]     （省略時用最近一次執行）
log_event.py end 會自動呼叫。
"""
import sys
from collections import Counter
from datetime import datetime

from common import LOGS, NODE_ORDER, utf8_stdout
from log_event import read_events

RESULT = {"pass": "✅ 通過", "fail": "❌ 不通過", "escalate": "🛑 卡關求救"}


def _result(e):
    if e["node"] == "ESC":
        return f"🧑 人工決定 → {e.get('routed_to') or e.get('next')}"
    return RESULT[e["result"]]


def _checks_cell(checks):
    ok = sum(1 for c in checks if c["pass"])
    bad = [c["item"] for c in checks if not c["pass"]]
    cell = f"✓{ok} ✗{len(bad)}"
    return cell + ("：" + "、".join(bad) if bad else "")


def _scope_cell(s):
    if not s:
        return ""
    slides = "大綱調整中" if s.get("slides") is None else "、".join(s["slides"]) or "—"
    cell = f"重跑 {slides}"
    if s.get("cards"):
        cell += f"（卡 {'、'.join(s['cards'])}）"
    if s.get("untouched") is not None:
        cell += f"，{s['untouched']} 頁不動"
    return cell


def build(run_id):
    rows = read_events(run_id)
    ev = [e for e in rows if e["checker"] != "system"]
    sys_ev = [e for e in rows if e["checker"] == "system"]
    version = rows[0]["graph_version"] if rows else "?"
    start = next((e["timestamp"] for e in sys_ev if e["result"] == "start"), None)
    end = next((e["timestamp"] for e in sys_ev if e["result"] == "end"), None)
    lines = [f"# 執行紀錄 {run_id}（graph {version}）", ""]
    if start:
        lines.append(f"- 開始：{start}" + (f"　結束：{end}" if end else "　（未結束）"))
        if end:
            mins = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60
            lines.append(f"- 總耗時：約 {mins:.0f} 分鐘")
    fails = [e for e in ev if e["result"] != "pass" and e["node"] != "ESC"]
    lines += [
        f"- 檢查次數：{len(ev)}（程式 {sum(e['checker'] == 'script' for e in ev)}、AI {sum(e['checker'] == 'ai' for e in ev)}、人工 {sum(e['checker'] == 'human' for e in ev)}）",
        f"- 不通過：{len(fails)} 次；其中大退回 {sum(bool(e.get('big_retreat')) for e in ev)} 次、卡關求救 {sum(e['result'] == 'escalate' for e in ev)} 次",
        f"- 人工關卡退回：{sum(e['node'] in ('U0', 'U4', 'U9') and e['result'] == 'fail' for e in ev)} 次；卡關後人工決定：{sum(e['node'] == 'ESC' for e in ev)} 次",
        "",
        "## 各節點彙總",
        "",
        "| 節點 | 檢查次數 | 不通過 | 最多到第幾輪 | 最後結果 |",
        "|---|---|---|---|---|",
    ]
    for node in NODE_ORDER + ["ESC"]:
        ne = [e for e in ev if e["node"] == node]
        if not ne:
            continue
        lines.append(f"| {node} | {len(ne)} | {sum(e['result'] != 'pass' for e in ne)} | "
                     f"{max(e['attempt'] for e in ne)} | {_result(ne[-1])} |")

    lines += ["", "## 逐筆紀錄", "",
              "| # | 時間 | 節點 | 輪 | 檢查者 | 結果 | 檢查項目 | 錯誤類型 | 發現→產生 | 退回到 | 重跑範圍 |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, e in enumerate(ev, 1):
        gap = f"{e['detected_at']}→{e['origin_node']}" if e["result"] != "pass" and e["detected_at"] else ""
        route = (e.get("routed_to") or "") + ("（大退回）" if e.get("big_retreat") else "")
        if e["result"] == "escalate":
            route = "暫停問使用者"
        lines.append(f"| {i} | {e['timestamp'][11:19]} | {e['node']} | {e['attempt']} | {e['checker']} | "
                     f"{_result(e)} | {_checks_cell(e['checks'])} | {'、'.join(e['error_type'])} | "
                     f"{gap} | {route} | {_scope_cell(e.get('rerun_scope'))} |")

    lines += ["", "## 退回原因", ""]
    if not fails:
        lines.append("（沒有退回）")
    for i, e in enumerate(ev, 1):
        if e["result"] != "pass":
            lines.append(f"- **#{i} {e['node']} 第 {e['attempt']} 輪 → {e.get('routed_to') or '使用者'}**：{e.get('reason') or ''}")

    gaps = Counter(f"{e['detected_at']}→{e['origin_node']}" for e in fails
                   if e["origin_node"] and e["origin_node"] != e["detected_at"])
    lines += ["", "## 晚發現的錯誤（發現位置 ≠ 產生位置）", ""]
    lines += [f"- {k}：{v} 次" for k, v in gaps.most_common()] or ["（沒有）"]
    return "\n".join(lines) + "\n"


def write(run_id):
    path = LOGS / f"run_{run_id}.md"
    path.write_text(build(run_id), "utf-8")
    print(f"已產生 {path.relative_to(LOGS.parent).as_posix()}")


def main():
    utf8_stdout()
    if len(sys.argv) > 1:
        run_id = sys.argv[1]
    else:
        runs = [e["run_id"] for e in read_events()]
        if not runs:
            raise SystemExit("還沒有任何執行紀錄")
        run_id = runs[-1]
    write(run_id)


if __name__ == "__main__":
    main()

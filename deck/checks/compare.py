"""比較不同 graph 版本的執行紀錄 → logs/compare.md。

預設每個版本取「最後一次完整執行（有 end）」；加 --all 則合併該版本所有執行。

用法：python checks/compare.py [--all]
"""
import argparse
from collections import Counter, defaultdict

from common import LOGS, NODE_ORDER, cfg, utf8_stdout
from log_event import read_events


def pick_runs(rows, use_all):
    by_ver = defaultdict(list)
    for e in rows:
        if e["node"] == "RUN" and e["result"] == "end":
            by_ver[e["graph_version"]].append(e["run_id"])
    if use_all:
        return {v: ids for v, ids in by_ver.items()}
    return {v: ids[-1:] for v, ids in by_ver.items()}


def stats(ev):
    fails = [e for e in ev if e["result"] != "pass" and e["node"] != "ESC"]
    scoped = [e for e in ev if e.get("rerun_scope") and e["rerun_scope"].get("slides") is not None]
    return {
        "檢查次數": len(ev),
        "不通過次數": len(fails),
        "大退回": sum(bool(e.get("big_retreat")) for e in ev),
        "卡關求救": sum(e["result"] == "escalate" for e in ev),
        "人工介入（含通過）": sum(e["checker"] == "human" for e in ev),
        "人工關卡退回": sum(e["node"] in ("U0", "U4", "U9") and e["result"] == "fail" for e in ev),
        "晚發現（發現≠產生）": sum(1 for e in fails if e["origin_node"] and e["origin_node"] != e["detected_at"]),
        "局部重跑時重寫的頁數": max((len(e["rerun_scope"]["slides"]) for e in scoped), default=0),
        "局部重跑時不動的頁數": max((e["rerun_scope"].get("untouched") or 0 for e in scoped), default=0),
    }


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    rows = read_events()
    runs = pick_runs(rows, a.all)
    if not runs:
        raise SystemExit("還沒有完整的執行紀錄（需要 log_event.py end）")
    versions = sorted(runs)
    ev = {v: [e for e in rows if e["run_id"] in runs[v] and e["checker"] != "system"] for v in versions}

    head = "| 指標 | " + " | ".join(versions) + " |"
    sep = "|---|" + "---|" * len(versions)
    out = ["# graph 版本比較", "",
           f"目前 config 版本：{cfg()['graph_version']}。比較的執行：" +
           "；".join(f"{v} = {', '.join(runs[v])}" for v in versions), "",
           "## 整體", "", head, sep]
    st = {v: stats(ev[v]) for v in versions}
    for k in st[versions[0]]:
        out.append(f"| {k} | " + " | ".join(str(st[v][k]) for v in versions) + " |")

    out += ["", "## 各節點不通過次數（哪個節點最常出錯）", "", head.replace("指標", "節點"), sep]
    for node in NODE_ORDER:
        cells = [sum(1 for e in ev[v] if e["node"] == node and e["result"] != "pass") for v in versions]
        if any(cells) or any(e["node"] == node for v in versions for e in ev[v]):
            out.append(f"| {node} | " + " | ".join(map(str, cells)) + " |")

    out += ["", "## 錯誤類型排名", ""]
    for v in versions:
        cnt = Counter(t for e in ev[v] if e["result"] != "pass" for t in e["error_type"])
        out.append(f"- **{v}**：" + ("、".join(f"{t} {n}" for t, n in cnt.most_common()) or "（沒有錯誤）"))

    out += ["", "## 在哪裡發現 vs 在哪裡產生（檢查有沒有往前移）", "",
            "同一種錯誤如果在新版本改成「產生的節點當場發現」，代表檢查成功往前移。", ""]
    for v in versions:
        pairs = Counter(f"{e['detected_at']}→{e['origin_node']}（{'、'.join(e['error_type'])}）"
                        for e in ev[v] if e["result"] != "pass" and e["detected_at"])
        out.append(f"- **{v}**：" + ("、".join(f"{p} ×{n}" for p, n in pairs.most_common()) or "（沒有錯誤）"))

    out += ["", "## 各 loop 用了幾輪才通過", "", head.replace("指標", "loop"), sep]
    for loop in cfg()["loops"]:
        cells = []
        for v in versions:
            att = [e["attempt"] for e in ev[v] if e.get("loop") == loop]
            cells.append(str(max(att)) if att else "—")
        out.append(f"| {loop} | " + " | ".join(cells) + " |")

    if len(versions) >= 2:
        out += ["", "## graph 改了什麼", "",
                f"```\ngit diff graph-{versions[0]} graph-{versions[-1]} -- deck/graph.md deck/config.json deck/checks deck/prompts\n```"]
    path = LOGS / "compare.md"
    path.write_text("\n".join(out) + "\n", "utf-8")
    print(f"已產生 {path.relative_to(LOGS.parent).as_posix()}")


if __name__ == "__main__":
    main()

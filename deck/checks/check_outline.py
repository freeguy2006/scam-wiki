"""N4 大綱檢查：work/04_outline.md → work/04_check.json。

大綱格式（每頁一段）：
  ## S01｜標題
  - 段落：cover
  - 目的：……
  - 卡號：E01、E05
  - 題數：2          ← 只有 quiz 段落需要

用法：python checks/check_outline.py [--no-log]
"""
import argparse

from common import (PREV, SLIDE_ID, WORK, cfg, finish, item, load_json, load_scope,
                    parse_outline, utf8_stdout)


def run():
    c = cfg()
    checks = []
    try:
        slides = parse_outline((WORK / "04_outline.md").read_text("utf-8"))
        cards = {k["id"] for k in load_json(WORK / "03_evidence.json")["cards"]}
    except Exception as e:  # noqa: BLE001
        return [item("檔案格式", False, str(e), "結構缺段", "N4")]
    if not slides:
        return [item("檔案格式", False, "找不到「## S01｜標題」格式的頁面", "結構缺段", "N4")]

    ids = [s["id"] for s in slides]
    bad = [i for i in ids if not SLIDE_ID.match(i)] + sorted({i for i in ids if ids.count(i) > 1})
    checks.append(item("頁碼格式與不重複", not bad, f"有問題：{bad}" if bad else "", "結構缺段", "N4"))

    n = len(slides)
    checks.append(item(f"頁數 {c['slides_min']}～{c['slides_max']}", c["slides_min"] <= n <= c["slides_max"],
                       f"目前 {n} 頁", "結構缺段", "N4"))

    order = [s["id"] for s in c["segments"]]
    unknown = [f"{s['id']}：{s['segment']}" for s in slides if s["segment"] not in order]
    checks.append(item("段落名稱正確", not unknown, "、".join(unknown), "結構缺段", "N4"))

    idx = [order.index(s["segment"]) for s in slides if s["segment"] in order]
    checks.append(item("教學順序（目標→概念→手法→紅旗→應對→測驗→總結）", idx == sorted(idx),
                       "" if idx == sorted(idx) else "段落順序顛倒", "結構缺段", "N4"))

    count_bad = []
    for seg in c["segments"]:
        k = sum(1 for s in slides if s["segment"] == seg["id"])
        if not seg["min_slides"] <= k <= seg["max_slides"]:
            count_bad.append(f"{seg['name']} {k} 頁（應 {seg['min_slides']}～{seg['max_slides']}）")
    checks.append(item("各段頁數", not count_bad, "、".join(count_bad), "結構缺段", "N4"))

    no_card = [s["id"] for s in slides if not s["cards"]]
    checks.append(item("每頁至少引用 1 張卡", not no_card, f"沒有卡號：{no_card}" if no_card else "",
                       "缺來源", "N4", no_card))
    ghost = [f"{s['id']}:{k}" for s in slides for k in s["cards"] if k not in cards]
    checks.append(item("卡號都存在", not ghost, f"不存在：{ghost}" if ghost else "", "缺來源", "N4",
                       [g.split(":")[0] for g in ghost]))

    quiz_total = sum(s["quiz"] for s in slides if s["segment"] == "quiz")
    quiz_zero = [s["id"] for s in slides if s["segment"] == "quiz" and s["quiz"] < 1]
    ok = c["quiz_min"] <= quiz_total <= c["quiz_max"] and not quiz_zero
    checks.append(item(f"測驗 {c['quiz_min']}～{c['quiz_max']} 題", ok,
                       f"目前 {quiz_total} 題" + (f"；{quiz_zero} 沒寫題數" if quiz_zero else ""), "結構缺段", "N4"))

    no_purpose = [s["id"] for s in slides if not s["purpose"]]
    checks.append(item("每頁有教學目的", not no_purpose, f"缺：{no_purpose}" if no_purpose else "", "結構缺段", "N4"))

    scope = load_scope()
    if scope and scope.get("slides") is not None and (PREV / "04_outline.md").exists():
        old = {s["id"]: s["raw"] for s in parse_outline((PREV / "04_outline.md").read_text("utf-8"))}
        new = {s["id"]: s["raw"] for s in slides}
        allowed = set(scope["slides"])
        changed = [i for i in old if i not in allowed and new.get(i) != old[i]]
        checks.append(item("範圍外頁面的大綱未變動", not changed, f"不該改動：{changed}" if changed else "",
                           "超出重跑範圍", "N4", changed))
    return checks


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()
    finish("N4", run(), WORK / "04_check.json", log=not a.no_log)


if __name__ == "__main__":
    main()

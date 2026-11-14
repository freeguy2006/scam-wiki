"""N3 證據卡檢查：work/03_evidence.json → work/03_check.json。

- 原句要「逐字」出現在指定頁面的指定段落（比對前只去掉 [[連結]]、粗體、空白，並把全形轉半形）
- claim（白話句）裡的數字必須都出現在原句裡
- 局部重跑時，範圍外的卡片不能變動

用法：python checks/check_evidence.py [--no-log]
"""
import argparse

import log_event
from common import (CARD_ID, PREV, WORK, cfg, finish, item, load_json, load_scope,
                    norm, numbers, numbers_with_unit, plain, table_rows, utf8_stdout, wiki_pages, wiki_sections,
                    year_aliases)


def _repeat_shortage(seg_names):
    """同一次執行中，上一輪 N3 也因同一段卡片不足而失敗 → 判定 wiki 本身不足，退回 N1。"""
    try:
        run = log_event.current_run()
    except SystemExit:
        return False
    prev = [e for e in log_event.read_events(run["run_id"]) if e["node"] == "N3" and e["result"] != "pass"]
    if not prev:
        return False
    for c in prev[-1]["checks"]:
        if c["item"] == "每段卡片足夠" and not c["pass"] and any(n in c.get("detail", "") for n in seg_names):
            return True
    return False


def run():
    c = cfg()
    pages = wiki_pages()
    checks = []
    try:
        cards = load_json(WORK / "03_evidence.json")["cards"]
        retrieval = load_json(WORK / "01_retrieval.json")
    except Exception as e:  # noqa: BLE001
        return [item("檔案格式", False, str(e), "結構缺段", "N3")]
    selected = {p["page"] for s in retrieval["segments"] for p in s.get("pages", [])}

    ids = [k.get("id", "") for k in cards]
    bad_id = [i for i in ids if not CARD_ID.match(i)]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    checks.append(item("卡號格式與不重複", not bad_id and not dup,
                       f"格式錯誤：{bad_id}；重複：{dup}" if bad_id or dup else f"共 {len(cards)} 張",
                       "結構缺段", "N3"))

    not_selected, no_section, not_verbatim, num_bad = [], [], [], []
    cache = {}
    for k in cards:
        page, sec, quote = k.get("page"), k.get("section"), k.get("quote", "")
        if page not in pages or page not in selected:
            not_selected.append(f"{k.get('id')}：{page}")
            continue
        if page not in cache:
            cache[page] = wiki_sections(pages[page])
        secs = cache[page]
        if sec not in secs:
            no_section.append(f"{k.get('id')}：{page} 沒有「## {sec}」")
            continue
        if not quote or norm(quote) not in norm(secs[sec]):
            not_verbatim.append(f"{k.get('id')}（{page}／{sec}）")
        extra = numbers(k.get("claim", "")) - year_aliases(numbers(quote))
        if extra:
            num_bad.append(f"{k.get('id')}：{sorted(extra)}")
    checks.append(item("頁面在 N1 選取範圍內", not not_selected, "、".join(not_selected), "缺來源", "N3"))
    checks.append(item("段落存在", not no_section, "、".join(no_section), "缺來源", "N3"))
    checks.append(item("原句逐字出現在 wiki", not not_verbatim, "不符：" + "、".join(not_verbatim) if not_verbatim else "",
                       "缺來源", "N3"))
    checks.append(item("白話句數字都在原句裡", not num_bad, "、".join(num_bad), "數字不符", "N3"))

    # v2：數字的口徑寫在表格第一欄。v1 的摘要句漏掉「轉移 50% 款項」到 N6 才發現，
    # 這裡要求：卡片數字若是同頁某表格列的數值，必須有卡片抄下那一列（帶出指標名稱）。
    no_scope = []
    for k in cards:
        page = k.get("page")
        if page not in pages or page not in selected:
            continue
        same_page = [norm(x.get("quote", "")) for x in cards if x.get("page") == page]
        for first, value, _ in table_rows(pages[page]):
            hit = numbers_with_unit(k.get("quote", "")) & numbers_with_unit(value)
            if hit and not any(norm(first) in q for q in same_page):
                no_scope.append(f"{k.get('id')} 的 {'、'.join(sorted(hit))} → 缺表格列「{plain(first)}」")
    no_scope = list(dict.fromkeys(no_scope))
    checks.append(item("數字附上表格口徑", not no_scope, "；".join(no_scope), "扭曲原意", "N3"))

    short = []
    for s in c["segments"]:
        if "min_cards" not in s:
            continue
        n = sum(1 for k in cards if k.get("segment") == s["id"])
        if n < s["min_cards"]:
            short.append(f"{s['name']} {n}/{s['min_cards']}")
    origin = "N1" if short and _repeat_shortage([x.split()[0] for x in short]) else "N3"
    checks.append(item("每段卡片足夠", not short, "不足：" + "、".join(short) if short else "",
                       "覆蓋不足", origin))

    scope = load_scope()
    if scope and (PREV / "03_evidence.json").exists():
        old = {k["id"]: k for k in load_json(PREV / "03_evidence.json")["cards"]}
        new = {k["id"]: k for k in cards}
        allowed = set(scope.get("cards", []))
        changed = [i for i in old if i not in allowed and new.get(i) != old[i]]
        checks.append(item("範圍外卡片未變動", not changed,
                           f"不該改動：{changed}" if changed else f"重跑範圍：{sorted(allowed) or '（只新增）'}",
                           "超出重跑範圍", "N3"))
    return checks


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()
    finish("N3", run(), WORK / "03_check.json", log=not a.no_log)


if __name__ == "__main__":
    main()

"""N5 逐頁稿檢查：work/05_slides.json → work/05_check.json，並產生 work/05_links.json 給 N7 用。

05_slides.json 格式見 graph.md「檔案格式」。

用法：python checks/check_slides.py [--no-log]
"""
import argparse
import re

from common import (PREV, WORK, cfg, char_count, finish, item, link_href, load_json,
                    load_scope, numbers, parse_outline, roc_year_problems, save_json,
                    slide_cards, utf8_stdout, wiki_pages, year_aliases)

FORBIDDEN_SUPPLEMENT = [
    (re.compile(r"\d"), "數字"),
    (re.compile(r"https?://|www\.|\.com|\.tw|\.org", re.I), "網址"),
    (re.compile(r"第.{1,6}條|條例|法第"), "法條"),
]


def run():
    c = cfg()
    pages = wiki_pages()
    checks = []
    try:
        deck = load_json(WORK / "05_slides.json")
        slides = deck["slides"]
        cards = {k["id"]: k for k in load_json(WORK / "03_evidence.json")["cards"]}
        outline = {s["id"]: s for s in parse_outline((WORK / "04_outline.md").read_text("utf-8"))}
    except Exception as e:  # noqa: BLE001
        return [item("檔案格式", False, str(e), "結構缺段", "N5")], {}

    # --- 結構 ---
    n = len(slides)
    checks.append(item(f"頁數 {c['slides_min']}～{c['slides_max']}", c["slides_min"] <= n <= c["slides_max"],
                       f"目前 {n} 頁", "結構缺段", "N5"))
    ids = [s.get("id") for s in slides]
    mismatch = [i for i in ids if i not in outline] + [i for i in outline if i not in ids]
    seg_diff = [s["id"] for s in slides if s.get("id") in outline and s.get("segment") != outline[s["id"]]["segment"]]
    order_diff = ids != [i for i in outline if i in ids]
    ok = not mismatch and not seg_diff and not order_diff
    checks.append(item("和大綱一致（頁碼、段落、順序）", ok,
                       f"頁碼不一致：{mismatch}；段落不同：{seg_diff}；順序不同：{order_diff}" if not ok else "",
                       "結構缺段", "N5", mismatch + seg_diff))

    # --- 來源 ---
    no_card, ghost, off_outline, src_bad, block_no_card = [], [], [], [], []
    for s in slides:
        used = slide_cards(s)
        if not used:
            no_card.append(s["id"])
        ghost += [f"{s['id']}:{k}" for k in used if k not in cards]
        if s["id"] in outline:
            off_outline += [f"{s['id']}:{k}" for k in used if k not in outline[s["id"]]["cards"]]
        for i, b in enumerate(s.get("blocks", []), 1):
            if b.get("type", "fact") == "fact" and not b.get("cards"):
                block_no_card.append(f"{s['id']}-b{i}")
        expect = list(dict.fromkeys(cards[k]["page"] for k in used if k in cards))
        if sorted(s.get("sources", [])) != sorted(expect):
            src_bad.append(f"{s['id']}（應為 {'、'.join(expect)}）")
    checks.append(item("每頁至少引用 1 張卡", not no_card, f"{no_card}" if no_card else "", "缺來源", "N5", no_card))
    checks.append(item("每句都有卡號或補充標記", not block_no_card, "、".join(block_no_card), "缺來源", "N5",
                       [b.split("-")[0] for b in block_no_card]))
    checks.append(item("卡號都存在", not ghost, "、".join(ghost), "缺來源", "N5", [g.split(":")[0] for g in ghost]))
    checks.append(item("只用大綱分配給該頁的卡", not off_outline, "、".join(off_outline), "結構缺段", "N5",
                       [g.split(":")[0] for g in off_outline]))
    checks.append(item("來源列 = 引用卡片的 wiki 頁面", not src_bad, "、".join(src_bad), "缺來源", "N5",
                       [x.split("（")[0] for x in src_bad]))

    # --- 數字 ---
    def allowed_nums(ids_):
        out = set()
        for k in ids_:
            if k in cards:
                out |= numbers(cards[k]["quote"])
        return year_aliases(out)

    num_bad, roc_bad = [], []
    for s in slides:
        texts = [(s.get("title", ""), slide_cards(s), "標題"), (s.get("notes", ""), slide_cards(s), "備註")]
        texts += [(b.get("text", ""), b.get("cards", []), f"b{i}") for i, b in enumerate(s.get("blocks", []), 1)
                  if b.get("type", "fact") == "fact"]
        for qi, q in enumerate(s.get("quiz", []), 1):
            qc = q.get("q_cards", []) + q.get("a_cards", [])
            texts.append((q.get("question", ""), qc, f"Q{qi} 題目"))
            texts += [(o.get("text", ""), qc, f"Q{qi} 選項") for o in q.get("options", [])]
            texts.append((q.get("answer", ""), qc, f"Q{qi} 解答"))
        for text, ids_, where in texts:
            extra = numbers(text) - allowed_nums(ids_)
            if extra:
                num_bad.append(f"{s['id']} {where}：{sorted(extra)}")
            roc_bad += [f"{s['id']} {where}：{p}" for p in roc_year_problems(text)]
    checks.append(item("數字都出現在引用的卡片裡", not num_bad, "、".join(num_bad), "數字不符", "N5",
                       [x.split()[0] for x in num_bad]))
    checks.append(item("民國年附西元且換算正確", not roc_bad, "、".join(roc_bad), "數字不符", "N5",
                       [x.split()[0] for x in roc_bad]))

    # --- 字數 ---
    long_ = []
    for s in slides:
        if s.get("segment") == "quiz":
            k = sum(char_count(q.get("question", "")) + sum(char_count(o.get("text", "")) for o in q.get("options", []))
                    for q in s.get("quiz", []))
            if k > c["quiz_char_max_per_slide"]:
                long_.append(f"{s['id']} 測驗 {k}/{c['quiz_char_max_per_slide']} 字")
        else:
            k = sum(char_count(b.get("text", "")) for b in s.get("blocks", []))
            if k > c["body_char_max"]:
                long_.append(f"{s['id']} {k}/{c['body_char_max']} 字")
    checks.append(item(f"正文 ≤ {c['body_char_max']} 字", not long_, "、".join(long_), "版面溢出", "N5",
                       [x.split()[0] for x in long_]))

    # --- 補充 ---
    sp = c["supplement"]
    sup_bad, total = [], 0
    for s in slides:
        sups = [b for b in s.get("blocks", []) if b.get("type") == "supplement"]
        total += len(sups)
        if sups and s.get("segment") not in sp["segments"]:
            sup_bad.append(f"{s['id']} 不在允許的段落（只能在 {sp['segments']}）")
        if len(sups) > sp["max_per_slide"]:
            sup_bad.append(f"{s['id']} 有 {len(sups)} 則（上限 {sp['max_per_slide']}）")
        for b in sups:
            if b.get("cards"):
                sup_bad.append(f"{s['id']} 補充不應帶卡號（有卡號就是事實句）")
            for pat, label in FORBIDDEN_SUPPLEMENT:
                if pat.search(b.get("text", "")):
                    sup_bad.append(f"{s['id']} 補充含{label}：「{b['text'][:20]}…」")
        if any(b.get("type") not in ("fact", "supplement", None) for b in s.get("blocks", [])):
            sup_bad.append(f"{s['id']} 有未知的區塊類型")
    if total > sp["max_total"]:
        sup_bad.append(f"整份 {total} 則（上限 {sp['max_total']}）")
    checks.append(item("補充規則", not sup_bad, "、".join(sup_bad) if sup_bad else f"共 {total} 則",
                       "補充違規", "N5", [x.split()[0] for x in sup_bad if x.startswith("S")]))

    # --- 測驗 ---
    qs = [(s, q) for s in slides for q in s.get("quiz", [])]
    stray = [s["id"] for s in slides if s.get("quiz") and s.get("segment") != "quiz"]
    checks.append(item(f"測驗 {c['quiz_min']}～{c['quiz_max']} 題，且只在測驗頁", c["quiz_min"] <= len(qs) <= c["quiz_max"] and not stray,
                       f"目前 {len(qs)} 題" + (f"；非測驗頁有題目：{stray}" if stray else ""), "結構缺段", "N5", stray))
    q_src, q_form, q_sup = [], [], []
    for s, q in qs:
        tag = f"{s['id']}/{q.get('id', '?')}"
        if not q.get("q_cards"):
            q_src.append(f"{tag} 題目沒有卡號")
        if not q.get("a_cards"):
            q_src.append(f"{tag} 解答沒有卡號")
        if not q.get("answer"):
            q_src.append(f"{tag} 沒有解說")
        opts = q.get("options", [])
        n_correct = sum(1 for o in opts if o.get("correct"))
        if not 2 <= len(opts) <= 4 or n_correct != 1:
            q_form.append(f"{tag} 選項 {len(opts)} 個、正解 {n_correct} 個（應 2～4 個、正解 1 個）")
    for s in slides:
        if s.get("segment") == "quiz" and any(b.get("type") == "supplement" for b in s.get("blocks", [])):
            q_sup.append(s["id"])
        for q in s.get("quiz", []):
            if q.get("type") == "supplement":
                q_sup.append(f"{s['id']}/{q.get('id', '?')}")
    checks.append(item("測驗題目與解答都有卡號", not q_src, "、".join(q_src), "缺來源", "N5",
                       [x.split("/")[0] for x in q_src]))
    checks.append(item("測驗選項格式", not q_form, "、".join(q_form), "結構缺段", "N5",
                       [x.split("/")[0] for x in q_form]))
    checks.append(item("測驗不使用補充內容", not q_sup, f"{q_sup}" if q_sup else "", "補充違規", "N5",
                       [x.split("/")[0] for x in q_sup]))

    # --- 局部重跑 ---
    scope = load_scope()
    if scope and scope.get("slides") is not None and (PREV / "05_slides.json").exists():
        old = {s["id"]: s for s in load_json(PREV / "05_slides.json")["slides"]}
        new = {s["id"]: s for s in slides}
        allowed = set(scope["slides"])
        changed = [i for i in old if i not in allowed and new.get(i) != old[i]]
        checks.append(item("範圍外頁面未變動", not changed,
                           f"不該改動：{changed}" if changed else f"只重寫 {sorted(allowed)}，其餘 {len(old) - len(allowed & set(old))} 頁不動",
                           "超出重跑範圍", "N5", changed))

    # --- 給 N7 的連結表 ---
    base = c["source_base_url"]
    links = {}
    for k in cards.values():
        if k["page"] in pages:
            href, rel = link_href(base, pages[k["page"]])
            links[k["page"]] = {"wiki_path": rel, "href": href}
    return checks, {"source_base_url": base, "pages": links}


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()
    checks, links = run()
    if links:
        save_json(WORK / "05_links.json", links)
    finish("N5", checks, WORK / "05_check.json", log=not a.no_log)


if __name__ == "__main__":
    main()

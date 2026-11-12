"""N8 渲染檢查：用 Playwright 開 deck/deck.html，對照 work/05_slides.json。

檢查：頁數與順序、鍵盤翻頁、HTML 文字和稿一致（沒有多出字或數字）、補充標記、
每頁來源列與連結、測驗可點且解答顯示出處、桌機與手機寬度不溢出、沒有 JS 錯誤、
局部重跑時範圍外頁面的 HTML 未變動。截圖存到 work/screenshots/。

HTML 必須遵守的標記約定見 prompts/gen_N7_render.md。

用法：python checks/check_render.py [--no-log]
"""
import argparse
import re
from urllib.parse import quote, unquote

import log_event
from common import (DECK, PREV, WORK, cfg, char_count, finish, item, load_json, load_scope,
                    norm, numbers, utf8_stdout, wiki_pages, year_aliases)

HTML = DECK / "deck.html"
SHOTS = WORK / "screenshots"

JS_CURRENT = """() => {
  let best = null, area = 0;
  for (const s of document.querySelectorAll('section.slide')) {
    const cs = getComputedStyle(s);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.5) continue;
    const r = s.getBoundingClientRect();
    const w = Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0));
    const h = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
    if (w * h > area) { area = w * h; best = s.dataset.slide; }
  }
  return best;
}"""

JS_INSPECT = """(sid) => {
  const s = document.querySelector(`section.slide[data-slide="${sid}"]`);
  if (!s) return null;
  const vis = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden'; };
  const chainVisible = (el, root) => { for (let e = el; e && e !== root.parentElement; e = e.parentElement) if (!vis(e)) return false; return true; };
  const textOf = (root, exclude) => {
    let out = '';
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (w.nextNode()) {
      const el = w.currentNode.parentElement;
      if (!el || (exclude && el.closest(exclude)) || !chainVisible(el, root)) continue;
      out += w.currentNode.textContent + ' ';
    }
    return out;
  };
  const scrollable = ['auto', 'scroll'].includes(getComputedStyle(s).overflowY);
  const over = [];
  for (const el of s.querySelectorAll('*')) {
    if (el.closest('[data-notes],[data-deco],[aria-hidden="true"]') || !chainVisible(el, s)) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    const label = el.tagName.toLowerCase() + '「' + (el.textContent || '').trim().slice(0, 12) + '」';
    if (r.right > innerWidth + 1 || r.left < -1) over.push('水平 ' + label);
    else if (!scrollable && (r.bottom > innerHeight + 1 || r.top < -1)) over.push('垂直 ' + label);
  }
  if (s.scrollWidth > s.clientWidth + 1) over.push('頁面可水平捲動');
  const links = sel => [...s.querySelectorAll(sel)].map(a => ({text: a.textContent.trim(), path: a.dataset.wikiPath || null, href: a.getAttribute('href')}));
  return {
    body: textOf(s, '[data-ui],[data-sources],[data-notes],[data-answer]'),
    over: [...new Set(over)].slice(0, 6),
    sources: links('[data-sources] a'),
    supplements: s.querySelectorAll('[data-supplement]').length,
    notesVisible: [...s.querySelectorAll('[data-notes]')].some(e => chainVisible(e, s) && e.getBoundingClientRect().height > 0),
  };
}"""

JS_ANSWER = """(qid) => {
  const q = document.querySelector(`[data-quiz="${qid}"]`);
  if (!q) return null;
  const a = q.querySelector('[data-answer]');
  if (!a) return {exists: false};
  const cs = getComputedStyle(a);
  const visible = cs.display !== 'none' && cs.visibility !== 'hidden' && !a.hidden && a.getBoundingClientRect().height > 0;
  let text = '';
  const w = document.createTreeWalker(a, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) if (!w.currentNode.parentElement.closest('[data-answer-sources]')) text += w.currentNode.textContent;
  return {exists: true, visible, text,
          sources: [...a.querySelectorAll('[data-answer-sources] a')].map(x => ({text: x.textContent.trim(), path: x.dataset.wikiPath || null, href: x.getAttribute('href')}))};
}"""


def _sections(html):
    return {m.group(1): re.sub(r"\s+", " ", m.group(0))
            for m in re.finditer(r'<section\b[^>]*data-slide="(S\w+)"[^>]*>.*?</section>', html, re.S)}


def _prev_overflow_slides():
    try:
        run = log_event.current_run()
    except SystemExit:
        return set()
    prev = [e for e in log_event.read_events(run["run_id"]) if e["node"] == "N8" and e["result"] != "pass"]
    if not prev:
        return set()
    return {s for c in prev[-1]["checks"] if c["item"].startswith("文字不溢出") and not c["pass"]
            for s in c.get("slides", [])}


def _link_ok(link, base, pages_by_name, expect_name):
    rel = pages_by_name.get(expect_name)
    if rel is None or link["path"] != rel:
        return False
    return link["href"] in (base + rel, base + quote(rel))


def run():
    c = cfg()
    base = c["source_base_url"]
    sp_label = c["supplement"]["label"]
    checks = []
    if not HTML.exists():
        return [item("deck.html 存在", False, "找不到 deck/deck.html", "結構缺段", "N7")]
    raw = HTML.read_text("utf-8")
    deck = load_json(WORK / "05_slides.json")
    slides = deck["slides"]
    expected_ids = [s["id"] for s in slides]
    pages_by_name = {k: v[len("wiki/"):] for k, v in wiki_pages().items()}
    cards = {k["id"]: k for k in load_json(WORK / "03_evidence.json")["cards"]}

    # --- 靜態檢查 ---
    ext_js = re.findall(r"<script[^>]+src=[\"']([^\"']+)", raw)
    ext_css = [h for h in re.findall(r"<link[^>]+href=[\"'](https?://[^\"']+)", raw)
               if not re.match(r"https://fonts\.(googleapis|gstatic)\.com/", h)]
    checks.append(item("單一 HTML 檔（無外部 JS／CSS，字型除外）", not ext_js and not ext_css,
                       f"外部檔案：{ext_js + ext_css}" if ext_js or ext_css else "", "結構缺段", "N7"))
    m = re.search(r"<html[^>]*data-source-base=[\"']([^\"']*)[\"']", raw)
    checks.append(item("html 標記 data-source-base 與設定一致", bool(m) and m.group(1) == base,
                       f"設定 {base}，HTML {m.group(1) if m else '（沒有）'}", "缺來源", "N7"))
    nested = len(re.findall(r"<section\b", raw)) != len(_sections(raw))
    checks.append(item("沒有巢狀 section", not nested, "", "結構缺段", "N7"))

    scope = load_scope()
    if scope and scope.get("slides") is not None and (PREV / "deck.html").exists():
        old, new = _sections((PREV / "deck.html").read_text("utf-8")), _sections(raw)
        allowed = set(scope["slides"])
        changed = [i for i in old if i not in allowed and new.get(i) != old[i]]
        checks.append(item("範圍外頁面的 HTML 未變動", not changed,
                           f"不該改動：{changed}" if changed else f"只重排 {sorted(allowed)}",
                           "超出重跑範圍", "N7", changed))

    # --- 瀏覽器檢查 ---
    from playwright.sync_api import sync_playwright

    repeat_over = _prev_overflow_slides()
    js_errors, nav_bad, over_bad = [], {}, {}
    text_bad, num_bad, extra_bad, sup_bad, src_bad, notes_bad = [], [], [], [], [], []
    quiz_bad, quiz_src_bad = [], []
    order_ok = True
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel=c.get("browser_channel") or None)
        except Exception:  # noqa: BLE001
            browser = p.chromium.launch()
        for vp in c["render"]["viewports"]:
            desktop = vp is c["render"]["viewports"][0]
            page = browser.new_page(viewport={"width": vp["width"], "height": vp["height"]})
            page.on("pageerror", lambda e, n=vp["name"]: js_errors.append(f"{n}：{e}"))
            page.goto(HTML.as_uri())
            page.wait_for_timeout(600)
            if desktop:
                got = page.eval_on_selector_all("section.slide", "els => els.map(e => e.dataset.slide)")
                order_ok = got == expected_ids
                checks.append(item("頁數與順序和稿一致", order_ok, f"HTML：{got}" if not order_ok else f"{len(got)} 頁",
                                   "結構缺段", "N7"))
                for need in ("prev", "next"):
                    if not page.query_selector(f'[data-nav="{need}"]'):
                        nav_bad.setdefault("按鈕", []).append(f"缺少 data-nav={need}（手機需要）")
            (SHOTS / vp["name"]).mkdir(parents=True, exist_ok=True)

            for s in slides:
                sid = s["id"]
                cur = page.evaluate(JS_CURRENT)
                if cur != sid:
                    nav_bad.setdefault(vp["name"], []).append(f"預期 {sid}，畫面是 {cur}")
                    break
                info = page.evaluate(JS_INSPECT, sid)
                page.screenshot(path=str(SHOTS / vp["name"] / f"{sid}.png"))
                if info["over"]:
                    over_bad.setdefault(sid, []).append(f"{vp['name']}：{'、'.join(info['over'])}")

                if desktop:
                    body = norm(info["body"])
                    expect = [s.get("title", "")] + [b.get("text", "") for b in s.get("blocks", [])]
                    for q in s.get("quiz", []):
                        expect += [q.get("question", "")] + [o.get("text", "") for o in q.get("options", [])]
                    expect = [e for e in expect if e.strip()]
                    missing = [e[:15] for e in expect if norm(e) not in body]
                    if missing:
                        text_bad.append(f"{sid}：{missing}")
                    rest = body
                    for e in sorted(expect, key=len, reverse=True):
                        rest = rest.replace(norm(e), "")
                    rest = rest.replace(norm(sp_label), "")
                    if char_count(rest) > c["render"]["extra_chars_max"]:
                        extra_bad.append(f"{sid}：多出「{rest[:30]}」")
                    allowed = year_aliases(set().union(*[numbers(e) for e in expect]) if expect else set())
                    extra_num = numbers(info["body"]) - allowed
                    if extra_num:
                        num_bad.append(f"{sid}：{sorted(extra_num)}")
                    n_sup = sum(1 for b in s.get("blocks", []) if b.get("type") == "supplement")
                    if info["supplements"] != n_sup or info["body"].count(sp_label) < n_sup:
                        sup_bad.append(f"{sid}：應有 {n_sup} 則補充並標示「{sp_label}」")
                    want = sorted(s.get("sources", []))
                    got_src = sorted(l["text"] for l in info["sources"])
                    if got_src != want or not all(_link_ok(l, base, pages_by_name, l["text"]) for l in info["sources"]):
                        src_bad.append(f"{sid}：應為 {want}，HTML 為 {got_src}")
                    if info["notesVisible"]:
                        notes_bad.append(sid)

                for q in s.get("quiz", []):
                    qid = q.get("id")
                    before = page.evaluate(JS_ANSWER, qid)
                    if before is None or not before["exists"]:
                        quiz_bad.append(f"{sid}/{qid}：找不到 data-quiz 或 data-answer")
                        continue
                    if desktop and before["visible"]:
                        quiz_bad.append(f"{sid}/{qid}：還沒作答就顯示解答")
                    correct = [o["text"] for o in q["options"] if o.get("correct")][0]
                    opt = page.locator(f'[data-quiz="{qid}"] [data-option][data-correct="true"]')
                    if opt.count() != 1 or norm(correct) not in norm(opt.first.inner_text()):
                        quiz_bad.append(f"{sid}/{qid}：data-correct 標記的選項和稿的正解不同")
                        continue
                    opt.first.click()
                    page.wait_for_timeout(300)
                    after = page.evaluate(JS_ANSWER, qid)
                    if not after["visible"]:
                        quiz_bad.append(f"{sid}/{qid}（{vp['name']}）：點選後沒有顯示解答")
                        continue
                    if desktop:
                        if norm(q.get("answer", "")) not in norm(after["text"]):
                            quiz_bad.append(f"{sid}/{qid}：解答文字和稿不同")
                        want = sorted(dict.fromkeys(cards[k]["page"] for k in q.get("q_cards", []) + q.get("a_cards", []) if k in cards))
                        got_q = sorted(l["text"] for l in after["sources"])
                        if got_q != want or not all(_link_ok(l, base, pages_by_name, l["text"]) for l in after["sources"]):
                            quiz_src_bad.append(f"{sid}/{qid}：解答出處應為 {want}，HTML 為 {got_q}")
                    page.screenshot(path=str(SHOTS / vp["name"] / f"{sid}_{qid}_answer.png"))
                    info2 = page.evaluate(JS_INSPECT, sid)
                    if info2["over"]:
                        over_bad.setdefault(sid, []).append(f"{vp['name']} 顯示解答後：{'、'.join(info2['over'])}")

                page.keyboard.press("ArrowRight")
                page.wait_for_timeout(450)
            page.close()
        browser.close()

    checks.append(item("鍵盤翻頁與翻頁按鈕", not nav_bad,
                       "；".join(f"{k}：{'、'.join(v)}" for k, v in nav_bad.items()), "結構缺段", "N7"))
    checks.append(item("沒有 JS 錯誤", not js_errors, "、".join(js_errors[:5]), "結構缺段", "N7"))
    over_slides = sorted(over_bad)
    origin = "N5" if over_slides and set(over_slides) & repeat_over else "N7"
    checks.append(item("文字不溢出（桌機 1280×720、手機 390×844）", not over_bad,
                       "；".join(f"{k} {'／'.join(v)}" for k, v in over_bad.items())
                       + ("（同一頁連續兩輪溢出 → 退回 N5 濃縮）" if origin == "N5" else ""),
                       "版面溢出", origin, over_slides))
    checks.append(item("HTML 文字和稿一致", not text_bad, "缺少：" + "、".join(text_bad) if text_bad else "",
                       "扭曲原意", "N7", [x.split("：")[0] for x in text_bad]))
    checks.append(item(f"沒有多出稿以外的文字（容許 {c['render']['extra_chars_max']} 字裝飾）", not extra_bad,
                       "、".join(extra_bad), "扭曲原意", "N7", [x.split("：")[0] for x in extra_bad]))
    checks.append(item("沒有多出稿以外的數字", not num_bad, "、".join(num_bad), "數字不符", "N7",
                       [x.split("：")[0] for x in num_bad]))
    checks.append(item("補充有標示", not sup_bad, "、".join(sup_bad), "補充違規", "N7",
                       [x.split("：")[0] for x in sup_bad]))
    checks.append(item("每頁來源列正確且可連到 wiki", not src_bad, "、".join(src_bad), "缺來源", "N7",
                       [x.split("：")[0] for x in src_bad]))
    checks.append(item("講者備註預設隱藏", not notes_bad, f"{notes_bad}" if notes_bad else "", "結構缺段", "N7", notes_bad))
    quiz_bad = list(dict.fromkeys(quiz_bad))
    checks.append(item("測驗可點選並顯示解答", not quiz_bad, "、".join(quiz_bad), "結構缺段", "N7",
                       [x.split("/")[0] for x in quiz_bad]))
    checks.append(item("測驗解答顯示出處", not quiz_src_bad, "、".join(quiz_src_bad), "缺來源", "N7",
                       [x.split("/")[0] for x in quiz_src_bad]))

    if not base.startswith(("http://", "https://")):
        broken = sorted({rel for rel in pages_by_name.values()
                         if f'data-wiki-path="{rel}"' in raw and not (HTML.parent / unquote(base + rel)).exists()})
        checks.append(item("相對路徑連結指向存在的檔案", not broken, f"找不到：{broken}" if broken else "", "缺來源", "N7"))
    return checks


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()
    finish("N8", run(), WORK / "08_render_check.json", log=not a.no_log)


if __name__ == "__main__":
    main()

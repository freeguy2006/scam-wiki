"""局部重跑：大退回時只重做受影響的證據卡與頁面，其他頁不動。

用法：
  python checks/impact.py snapshot --from N6 --reason "E12 把日均寫成單月"
        把目前的 03/04/05/deck.html 存到 work/prev/，建立空的重跑範圍
        （加 --open-outline：退回 N1/N0 時，大綱可以自由調整，等 N4 通過後再用 affected 鎖定頁面）
  python checks/impact.py add --cards E12            加入要重做的卡片（自動加入引用它的頁面）
  python checks/impact.py add --slides S06           加入要重寫的頁面
  python checks/impact.py affected                   比對 prev 與目前的證據卡、大綱，自動算出受影響頁面
  python checks/impact.py show                       顯示目前範圍
  python checks/impact.py clear                      交件前確認通過後清除

檢查腳本（check_evidence / outline / slides / render）在範圍存在時，會確認範圍外的內容和 prev 完全相同。
"""
import argparse
import shutil
from datetime import datetime

from common import (DECK, PREV, SCOPE_FILE, WORK, load_json, parse_outline, save_json,
                    slide_cards, utf8_stdout)

FILES = [WORK / "03_evidence.json", WORK / "04_outline.md", WORK / "05_slides.json", DECK / "deck.html"]


def _prev_slides():
    p = PREV / "05_slides.json"
    return load_json(p)["slides"] if p.exists() else []


def _citing(card_ids):
    """引用這些卡片的頁面（看 prev 的逐頁稿與目前的大綱）。"""
    ids = set(card_ids)
    hit = {s["id"] for s in _prev_slides() if ids & set(slide_cards(s))}
    if (WORK / "04_outline.md").exists():
        hit |= {s["id"] for s in parse_outline((WORK / "04_outline.md").read_text("utf-8")) if ids & set(s["cards"])}
    return hit


def _save(scope):
    prev = _prev_slides()
    if scope.get("slides") is not None and prev:
        scope["untouched"] = len(prev) - len(set(scope["slides"]) & {s["id"] for s in prev})
    save_json(SCOPE_FILE, scope)
    show(scope)


def show(scope=None):
    scope = scope or (load_json(SCOPE_FILE) if SCOPE_FILE.exists() else None)
    if not scope:
        print("目前沒有重跑範圍（全部照常生成）")
        return
    slides = "（大綱開放調整中）" if scope.get("slides") is None else (scope["slides"] or "（無）")
    print(f"重跑範圍：來自 {scope['from']}，原因：{scope['reason']}")
    print(f"  卡片：{scope['cards'] or '（無）'}")
    print(f"  頁面：{slides}")
    if scope.get("untouched") is not None:
        print(f"  不動的頁面：{scope['untouched']} 頁")


def cmd_snapshot(a):
    if PREV.exists():
        shutil.rmtree(PREV)
    PREV.mkdir(parents=True)
    saved = []
    for f in FILES:
        if f.exists():
            shutil.copy2(f, PREV / f.name)
            saved.append(f.name)
    print(f"已存快照：{saved}")
    _save({"from": a.from_, "reason": a.reason, "cards": [],
           "slides": None if a.open_outline else [],
           "created": datetime.now().astimezone().isoformat(timespec="seconds")})


def _load():
    if not SCOPE_FILE.exists():
        raise SystemExit("沒有重跑範圍：請先 snapshot")
    return load_json(SCOPE_FILE)


def cmd_add(a):
    scope = _load()
    cards = sorted(set(scope["cards"]) | set(a.cards or []))
    slides = set(scope["slides"] or []) | set(a.slides or []) | _citing(a.cards or [])
    scope["cards"], scope["slides"] = cards, sorted(slides)
    _save(scope)


def cmd_affected(a):
    scope = _load()
    changed = set(scope["cards"])
    if (PREV / "03_evidence.json").exists() and (WORK / "03_evidence.json").exists():
        old = {k["id"]: k for k in load_json(PREV / "03_evidence.json")["cards"]}
        new = {k["id"]: k for k in load_json(WORK / "03_evidence.json")["cards"]}
        changed |= {i for i in old if new.get(i) != old[i]}
    slides = set(scope["slides"] or []) | _citing(changed)
    if (PREV / "04_outline.md").exists() and (WORK / "04_outline.md").exists():
        old = {s["id"]: s["raw"] for s in parse_outline((PREV / "04_outline.md").read_text("utf-8"))}
        new = {s["id"]: s["raw"] for s in parse_outline((WORK / "04_outline.md").read_text("utf-8"))}
        slides |= {i for i in set(old) | set(new) if old.get(i) != new.get(i)}
    scope["cards"], scope["slides"] = sorted(changed), sorted(slides)
    _save(scope)


def cmd_clear(a):
    if SCOPE_FILE.exists():
        SCOPE_FILE.unlink()
    if PREV.exists():
        shutil.rmtree(PREV)
    print("已清除重跑範圍與快照")


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("snapshot")
    p.add_argument("--from", dest="from_", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--open-outline", action="store_true")
    p.set_defaults(f=cmd_snapshot)
    p = sub.add_parser("add"); p.add_argument("--cards", nargs="*"); p.add_argument("--slides", nargs="*"); p.set_defaults(f=cmd_add)
    p = sub.add_parser("affected"); p.set_defaults(f=cmd_affected)
    p = sub.add_parser("show"); p.set_defaults(f=lambda a: show())
    p = sub.add_parser("clear"); p.set_defaults(f=cmd_clear)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()

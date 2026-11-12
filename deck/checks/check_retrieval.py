"""N2 覆蓋率關卡：檢查 N1 的 work/01_retrieval.json，輸出 work/02_coverage.json。

用法：python checks/check_retrieval.py [--no-log]
"""
import argparse

from common import WORK, cfg, finish, item, load_json, utf8_stdout, wiki_pages


def run():
    c = cfg()
    pages = wiki_pages()
    checks = []
    try:
        data = load_json(WORK / "01_retrieval.json")
        segs = {s["id"]: s.get("pages", []) for s in data["segments"]}
    except Exception as e:  # noqa: BLE001
        return [item("檔案格式", False, f"無法讀取 01_retrieval.json：{e}", "結構缺段", "N1")], {}
    checks.append(item("檔案格式", True))

    need = [s for s in c["segments"] if "retrieval_min_pages" in s]
    missing_seg = [s["id"] for s in need if s["id"] not in segs]
    checks.append(item("教學段落齊全", not missing_seg,
                       f"缺少段落：{missing_seg}" if missing_seg else f"{[s['id'] for s in need]}",
                       "結構缺段", "N1"))

    bad = []
    for sid, plist in segs.items():
        for p in plist:
            name = p.get("page")
            if name not in pages:
                bad.append(f"{sid}/{name}（不存在）")
            elif p.get("path") and p["path"] != pages[name]:
                bad.append(f"{sid}/{name}（路徑應為 {pages[name]}）")
    checks.append(item("頁面都存在", not bad, "、".join(bad), "缺來源", "N1"))

    coverage = {}
    short = []
    for s in need:
        found = [p["page"] for p in segs.get(s["id"], []) if p.get("page") in pages]
        found = list(dict.fromkeys(found))
        coverage[s["id"]] = {"pages": found, "count": len(found), "min": s["retrieval_min_pages"]}
        if len(found) < s["retrieval_min_pages"]:
            short.append(f"{s['name']} {len(found)}/{s['retrieval_min_pages']}")
    checks.append(item("每段頁數足夠", not short,
                       "不足：" + "、".join(short) if short else "；".join(f"{k} {v['count']} 頁" for k, v in coverage.items()),
                       "覆蓋不足", "N1"))

    tactics = [p for p in coverage.get("tactics", {}).get("pages", []) if pages[p].startswith("wiki/手法/")]
    checks.append(item(f"手法至少 {c['tactics_min_distinct']} 種", len(tactics) >= c["tactics_min_distinct"],
                       f"目前 {len(tactics)} 種：{'、'.join(tactics)}", "覆蓋不足", "N1"))

    all_selected = {p.get("page") for plist in segs.values() for p in plist}
    lack = [p for p in c["required_pages"] if p not in all_selected]
    checks.append(item("必含頁面", not lack, f"缺少：{'、'.join(lack)}" if lack else "、".join(c["required_pages"]),
                       "覆蓋不足", "N1"))
    return checks, coverage


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()
    checks, coverage = run()
    finish("N2", checks, WORK / "02_coverage.json", log=not a.no_log, extra={"coverage": coverage})


if __name__ == "__main__":
    main()

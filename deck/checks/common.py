"""各檢查腳本共用的路徑、設定、文字正規化與檔案解析。"""
import json
import re
import sys
import unicodedata
from pathlib import Path

DECK = Path(__file__).resolve().parent.parent
REPO = DECK.parent
WIKI = REPO / "wiki"
WORK = DECK / "work"
PREV = WORK / "prev"
LOGS = DECK / "logs"
SCOPE_FILE = WORK / "rerun_scope.json"

NODE_ORDER = ["N0", "U0", "N1", "N2", "N3", "N4", "U4", "N5", "N6", "N7", "N8", "U9", "N9"]
CARD_ID = re.compile(r"^E\d{2,3}$")
SLIDE_ID = re.compile(r"^S\d{2}[a-z]?$")


def utf8_stdout():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass


def cfg():
    return json.loads((DECK / "config.json").read_text("utf-8"))


def load_json(path):
    return json.loads(Path(path).read_text("utf-8"))


def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


# ---------- 文字正規化 ----------

WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def plain(s):
    """去掉 wiki 連結與 markdown 粗體標記，保留顯示文字。"""
    s = WIKILINK.sub(lambda m: m.group(2) or m.group(1), s)
    return s.replace("**", "").replace("`", "")


def norm(s):
    """比對用：去 markdown、NFKC（全形轉半形）、去掉所有空白。"""
    s = unicodedata.normalize("NFKC", plain(s))
    return re.sub(r"\s+", "", s)


# 千分位只認「逗號後剛好 3 位數」，避免「第 3，12–17 歲」被黏成 312
NUM = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
ROC_YEAR = re.compile(r"(?<![\d.])(1[01]\d)\s*年")
ROC_WITH_AD = re.compile(r"(?<![\d.])(1[01]\d)\s*年\s*[(]\s*(\d{4})\s*[)]")


def numbers(s):
    """抽出阿拉伯數字（去千分位、去小數尾零）。國字數字不在檢查範圍。"""
    out = set()
    for n in NUM.findall(unicodedata.normalize("NFKC", s)):
        n = n.replace(",", "")
        if "." in n:
            n = n.rstrip("0").rstrip(".")
        out.add(n)
    return out


NUM_UNIT = re.compile(rf"({NUM.pattern})\s*([%％一-鿿])")


def numbers_with_unit(s):
    """數字連同緊接的單位字（6.29分鐘→「6.29分」、47 億→「47億」），避免「6 月」和「6%」被當成同一個數。"""
    out = set()
    for n, u in NUM_UNIT.findall(unicodedata.normalize("NFKC", s)):
        out.add(n.replace(",", "") + u)
    return out


def year_aliases(nums):
    """民國年與西元年互相視為同一個數字（114 ⇄ 2025）。"""
    extra = set()
    for n in nums:
        if n.isdigit():
            v = int(n)
            if 100 <= v <= 119:
                extra.add(str(v + 1911))
            elif 2011 <= v <= 2030:
                extra.add(str(v - 1911))
    return nums | extra


def roc_year_problems(text):
    """民國年必須附西元，且換算正確。回傳問題描述清單。"""
    t = unicodedata.normalize("NFKC", text)
    problems = []
    annotated = set()
    for m in ROC_WITH_AD.finditer(t):
        annotated.add(m.start())
        roc, ad = int(m.group(1)), int(m.group(2))
        if roc + 1911 != ad:
            problems.append(f"「{m.group(0)}」換算錯誤，應為 {roc + 1911}")
    for m in ROC_YEAR.finditer(t):
        if m.start() not in annotated:
            problems.append(f"「{m.group(0)}」沒有附西元")
    return problems


def char_count(s):
    return len(re.sub(r"\s+", "", s))


# ---------- wiki ----------

def wiki_pages():
    """頁面名稱 → 相對於 repo 的路徑（wiki/手法/假網拍.md）。"""
    pages = {}
    for p in WIKI.rglob("*.md"):
        if p.name in ("index.md", "log.md"):
            continue
        pages[p.stem] = p.relative_to(REPO).as_posix()
    return pages


def wiki_sections(path):
    """## 標題 → 該段全文（含底下的 ### 小節）。"""
    text = (REPO / path).read_text("utf-8")
    sections, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m and not line.startswith("###"):
            cur = m.group(1)
            sections[cur] = []
        elif cur is not None:
            sections[cur].append(line)
    return {k: "\n".join(v) for k, v in sections.items()}


CASE_HINT = re.compile(r"案例|被騙[^。\n]{0,8}\d")


def has_case(path):
    """手法頁有沒有具體案例：出現「案例」字樣，或「被騙 400 萬餘元」這類金額描述。"""
    return bool(CASE_HINT.search((REPO / path).read_text("utf-8")))


def table_rows(path):
    """wiki 頁面裡的表格列 → [(第一欄, 第二欄, 整列原文)]，跳過表頭與分隔列。"""
    rows = []
    lines = (REPO / path).read_text("utf-8").splitlines()
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= set("-: "):
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if re.match(r"^\s*\|[\s:|-]+\|\s*$", nxt):  # 下一列是分隔列 → 這列是表頭
            continue
        rows.append((cells[0], cells[1], line))
    return rows


def link_href(base, wiki_path):
    """wiki/手法/假網拍.md → base + 手法/假網拍.md"""
    rel = wiki_path[len("wiki/"):] if wiki_path.startswith("wiki/") else wiki_path
    return base + rel, rel


# ---------- 大綱 ----------

OUTLINE_HEAD = re.compile(r"^##\s+(S\d{2}[a-z]?)\s*[｜|]\s*(.+?)\s*$")
OUTLINE_FIELD = re.compile(r"^-\s*(段落|目的|卡號|題數)\s*[:：]\s*(.*)$")


def parse_outline(text):
    slides, cur = [], None
    for line in text.splitlines():
        m = OUTLINE_HEAD.match(line)
        if m:
            cur = {"id": m.group(1), "title": m.group(2), "segment": None,
                   "purpose": "", "cards": [], "quiz": 0, "raw": [line]}
            slides.append(cur)
            continue
        if cur is None:
            continue
        cur["raw"].append(line)
        f = OUTLINE_FIELD.match(line.strip())
        if not f:
            continue
        key, val = f.groups()
        if key == "段落":
            cur["segment"] = val.strip()
        elif key == "目的":
            cur["purpose"] = val.strip()
        elif key == "卡號":
            cur["cards"] = re.findall(r"E\d{2,3}", val)
        elif key == "題數":
            d = re.search(r"\d+", val)
            cur["quiz"] = int(d.group()) if d else 0
    for s in slides:
        s["raw"] = "\n".join(l.rstrip() for l in s["raw"]).strip()
    return slides


# ---------- 逐頁稿 ----------

def slide_cards(slide):
    """一頁引用到的全部卡號（區塊＋測驗）。"""
    ids = []
    for b in slide.get("blocks", []):
        ids += b.get("cards", [])
    for q in slide.get("quiz", []):
        ids += q.get("q_cards", []) + q.get("a_cards", [])
    return list(dict.fromkeys(ids))


# ---------- 局部重跑範圍 ----------

def load_scope():
    if SCOPE_FILE.exists():
        return load_json(SCOPE_FILE)
    return None


# ---------- 檢查結果 ----------

def item(name, ok, detail="", error_type=None, origin=None, slides=None):
    d = {"item": name, "pass": bool(ok)}
    if detail:
        d["detail"] = detail
    if not ok:
        d["error_type"] = error_type
        d["origin"] = origin
        if slides:
            d["slides"] = sorted(set(slides))
    return d


def finish(node, checks, out_path, log=True, extra=None):
    """寫出檢查結果，並（預設）追加到 logs/events.jsonl。"""
    result = "pass" if all(c["pass"] for c in checks) else "fail"
    data = {"node": node, "checker": "script", "result": result, "checks": checks}
    if extra:
        data.update(extra)
    save_json(out_path, data)
    print(f"[{node}] 程式檢查：{'通過' if result == 'pass' else '不通過'}（{out_path.relative_to(DECK).as_posix()}）")
    for c in checks:
        mark = "✓" if c["pass"] else "✗"
        line = f"  {mark} {c['item']}"
        if c.get("detail"):
            line += f"：{c['detail']}"
        print(line)
    if log:
        import log_event
        log_event.record(node=node, checker="script", checks=checks, result=result)
    return result

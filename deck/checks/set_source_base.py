"""更改來源列連結的開頭網址（例如之後放到 GitHub），不必重新渲染。

用法：
  python checks/set_source_base.py --base "https://github.com/<帳號>/<repo>/blob/main/wiki/"
  python checks/set_source_base.py --base "../wiki/"          改回相對路徑

會更新 config.json 的 source_base_url，並依每個連結的 data-wiki-path 改寫 deck.html 的 href。
改完請再跑一次 python checks/check_render.py 確認。
"""
import argparse
import re

from common import DECK, WORK, link_href, load_json, save_json, utf8_stdout


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    base = ap.parse_args().base
    if not base.endswith("/"):
        base += "/"

    cfg_path = DECK / "config.json"
    text = cfg_path.read_text("utf-8")
    text = re.sub(r'("source_base_url"\s*:\s*)"[^"]*"', lambda m: f'{m.group(1)}"{base}"', text, count=1)
    cfg_path.write_text(text, "utf-8")
    print(f"config.json：source_base_url = {base}")

    html_path = DECK / "deck.html"
    if html_path.exists():
        html = html_path.read_text("utf-8")
        html = re.sub(r'(<html[^>]*data-source-base=)(["\'])[^"\']*\2', lambda m: f"{m.group(1)}\"{base}\"", html, count=1)
        n = 0

        def fix(m):
            nonlocal n
            tag = m.group(0)
            path = re.search(r'data-wiki-path=["\']([^"\']+)', tag)
            if not path:
                return tag
            n += 1
            href = base + path.group(1)
            if re.search(r'\shref=', tag):
                return re.sub(r'\shref=(["\'])[^"\']*\1', f' href="{href}"', tag, count=1)
            return tag[:-1] + f' href="{href}">'

        html = re.sub(r"<a\b[^>]*>", fix, html)
        html_path.write_text(html, "utf-8")
        print(f"deck.html：改寫 {n} 個連結")

    links_path = WORK / "05_links.json"
    if links_path.exists():
        links = load_json(links_path)
        links["source_base_url"] = base
        for v in links["pages"].values():
            v["href"], _ = link_href(base, v["wiki_path"])
        save_json(links_path, links)


if __name__ == "__main__":
    main()

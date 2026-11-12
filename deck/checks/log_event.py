"""執行紀錄：每次檢查追加一行到 logs/events.jsonl，並依 config 決定下一步。

用法：
  python checks/log_event.py start [--note 說明]       開始一次執行（產生 run_id）
  python checks/log_event.py review work/06_faithfulness.json   記錄 AI 審查結果
  python checks/log_event.py human --node U4 --result fail --routed-to N1 \
         --error-type 覆蓋不足 --reason "缺少假求職"           記錄人工關卡
  python checks/log_event.py status                   目前輪次、大退回次數
  python checks/log_event.py end                      結束執行並產生 logs/run_<id>.md

程式檢查（check_*.py）會自動呼叫 record()，不必手動記錄。
"""
import argparse
import json
from datetime import datetime

from common import LOGS, NODE_ORDER, SCOPE_FILE, cfg, load_json, save_json, utf8_stdout

EVENTS = LOGS / "events.jsonl"
CURRENT = LOGS / "current_run.json"


def _now():
    return datetime.now().astimezone()


def read_events(run_id=None):
    if not EVENTS.exists():
        return []
    rows = [json.loads(l) for l in EVENTS.read_text("utf-8").splitlines() if l.strip()]
    return [r for r in rows if run_id is None or r["run_id"] == run_id]


def current_run():
    if not CURRENT.exists():
        raise SystemExit("尚未開始執行：請先跑 python checks/log_event.py start")
    return load_json(CURRENT)


def loop_of(node, c):
    for name, nodes in c["loops"].items():
        if node in nodes:
            return name
    return None


def _upstream(nodes):
    nodes = [n for n in nodes if n in NODE_ORDER]
    return min(nodes, key=NODE_ORDER.index) if nodes else None


def _signature(checks):
    # 用 list 而不是 tuple：寫進 JSON 再讀回來才比得起來
    return sorted([c["item"], sorted(c.get("slides", []))] for c in checks if not c["pass"])


def _append(ev):
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def record(node, checker, checks, result, routed_to=None, reason=None,
           origin=None, error_types=None, next_node=None):
    c = cfg()
    run = current_run()
    events = read_events(run["run_id"])
    now = _now()
    last_ts = datetime.fromisoformat(events[-1]["timestamp"]) if events else now

    # 最近一次「重設點」（大退回、人工決定）之後，才算同一輪 loop
    reset_at = max((i for i, e in enumerate(events) if e.get("reset")), default=-1)
    since = events[reset_at + 1:]
    loop = loop_of(node, c)

    failed = [x for x in checks if not x["pass"]]
    if error_types is None:
        error_types = list(dict.fromkeys(x["error_type"] for x in failed if x.get("error_type")))
    origins = [x["origin"] for x in failed if x.get("origin")]

    if checker == "human":
        attempt = sum(1 for e in events if e["node"] == node) + 1
    else:
        attempt = sum(1 for e in since if e.get("loop") == loop and e["result"] in ("fail", "escalate")) + 1

    big = False
    escalate_reason = None
    if result == "fail":
        allowed = c["routes"].get(node, [])
        if routed_to is None:
            cands = [o for o in origins if o in allowed]
            routed_to = _upstream(cands) or (allowed[0] if allowed else None)
        elif allowed and routed_to not in allowed:
            raise SystemExit(f"{node} 不能退回 {routed_to}；退回表允許：{allowed}")
        origin = origin or _upstream(origins) or routed_to
        if checker != "human":
            big = loop_of(routed_to, c) != loop
            prev = [e for e in since if e.get("loop") == loop and e["node"] == node
                    and e["result"] in ("fail", "escalate")]
            big_count = sum(1 for e in events if e.get("big_retreat"))
            if attempt >= c["max_rounds_per_loop"]:
                escalate_reason = f"{loop} 第 {attempt} 輪仍不通過（上限 {c['max_rounds_per_loop']} 輪）"
            elif prev and prev[-1].get("signature") == _signature(checks):
                escalate_reason = "和上一輪的問題完全相同（沒有進步）"
            elif big and big_count >= c["max_big_retreats"]:
                escalate_reason = f"大退回已達 {big_count} 次（上限 {c['max_big_retreats']} 次）"
        if escalate_reason:
            result = "escalate"
            big = False
            next_node = "ESC"
        else:
            next_node = next_node or routed_to
    elif result == "pass":
        next_node = next_node or c["next"].get(node)

    if reason is None and failed:
        reason = "；".join(f"{x['item']}：{x.get('detail', '')}".rstrip("：") for x in failed)[:500]
    if escalate_reason:
        reason = f"【卡關求救】{escalate_reason}。{reason or ''}"

    scope = load_json(SCOPE_FILE) if SCOPE_FILE.exists() else None
    ev = {
        "run_id": run["run_id"],
        "graph_version": c["graph_version"],
        "node": node,
        "loop": loop,
        "attempt": attempt,
        "checker": checker,
        "checks": checks,
        "result": result,
        "error_type": error_types if result != "pass" else [],
        "detected_at": node if result != "pass" else None,
        "origin_node": origin if result != "pass" else None,
        "routed_to": routed_to if result != "pass" else None,
        "reason": reason if result != "pass" else (reason or None),
        "rerun_scope": {k: scope[k] for k in ("from", "reason", "cards", "slides", "untouched") if k in scope} if scope else None,
        "big_retreat": big,
        "reset": bool(big or (checker == "human" and result != "pass")),
        "signature": _signature(checks) if result != "pass" else None,
        "next": next_node,
        "timestamp": now.isoformat(timespec="seconds"),
        "duration_s": round((now - last_ts).total_seconds()),
    }
    if node == "ESC":
        # 卡關後的人工決定不是新的錯誤，不計入錯誤類型與發現位置統計
        ev.update(error_type=[], detected_at=None, origin_node=None)
    _append(ev)

    label = {"pass": "通過", "fail": "不通過", "escalate": "卡關求救"}[result]
    print(f"→ 紀錄：{node} 第 {attempt} 輪（{checker}）{label}")
    if result == "fail":
        kind = "大退回" if big else "loop 內重做"
        print(f"→ 下一步：退回 {routed_to}（{kind}；錯誤產生於 {origin}）")
    elif result == "escalate":
        print(f"→ 下一步：暫停，請使用者決定。{escalate_reason}")
    else:
        print(f"→ 下一步：{next_node}")
    return ev


def cmd_start(args):
    c = cfg()
    if CURRENT.exists():
        old = load_json(CURRENT)
        print(f"注意：上一次執行 {old['run_id']} 沒有 end，視為中斷。")
    run_id = _now().strftime("%Y%m%d-%H%M%S")
    save_json(CURRENT, {"run_id": run_id, "graph_version": c["graph_version"],
                        "started": _now().isoformat(timespec="seconds"), "note": args.note})
    _append({"run_id": run_id, "graph_version": c["graph_version"], "node": "RUN",
             "checker": "system", "result": "start", "reason": args.note,
             "timestamp": _now().isoformat(timespec="seconds"), "duration_s": 0})
    print(f"開始執行 {run_id}（graph {c['graph_version']}）")


def cmd_review(args):
    """AI 審查員的輸出 → 檢查項目。格式見 prompts/review_*.md。"""
    data = load_json(args.file)
    checks = []
    for cr in data.get("criteria", []):
        checks.append({"item": cr["item"], "pass": bool(cr.get("pass")), **({"detail": cr["detail"]} if cr.get("detail") else {})})
    for iss in data.get("issues", []):
        d = {"item": f"AI：{iss.get('error_type', '問題')}", "pass": False,
             "detail": iss.get("detail", ""), "error_type": iss.get("error_type"),
             "origin": iss.get("origin")}
        if iss.get("slides") or iss.get("slide"):
            d["slides"] = sorted(set(iss.get("slides") or [iss["slide"]]))
        checks.append(d)
    result = "pass" if data.get("result") == "pass" and all(x["pass"] for x in checks) else "fail"
    record(node=data["node"], checker="ai", checks=checks, result=result)


def cmd_human(args):
    checks = [{"item": f"人工確認（{args.node}）", "pass": args.result == "pass",
               **({"detail": args.reason} if args.reason else {})}]
    if args.result == "fail":
        if not args.reason:
            raise SystemExit("人工退回必須寫 --reason")
        checks[0]["error_type"] = args.error_type
        checks[0]["origin"] = args.origin or args.routed_to
    record(node=args.node, checker="human", checks=checks, result=args.result,
           routed_to=args.routed_to, reason=args.reason, origin=args.origin,
           error_types=[args.error_type] if args.error_type else None, next_node=args.next)


def cmd_status(args):
    c = cfg()
    run = current_run()
    events = read_events(run["run_id"])
    reset_at = max((i for i, e in enumerate(events) if e.get("reset")), default=-1)
    since = events[reset_at + 1:]
    print(f"執行 {run['run_id']}（graph {run['graph_version']}），共 {len(events) - 1} 筆紀錄")
    for loop in c["loops"]:
        n = sum(1 for e in since if e.get("loop") == loop and e["result"] in ("fail", "escalate"))
        print(f"  {loop} {c['loops'][loop]}：目前已失敗 {n} 輪")
    print(f"  大退回：{sum(1 for e in events if e.get('big_retreat'))} 次（上限 {c['max_big_retreats']}）")
    if events:
        print(f"  最後一筆：{events[-1]['node']} {events[-1]['result']} → {events[-1].get('next')}")


def cmd_end(args):
    run = current_run()
    _append({"run_id": run["run_id"], "graph_version": run["graph_version"], "node": "RUN",
             "checker": "system", "result": "end", "reason": args.note,
             "timestamp": _now().isoformat(timespec="seconds"), "duration_s": 0})
    CURRENT.unlink()
    import run_summary
    run_summary.write(run["run_id"])


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start"); p.add_argument("--note", default=None); p.set_defaults(f=cmd_start)
    p = sub.add_parser("review"); p.add_argument("file"); p.set_defaults(f=cmd_review)
    p = sub.add_parser("human")
    p.add_argument("--node", required=True, choices=["U0", "U4", "U9", "ESC"])
    p.add_argument("--result", required=True, choices=["pass", "fail"])
    p.add_argument("--routed-to"); p.add_argument("--origin"); p.add_argument("--next")
    p.add_argument("--error-type", choices=cfg()["error_types"]); p.add_argument("--reason")
    p.set_defaults(f=cmd_human)
    p = sub.add_parser("status"); p.set_defaults(f=cmd_status)
    p = sub.add_parser("end"); p.add_argument("--note", default=None); p.set_defaults(f=cmd_end)
    args = ap.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()

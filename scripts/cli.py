"""DialogMesh CLI — talks to the backend API directly, no frontend."""
import sys, json, urllib.request, os, uuid

BASE = os.environ.get("DM_API", "http://localhost:8000")

def _api(method, path, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()[:500]
        return {"error": f"HTTP {e.code}", "detail": err}
    except Exception as e:
        return {"error": str(e)[:200]}

def cmd_session(cmd, sid=None):
    if cmd == "new":
        sid = str(uuid.uuid4())[:12]
        print(f"session_id: {sid}")
        return sid
    elif cmd == "list":
        # Fetch recent sessions from v6
        r = _api("GET", "/v6/sessions?limit=10")
        for s in r.get("sessions", r.get("data", [])):
            sid = s.get("session_id", s.get("id", "?"))
            title = s.get("title", s.get("messages", [{}])[0].get("content", "")[:40] if s.get("messages") else "(empty)")
            print(f"  {sid[:12]}  {title}")
    elif cmd == "use":
        print(f"Using session: {sid}")
    return None

def cmd_chat(sid, msg):
    print(f"[You] {msg}")
    r = _api("POST", f"/v3/session/{sid}/message", {
        "content": msg,
        "provider": "deepseek",
        "model": "deepseek-v4-flash"
    })
    if "error" in r:
        print(f"[Error] {r['error']}")
        return
    content = r.get("content", "(empty)")
    print(f"[AI] {content}")
    tg = r.get("task_graph")
    if tg:
        print(f"\n  📋 任务规划 ({len(tg)} 步骤):")
        for n in tg:
            deps = ", ".join(n.get("dependencies", [])) or "无"
            print(f"    {n.get('id','?')}. {n.get('name','?')} [依赖: {deps}]")
    return r

def cmd_task(sid, subcmd, *args):
    if subcmd == "show":
        r = _api("GET", f"/v3/session/{sid}/task-graph")
        nodes = r.get("nodes", [])
        edges = r.get("edges", [])
        if not nodes:
            print("  (无任务)")
            return
        print(f"  任务图: {len(nodes)} 节点, {len(edges)} 连线")
        for n in nodes:
            deps = ", ".join(n.get("dependencies", [])) or "—"
            print(f"    [{n.get('id','?')}] {n.get('name','?')}  状态:{n.get('status','?')}  依赖:{deps}")
        if edges:
            print("  连线:")
            for e in edges:
                print(f"    {e['source']} → {e['target']}")
    elif subcmd == "save":
        # Read JSON from stdin or file
        if args:
            with open(args[0]) as f:
                data = json.load(f)
        else:
            data = json.load(sys.stdin)
        r = _api("PUT", f"/v3/session/{sid}/task-graph", {
            "nodes": data.get("nodes", []),
            "edges": data.get("edges", [])
        })
        print(f"  {'✅' if r.get('status') == 'ok' else '❌'} {r.get('status','?')}")
    elif subcmd == "confirm":
        print(f"  ✅ 任务已确认，下次对话 LLM 将收到该任务图并执行")

def cmd_export(sid, path):
    r = _api("GET", f"/v3/session/{sid}/task-graph")
    with open(path, "w") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 导出到 {path}")

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__.strip())
        print("\nCommands:")
        print("  session new                    创建新会话")
        print("  session list                   列出最近会话")
        print("  session use <id>               设置当前会话")
        print("  chat <sid> <msg>               发送消息 (需要 session-id)")
        print("  task show <sid>                查看任务图")
        print("  task save <sid> [file.json]    保存任务图 (从文件或stdin)")
        print("  task confirm <sid>             确认任务图")
        print("  export <sid> <file.json>       导出任务图到文件")
        print()
        print("Example:")
        print("  sid=$(python scripts/cli.py session new)")
        print("  python scripts/cli.py chat $sid '规划一个用户登录系统'")
        print("  python scripts/cli.py task show $sid")
        return

    cmd = args[0]
    if cmd == "session":
        cmd_session(args[1] if len(args) > 1 else "new", args[2] if len(args) > 2 else None)
    elif cmd == "chat":
        if len(args) < 3:
            print("Usage: cli chat <session-id> <message>")
            return
        cmd_chat(args[1], " ".join(args[2:]))
    elif cmd == "task":
        if len(args) < 3:
            print("Usage: cli task <show|save|confirm> <session-id> [file]")
            return
        cmd_task(args[2], args[1], *args[3:])
    elif cmd == "export":
        if len(args) < 3:
            print("Usage: cli export <session-id> <file.json>")
            return
        cmd_export(args[1], args[2])

if __name__ == "__main__":
    main()

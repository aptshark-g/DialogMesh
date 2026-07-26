# PermissionSystem — pledge+unveil+seccomp 权限分级

> 2026-07-25 · 三模式深度融合 · Cap 26位标志 · 4内置profile

---

## 模式吸收

```
pledge(2):   promise reduction only, execpromises, implicit caps
unveil(2):   path whitelist, lock()冻结, **/ glob
seccomp:     param-level filters, kill/trap/errno/log
gVisor:      ConstraintTree as userspace kernel
```

---

## 核心语义

```
Capability (26位):
  pledge: STDIO RPATH WPATH CPATH DPATH FATTR FLOCK TMPSET
  net:    INET INET6 UNIX_ DNS ROUTE
  proc:   PROC EXEC PROT_EXEC
  sys:    ID TTY SETTIME
  agent:  LLM_CALL MCP_INVOKE PERSIST_WRITE USER_INTERRUPT

Promise reduction: can only decrease, never increase
Implicit: wpath→rpath, exec→proc

PathSpace (unveil):
  unveil(path, r/w/rwc) → lock() → frozen
  **/*.py matches auth.py and src/auth.py

SyscallFilter (seccomp):
  allowed_globs/denied_globs → param-level override
  command_prefixes → bash白名单
  BlockAction: KILL/ERRNO/LOG/TRAP

ResourceQuota:
  memory_mb, cpu_seconds, disk_mb, files, connections, llm_tokens, llm_calls

Emergency override:
  grant_emergency(agent, 60s) → expires auto
```

---

## 4 内置 Profile

```
safe_read_agent   STDIO+RPATH+LLM — read *.py/*.yaml/*.json/*.md
code_editor       AGENT_FULL+FILE_MODIFY — edit code files, no /etc
devops_agent      AGENT_FULL+PROC+NET — bash/python/git/docker
llm_only_agent    STDIO+LLM — no FS, no exec, pure reasoning
```

## 接入

```python
profile = AgentProfiles.code_editor()
enforcer = PermissionEnforcer(constraint_tree, event_bus)
allowed, reason = enforcer.enforce(profile, Cap.WPATH,
    {"tool": "edit", "path": "auth.py"}, "editor")
```

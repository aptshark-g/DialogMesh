import os
import time
import json
import fnmatch
from typing import Optional, List, Dict
from flask import Flask, request, jsonify, render_template, render_template_string
from core import state
from core.winapi import (
    OpenProcess, CloseHandle, GetProcessId, PROCESS_ALL_ACCESS,
    suspend_process, resume_process, launch_and_attach,
)
from memory.scanner import first_scan, next_scan, next_scan_general, first_scan_byte_array, first_scan_between, \
    first_scan_unknown, enum_memory_regions
from memory.operations import safe_read, safe_write, fill_scan_value, format_value, read_memory_region, \
    resolve_pointer_chain, enum_process_modules, pointer_scan, start_lock, stop_lock, write_pointer_chain
from memory.watchlist import add_watch, get_watch_list, remove_watch
from analysis.tracker import start_tracking, stop_tracking, add_tracked_address
from analysis.classifier import classify_address
from analysis.causality import calculate_causal_dependency
from disasm.disassembler import disassemble_at, disassemble_region, get_instruction_at, find_pattern
from disasm.breakpoint import (
    set_memory_breakpoint, clear_memory_breakpoint, clear_all_breakpoints,
    get_breakpoint_hits, get_breakpoint_status, scan_nearby_writes,
    trace_data_propagation,
)
from disasm.tracer import start_instruction_trace, stop_instruction_trace, get_trace_log
from core.debugger import Debugger, BP_MODE_WRITE, BP_MODE_READ, BP_MODE_ACCESS
from core.dfg import DFGGraph
from core.ai_assistant import KimiCodePromptGenerator, test_connection as ai_test_connection
from core.intent_agent import IntentAgent, AgentMessage, UserResponse, MessageType, AgentState

# Optional psutil for process enumeration

# Optional psutil for process enumeration
psutil = None
# noinspection PyBroadException
try:
    import psutil
except Exception:
    pass

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
app.config["JSON_SORT_KEYS"] = False

# ── MCP Server Integration ──
from gui.mcp_routes import mcp_bp, init_mcp_server
init_mcp_server(app)
app.register_blueprint(mcp_bp, url_prefix="/mcp")

# 读取前端 HTML
# with open(os.path.join(os.path.dirname(__file__), "templates", "index.html"), "r", encoding="utf-8") as f:
#     HTML_TEMPLATE = f.read()


# CORS跨域处理
@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


# 内嵌完整前端HTML
@app.route("/")
@app.route("/gui.html")
def index():
    return render_template('index.html')


# 基础CE API
@app.route("/api/processes")
def api_processes():
    filter_str = request.args.get("filter", "").lower()
    # Import icon extractor (lazy, no hard dependency on PIL)
    try:
        from core.icon_extractor import get_process_icon_data
    except Exception:
        get_process_icon_data = None

    res = []
    if psutil is not None:
        for p in psutil.process_iter(["pid", "name"]):
            try:
                name = p.info["name"] or ""
                pid = p.info["pid"]
                match = False
                if not filter_str:
                    match = True
                else:
                    if fnmatch.fnmatch(name.lower(), filter_str) or fnmatch.fnmatch(str(pid), filter_str):
                        match = True
                if match:
                    item = {"name": name, "pid": pid}
                    if get_process_icon_data:
                        icon_data = get_process_icon_data(pid)
                        if icon_data:
                            item["icon_base64"] = icon_data["icon_base64"]
                            item["exe_path"] = icon_data["exe_path"]
                    res.append(item)
            except Exception:
                continue
    else:
        res.append({"name": "psutil-not-installed", "pid": 0, "error": "Install psutil for process list"})
    return jsonify(res)


@app.route("/api/attach", methods=["POST"])
def api_attach():
    pid = request.json.get("pid", 0)
    if not pid:
        return jsonify({"status": "error", "message": "invalid pid"})
    if state.g_hProcess:
        CloseHandle(state.g_hProcess)
        state.g_hProcess = None
    # Clear old debugger and DFG when switching processes
    if state.g_debugger:
        try:
            state.g_debugger.stop()
        except Exception:
            pass
        state.g_debugger = None
    state.g_dfg = None
    state.g_scanAddrs.clear()
    state.g_tracked_addrs.clear()
    state.g_taint_events.clear()
    state.g_input_events.clear()
    # Clear old locked addresses and tracking
    state.g_watch.clear()
    state.g_locked_addrs.clear()
    state.g_tracking = False
    h = OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h:
        return jsonify({"status": "error", "message": "attach failed"})
    state.g_hProcess = h
    state.g_pid = pid
    state.g_scanAddrs.clear()
    state.g_tracked_addrs.clear()
    state.g_taint_events.clear()
    state.g_input_events.clear()
    # Clear workflow engine state if exists
    if state.g_workflow_engine:
        state.g_workflow_engine = None
    
    # Clear intent agent session if exists
    global _intent_agent
    if _intent_agent and _intent_agent.state.value != 'done':
        _intent_agent.cancel()
    _intent_agent = None
    
    # 刷新模块缓存
    state.refresh_module_cache(pid)
    
    # Get main module base address for GUI base-addr buttons
    base_addr = None
    try:
        modules = enum_process_modules(pid)
        if modules and len(modules) > 0:
            base_addr = modules[0].get("base_addr")
    except Exception as e:
        print(f"[api_attach] Failed to get module base: {e}")
    
    # Phase 1: also attach DLL engine if available
    if state.g_use_dll:
        state.attach_dll(pid)
    
    resp = {"status": "ok"}
    if base_addr:
        resp["base_addr"] = f"0x{base_addr:x}"
    
    # Create project record in MemoryStore for persistence
    try:
        store = state.get_memory_store()
        if store:
            # Get process name from modules
            proc_name = "unknown"
            try:
                mods = enum_process_modules(pid)
                if mods:
                    proc_name = mods[0].get("name", "unknown")
            except Exception:
                pass
            project_id = f"{proc_name}_{pid}"
            store.create_project(project_id, proc_name, pid=pid)
            resp["project_id"] = project_id
    except Exception as e:
        print(f"[api_attach] MemoryStore project creation failed: {e}")
    
    return jsonify(resp)


@app.route("/api/launch", methods=["POST"])
def api_launch():
    """Launch a new target process and attach automatically."""
    data = request.json or {}
    exe_path = data.get("exe_path", "").strip()
    args = data.get("args", "")
    working_dir = data.get("working_dir", "")
    
    if not exe_path:
        return jsonify({"status": "error", "message": "exe_path required"})
    if not os.path.exists(exe_path):
        return jsonify({"status": "error", "message": f"file not found: {exe_path}"})
    
    # Detach existing process
    if state.g_hProcess:
        CloseHandle(state.g_hProcess)
        state.g_hProcess = None
    # Clear old debugger and DFG when switching processes
    if state.g_debugger:
        try:
            state.g_debugger.stop()
        except Exception:
            pass
        state.g_debugger = None
    state.g_dfg = None
    state.g_scanAddrs.clear()
    state.g_tracked_addrs.clear()
    state.g_taint_events.clear()
    state.g_input_events.clear()
    # Clear old locked addresses and tracking
    state.g_watch.clear()
    state.g_locked_addrs.clear()
    state.g_tracking = False
    # Clear workflow engine state if exists
    if state.g_workflow_engine:
        state.g_workflow_engine = None
    
    try:
        hProc, pid = launch_and_attach(
            exe_path,
            args=args,
            working_dir=working_dir if working_dir else None,
        )
        state.g_hProcess = hProc
        state.g_pid = pid
        
        # 刷新模块缓存
        state.refresh_module_cache(pid)
        
        # Attach DLL engine if available
        if state.g_use_dll:
            state.attach_dll(pid)
        
        # Get main module base address for GUI base-addr buttons
        base_addr = None
        try:
            modules = enum_process_modules(pid)
            if modules and len(modules) > 0:
                base_addr = modules[0].get("base_addr")
        except Exception as e:
            print(f"[api_launch] Failed to get module base: {e}")
        
        resp = {
            "status": "ok",
            "pid": pid,
            "exe_path": exe_path,
            "message": f"Launched and attached PID={pid}",
        }
        if base_addr:
            resp["base_addr"] = f"0x{base_addr:x}"
        
        # Create project record in MemoryStore for persistence
        try:
            store = state.get_memory_store()
            if store:
                proc_name = os.path.basename(exe_path)
                project_id = f"{proc_name}_{pid}"
                store.create_project(project_id, proc_name, pid=pid, exe_path=exe_path)
                resp["project_id"] = project_id
        except Exception as e:
            print(f"[api_launch] MemoryStore project creation failed: {e}")
        
        return jsonify(resp)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/regions", methods=["GET"])
def api_regions():
    """Enumerate memory regions in the attached process."""
    if not state.g_hProcess:
        return jsonify({"status": "error", "message": "no process attached"})
    addr_min = request.args.get("addr_min", None, type=int)
    addr_max = request.args.get("addr_max", None, type=int)
    # Default to 0x10000 if not provided (request.args.get with None default returns None)
    if addr_min is None:
        addr_min = 0x10000
    if addr_max is None:
        import sys
        addr_max = 0x7FFF00000000 if sys.maxsize > 2**32 else 0x7FFFFFFE
    regions = enum_memory_regions(state.g_hProcess, addr_min, addr_max)
    # Return only committed + readable regions for brevity, or all if requested
    show_all = request.args.get("all", "0") == "1"
    if not show_all:
        regions = [r for r in regions if r["committed"] and r["readable"]]
    # Limit to first 200 to avoid huge JSON
    return jsonify({
        "status": "ok",
        "count": len(regions),
        "regions": regions[:200],
    })


@app.route("/api/scan/first", methods=["POST"])
def api_first_scan():
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    typ = request.json.get("type", 2)
    val = request.json.get("value", "")
    addr_min = request.json.get("addr_min")
    addr_max = request.json.get("addr_max")
    if addr_min is not None:
        addr_min = int(addr_min, 16) if isinstance(addr_min, str) else addr_min
    if addr_max is not None:
        addr_max = int(addr_max, 16) if isinstance(addr_max, str) else addr_max
    if not val:
        return jsonify({"error": "value required"})
    first_scan(typ, val)
    results = []
    for a in state.g_scanAddrs[:500]:
        d = safe_read(a, state.g_dataSize)
        v = format_value(d, state.g_scanType) if d else "???"
        results.append({"address": f"{a:#x}", "value": v})
    return jsonify({
        "status": "ok",
        "count": len(state.g_scanAddrs),
        "results": results
    })


@app.route("/api/scan/next", methods=["POST"])
def api_next_scan():
    if not state.g_hProcess or not state.g_scanAddrs:
        return jsonify({"error": "no results"})
    val = request.json.get("value", "")
    next_scan(val)
    results = []
    for a in state.g_scanAddrs[:500]:
        d = safe_read(a, state.g_dataSize)
        v = format_value(d, state.g_scanType) if d else "???"
        results.append({"address": f"{a:#x}", "value": v})
    return jsonify({
        "status": "ok",
        "count": len(state.g_scanAddrs),
        "results": results
    })


@app.route("/api/results")
def api_results():
    res = []
    # 确保模块缓存已刷新
    if state.g_pid and not state.g_module_lookup:
        state.refresh_module_cache(state.g_pid)
    
    for a in state.g_scanAddrs[:500]:
        d = safe_read(a, state.g_dataSize)
        v = format_value(d, state.g_scanType) if d else "???"
        
        # 获取模块信息
        mod_info = state.get_module_info_for_address(a) if state.g_module_lookup else None
        if mod_info:
            addr_display = f"{mod_info['name']}+0x{mod_info['offset']:X}"
            module_name = mod_info['name']
            module_offset = mod_info['offset']
        else:
            addr_display = f"0x{a:08X}"
            module_name = None
            module_offset = None
        
        res.append({
            "address": f"{a:#x}",
            "address_display": addr_display,
            "module_name": module_name,
            "module_offset": f"0x{module_offset:X}" if module_offset is not None else None,
            "value": v
        })
    return jsonify({"results": res})


@app.route("/api/modify", methods=["POST"])
def api_modify():
    addr_str = request.json.get("address", "")
    val_str = request.json.get("value", "")
    try:
        addr = int(addr_str, 16)
    except:
        return jsonify({"status": "error"})
    data, _ = fill_scan_value(val_str, state.g_scanType)
    if safe_write(addr, data):
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"})


@app.route("/api/watch", methods=["POST"])
def api_add_watch():
    addr_str = request.json.get("address", "")
    try:
        addr = int(addr_str, 16)
    except:
        return jsonify({"status": "error"})
    if add_watch(addr):
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"})


@app.route("/api/watch")
def api_get_watch():
    return jsonify({"watch": get_watch_list()})


@app.route("/api/watch/remove", methods=["POST"])
def api_remove_watch():
    idx = request.json.get("index", -1)
    if remove_watch(idx):
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"})


# 未知初始值首次扫描
@app.route("/api/scan/first/unknown", methods=["POST"])
def api_first_scan_unknown():
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    typ = request.json.get("type", 2)
    first_scan_unknown(typ)
    results = []
    for a in state.g_scanAddrs[:500]:
        d = safe_read(a, state.g_dataSize)
        v = format_value(d, state.g_scanType) if d else "???"
        results.append({"address": f"{a:#x}", "value": v})
    return jsonify({
        "status": "ok",
        "count": len(state.g_scanAddrs),
        "results": results
    })


# 范围扫描
@app.route("/api/scan/first/between", methods=["POST"])
def api_first_scan_between():
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    typ = request.json.get("type", 2)
    min_val = request.json.get("min", "")
    max_val = request.json.get("max", "")
    if not min_val or not max_val:
        return jsonify({"error": "min and max value required"})
    first_scan_between(typ, min_val, max_val)
    results = []
    for a in state.g_scanAddrs[:500]:
        d = safe_read(a, state.g_dataSize)
        v = format_value(d, state.g_scanType) if d else "???"
        results.append({"address": f"{a:#x}", "value": v})
    return jsonify({
        "status": "ok",
        "count": len(state.g_scanAddrs),
        "results": results
    })


# 字节数组/特征码扫描
@app.route("/api/scan/first/bytearray", methods=["POST"])
def api_first_scan_bytearray():
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    hex_str = request.json.get("hex", "")
    if not hex_str:
        return jsonify({"error": "hex string required"})
    first_scan_byte_array(hex_str)
    results = []
    for a in state.g_scanAddrs[:500]:
        results.append({"address": f"{a:#x}"})
    return jsonify({
        "status": "ok",
        "count": len(state.g_scanAddrs),
        "results": results
    })


# 通用再次扫描（变动/未变动/增减）
@app.route("/api/scan/next/general", methods=["POST"])
def api_next_scan_general():
    if not state.g_hProcess or not state.g_scanAddrs:
        return jsonify({"error": "no results"})
    scan_mode = request.json.get("mode", state.SCAN_TYPE_CHANGED)
    value_str = request.json.get("value", "")
    min_str = request.json.get("min", "")
    max_str = request.json.get("max", "")
    next_scan_general(scan_mode, value_str=value_str, min_str=min_str, max_str=max_str)
    results = []
    for a in state.g_scanAddrs[:500]:
        d = safe_read(a, state.g_dataSize)
        v = format_value(d, state.g_scanType) if d else "???"
        results.append({"address": f"{a:#x}", "value": v})
    return jsonify({
        "status": "ok",
        "count": len(state.g_scanAddrs),
        "results": results
    })

# 枚举进程模块
@app.route("/api/modules")
def api_modules():
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    pid = GetProcessId(state.g_hProcess)
    modules = enum_process_modules(pid)
    return jsonify({"modules": modules})

# 指针扫描 (Phase 2: DLL accelerated with 64-bit range)
@app.route("/api/scan/pointer", methods=["POST"])
def api_pointer_scan():
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    target_addr_str = request.json.get("address", "")
    max_level = request.json.get("max_level", 3)
    max_offset = request.json.get("max_offset", 0x1000)
    addr_min_str = request.json.get("addr_min", "0x10000")
    addr_max_str = request.json.get("addr_max", "0x7FFFFFFE")
    try:
        target_addr = int(target_addr_str, 16)
        addr_min = int(addr_min_str, 16) if isinstance(addr_min_str, str) else addr_min_str
        addr_max = int(addr_max_str, 16) if isinstance(addr_max_str, str) else addr_max_str
    except:
        return jsonify({"error": "invalid address"})
    pid = GetProcessId(state.g_hProcess)
    results = pointer_scan(target_addr, max_level=max_level, max_offset=max_offset, pid=pid)
    return jsonify({
        "status": "ok",
        "count": len(results),
        "results": results[:100]
    })

# 解析指针链
@app.route("/api/pointer/resolve", methods=["POST"])
def api_resolve_pointer():
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    module_name = request.json.get("module", "")
    base_offset = request.json.get("base_offset", 0)
    offsets = request.json.get("offsets", [])
    pid = GetProcessId(state.g_hProcess)
    modules = enum_process_modules(pid)
    # 找到模块基址 (heap 时 base_offset 就是绝对地址)
    base_addr = None
    if module_name.lower() == "heap":
        base_addr = base_offset
    else:
        for mod in modules:
            if mod["name"].lower() == module_name.lower():
                base_addr = mod["base_addr"] + base_offset
                break
    if not base_addr:
        return jsonify({"error": "module not found"})
    # 解析指针链
    final_addr = resolve_pointer_chain(base_addr, offsets)
    if not final_addr:
        return jsonify({"error": "resolve failed"})
    # 读取当前值
    d = safe_read(final_addr, state.g_dataSize)
    v = format_value(d, state.g_scanType) if d else "???"
    return jsonify({
        "status": "ok",
        "address": f"{final_addr:#x}",
        "value": v
    })

# 通过指针链写入 (Phase 3)
@app.route("/api/pointer/write", methods=["POST"])
def api_pointer_write():
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    module_name = request.json.get("module", "")
    base_offset = request.json.get("base_offset", 0)
    offsets = request.json.get("offsets", [])
    value_str = request.json.get("value", "")
    try:
        base_offset = int(base_offset) if isinstance(base_offset, str) else base_offset
    except:
        return jsonify({"error": "invalid base_offset"})
    pid = GetProcessId(state.g_hProcess)
    modules = enum_process_modules(pid)
    base_addr = None
    if module_name.lower() == "heap":
        base_addr = base_offset
    else:
        for mod in modules:
            if mod["name"].lower() == module_name.lower():
                base_addr = mod["base_addr"] + base_offset
                break
    if not base_addr:
        return jsonify({"error": "module not found"})
    data, _ = fill_scan_value(value_str, state.g_scanType)
    if not data:
        return jsonify({"error": "invalid value"})
    if write_pointer_chain(base_addr, offsets, data):
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"})

# 内存查看器 API
@app.route("/api/memory/view", methods=["POST"])
def api_memory_view():
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})

    try:
        start_hex = request.json.get("start", "0x0")
        count = int(request.json.get("count", 256))
        data_type = int(request.json.get("type", state.g_scanType))

        start_addr = int(start_hex, 16)
    except Exception as e:
        return jsonify({"error": str(e)})

    _, sz = fill_scan_value("0", data_type)
    total_bytes = count * sz

    raw_bytes = read_memory_region(start_addr, total_bytes)

    if not raw_bytes:
        return jsonify({"error": "read failed"})

    results = []
    offset = 0
    for i in range(count):
        addr = start_addr + i * sz
        chunk = raw_bytes[offset: offset + sz]
        offset += sz

        val_str = "???"
        if len(chunk) == sz:
            val_str = format_value(chunk, data_type)

        results.append({
            "address": f"{addr:#x}",
            "value": val_str,
            "raw": list(chunk)
        })

    return jsonify({
        "start": start_hex,
        "type": data_type,
        "size": sz,
        "data": results
    })


@app.route("/api/status")
def api_status():
    if not state.g_hProcess:
        return jsonify({"attached": False})
    pid = GetProcessId(state.g_hProcess)
    import sys, platform
    status = {
        "attached": True,
        "pid": pid,
        "python_bits": 64 if sys.maxsize > 2**32 else 32,
        "platform": platform.machine(),
    }
    # Try to determine target process bit-width (Windows-specific)
    try:
        from ctypes import windll, c_int, c_void_p, byref, sizeof
        import ctypes
        # IsWow64Process: if target is 32-bit on 64-bit Windows, returns True
        # If target is 64-bit, returns False (or function not available on 32-bit Windows)
        IsWow64Process = windll.kernel32.IsWow64Process
        IsWow64Process.argtypes = [c_void_p, ctypes.POINTER(ctypes.c_int)]
        IsWow64Process.restype = c_int
        is_wow64 = ctypes.c_int(0)
        if IsWow64Process(state.g_hProcess, byref(is_wow64)):
            status["target_is_wow64"] = bool(is_wow64.value)
            status["target_bits"] = 32 if is_wow64.value else 64
        else:
            status["target_bits"] = 32 if sys.maxsize <= 2**32 else 64
    except Exception as e:
        status["target_bits_error"] = str(e)
    return jsonify(status)

# 启动地址锁定
@app.route("/api/lock/start", methods=["POST"])
def api_start_lock():
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    addr_str = request.json.get("address", "")
    value_str = request.json.get("value", "")
    typ = request.json.get("type", state.g_scanType)
    interval = request.json.get("interval", 0.1)
    try:
        addr = int(addr_str, 16)
    except:
        return jsonify({"error": "invalid address"})
    if start_lock(addr, value_str, typ, interval):
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"})

# 停止地址锁定
@app.route("/api/lock/stop", methods=["POST"])
def api_stop_lock():
    addr_str = request.json.get("address", "")
    try:
        addr = int(addr_str, 16)
    except:
        return jsonify({"error": "invalid address"})
    if stop_lock(addr):
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"})

# 获取锁定列表
@app.route("/api/lock")
def api_get_lock():
    res = []
    for item in state.g_locked_addrs:
        res.append({
            "address": f"{item['address']:#x}",
            "type": item["type"],
            "interval": item["interval"]
        })
    return jsonify({"lock": res})

# MemoryGraph API
@app.route("/api/track/add", methods=["POST"])
def api_add_track():
    addr_str = request.json.get("address", "")
    try:
        addr = int(addr_str, 16)
    except:
        return jsonify({"status": "error"})
    count = add_tracked_address(addr, state.g_scanType)
    return jsonify({"status": "ok", "count": count})


@app.route("/api/track/start", methods=["POST"])
def api_start_track():
    if not state.g_hProcess:
        return jsonify({"status": "error", "message": "no process attached"})
    if start_tracking():
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "already tracking"})


@app.route("/api/track/stop", methods=["POST"])
def api_stop_track():
    stop_tracking()

    nodes = []
    for i, item in enumerate(state.g_tracked_addrs):
        category, features = classify_address(item)
        item.category = category
        item.features = features
        nodes.append({
            "id": i,
            "address": f"{item.address:#x}",
            "category": category,
            "features": features,
            "timestamps": list(item.timestamps),
            "values": list(item.values)
        })

    edges = []
    for i in range(len(state.g_tracked_addrs)):
        for j in range(len(state.g_tracked_addrs)):
            if i == j:
                continue
            corr, delay = calculate_causal_dependency(state.g_tracked_addrs[i], state.g_tracked_addrs[j])
            if abs(corr) > 0.7:
                edges.append({
                    "source": i,
                    "target": j,
                    "source_addr": f"{state.g_tracked_addrs[i].address:#x}",
                    "target_addr": f"{state.g_tracked_addrs[j].address:#x}",
                    "correlation": float(corr),
                    "delay": delay
                })

    return jsonify({
        "status": "ok",
        "nodes": nodes,
        "edges": edges,
        "taint_events": state.g_taint_events,
        "input_events": state.g_input_events
    })


# 污点注入（简化版）
@app.route("/api/track/taint", methods=["POST"])
def api_taint():
    addr_str = request.json.get("address", "")
    new_value = request.json.get("value", "")
    try:
        addr = int(addr_str, 16)
    except:
        return jsonify({"status": "error"})

    # 简化实现：直接写入值并记录事件
    old_data = safe_read(addr, state.g_dataSize)
    data, _ = fill_scan_value(str(new_value), state.g_scanType)
    if safe_write(addr, data):
        import time
        state.g_taint_events.append({
            "timestamp": int(time.perf_counter() * 1000),
            "address": addr,
            "old_value": format_value(old_data, state.g_scanType) if old_data else "???",
            "new_value": str(new_value)
        })
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"})

# 暂停进程
@app.route("/api/process/suspend", methods=["POST"])
def api_suspend_process():
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    threads = suspend_process(state.g_hProcess)
    if not threads:
        return jsonify({"status": "error", "message": "no threads found, or already suspended"})
    # 保存线程 handle 以便恢复
    state._suspended_threads = threads
    return jsonify({"status": "ok", "threads": len(threads)})

# 恢复进程
@app.route("/api/process/resume", methods=["POST"])
def api_resume_process():
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    threads = getattr(state, '_suspended_threads', [])
    if threads:
        resume_process(threads)
        state._suspended_threads = []
    return jsonify({"status": "ok"})

# ══════════════════════════════════════════════════════════
# 反汇编 API (disasm)
# ══════════════════════════════════════════════════════════

@app.route("/api/disasm", methods=["POST"])
def api_disasm():
    """反汇编指定地址的指令"""
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    addr_str = request.json.get("address", "0x0")
    count = request.json.get("count", 20)
    is_64bit = request.json.get("is64", False)
    try:
        addr = int(addr_str, 16)
    except ValueError:
        return jsonify({"error": "invalid address"})
    results = disassemble_at(addr, count=count, is_64bit=is_64bit)
    return jsonify({"status": "ok", "count": len(results), "instructions": results})


@app.route("/api/disasm/region", methods=["POST"])
def api_disasm_region():
    """反汇编指定地址范围的指令"""
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    start_str = request.json.get("start", "0x0")
    end_str = request.json.get("end", "0x100")
    is_64bit = request.json.get("is64", False)
    try:
        start = int(start_str, 16)
        end = int(end_str, 16)
    except ValueError:
        return jsonify({"error": "invalid address"})
    results = disassemble_region(start, end, is_64bit=is_64bit)
    return jsonify({"status": "ok", "count": len(results), "instructions": results})


@app.route("/api/disasm/instruction", methods=["POST"])
def api_disasm_instruction():
    """获取单条指令详情"""
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    addr_str = request.json.get("address", "0x0")
    is_64bit = request.json.get("is64", False)
    try:
        addr = int(addr_str, 16)
    except ValueError:
        return jsonify({"error": "invalid address"})
    insn = get_instruction_at(addr, is_64bit=is_64bit)
    if not insn:
        return jsonify({"error": "read failed"})
    return jsonify({"status": "ok", "instruction": insn})


@app.route("/api/disasm/pattern", methods=["POST"])
def api_disasm_pattern():
    """特征码/字节模式搜索"""
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    hex_pattern = request.json.get("pattern", "")
    start_str = request.json.get("start", "0x00400000")
    end_str = request.json.get("end", "0x7FFFFFFF")
    try:
        start = int(start_str, 16)
        end = int(end_str, 16)
    except ValueError:
        return jsonify({"error": "invalid address"})
    if not hex_pattern:
        return jsonify({"error": "pattern required"})
    results = find_pattern(hex_pattern, start=start, end=end)
    return jsonify({
        "status": "ok",
        "count": len(results),
        "results": [f"{r:#x}" for r in results[:200]]
    })


# ══════════════════════════════════════════════════════════
# 内存断点 API (breakpoint)
# ══════════════════════════════════════════════════════════

@app.route("/api/breakpoint/set", methods=["POST"])
def api_set_breakpoint():
    """设置内存断点（找写入/读取）"""
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    addr_str = request.json.get("address", "")
    size = request.json.get("size", 4)
    mode = request.json.get("mode", "write")  # write / read / rw
    try:
        addr = int(addr_str, 16)
    except ValueError:
        return jsonify({"error": "invalid address"})
    if set_memory_breakpoint(addr, size=size, mode=mode):
        return jsonify({"status": "ok", "message": f"breakpoint set at {addr:#x}"})
    return jsonify({"status": "error", "message": "set failed"})


@app.route("/api/breakpoint/clear", methods=["POST"])
def api_clear_breakpoint():
    """清除内存断点"""
    addr_str = request.json.get("address", "")
    try:
        addr = int(addr_str, 16)
    except ValueError:
        return jsonify({"error": "invalid address"})
    if clear_memory_breakpoint(addr):
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "not found"})


@app.route("/api/breakpoint/clear_all", methods=["POST"])
def api_clear_all_breakpoints():
    """清除所有断点"""
    clear_all_breakpoints()
    return jsonify({"status": "ok"})


@app.route("/api/breakpoint/hits")
def api_breakpoint_hits():
    """获取断点命中日志"""
    hits = get_breakpoint_hits(limit=50)
    return jsonify({"hits": hits, "count": len(hits)})


@app.route("/api/breakpoint/status")
def api_breakpoint_status():
    """获取所有断点状态"""
    status = get_breakpoint_status()
    return jsonify({"breakpoints": status, "count": len(status)})


@app.route("/api/breakpoint/scan_writes", methods=["POST"])
def api_scan_nearby_writes():
    """扫描目标地址附近可能写入的指令"""
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    addr_str = request.json.get("address", "")
    search_range = request.json.get("range", 0x1000)
    is_64bit = request.json.get("is64", False)
    try:
        addr = int(addr_str, 16)
    except ValueError:
        return jsonify({"error": "invalid address"})
    results = scan_nearby_writes(addr, search_range=search_range, is_64bit=is_64bit)
    return jsonify({"status": "ok", "count": len(results), "instructions": results})


@app.route("/api/breakpoint/trace_propagation", methods=["POST"])
def api_trace_propagation():
    """追踪数据传播链"""
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    addr_str = request.json.get("address", "")
    depth = request.json.get("depth", 3)
    is_64bit = request.json.get("is64", False)
    try:
        addr = int(addr_str, 16)
    except ValueError:
        return jsonify({"error": "invalid address"})
    results = trace_data_propagation(addr, depth=depth, is_64bit=is_64bit)
    return jsonify({"status": "ok", "count": len(results), "chains": results})


# ══════════════════════════════════════════════════════════
# 指令追踪 API (tracer)
# ══════════════════════════════════════════════════════════

@app.route("/api/trace/start", methods=["POST"])
def api_start_trace():
    """启动指令级追踪"""
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    addr_str = request.json.get("address", "")
    start_addr = None
    if addr_str:
        try:
            start_addr = int(addr_str, 16)
        except ValueError:
            pass
    if start_instruction_trace(start_addr):
        return jsonify({"status": "ok", "message": "instruction tracing started"})
    return jsonify({"status": "error", "message": "failed to start"})


@app.route("/api/trace/stop", methods=["POST"])
def api_stop_trace():
    """停止指令追踪并返回结果"""
    result = stop_instruction_trace()
    return jsonify({"status": "ok", **result})


@app.route("/api/trace/log")
def api_trace_log():
    """获取当前追踪日志"""
    limit = request.args.get("limit", 200, type=int)
    log = get_trace_log(limit=limit)
    return jsonify({"log": log, "count": len(log)})


# ══════════════════════════════════════════════════════════
# 批量追踪 (便捷接口)
# ══════════════════════════════════════════════════════════

@app.route("/api/track/add_batch", methods=["POST"])
def api_add_track_batch():
    """批量添加时序追踪地址"""
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    addresses = request.json.get("addresses", [])
    added = 0
    for addr_str in addresses:
        try:
            addr = int(addr_str, 16)
            add_tracked_address(addr, state.g_scanType)
            added += 1
        except ValueError:
            continue
    return jsonify({"status": "ok", "added": added})


# ══════════════════════════════════════════════════════════
# Phase 4: Debugger API (C++ DLL engine)
# ══════════════════════════════════════════════════════════

@app.route("/api/debugger/start", methods=["POST"])
def api_debugger_start():
    """Start C++ debugger (DebugActiveProcess)"""
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    if not state.g_use_dll or not state.g_mg_handle:
        return jsonify({"error": "DLL engine not available"})
    try:
        if not state.g_debugger:
            state.g_debugger = Debugger(state.g_mg_handle)
        if not state.g_dfg:
            state.g_dfg = DFGGraph()
        state.g_debugger.start()
        return jsonify({"status": "ok", "message": "debugger started"})
    except Exception as e:
        err_str = str(e)
        # Add diagnostic hints based on common error patterns
        diagnostics = []
        if "err=-2" in err_str or "attach" in err_str.lower():
            diagnostics.append("Most likely cause: 32-bit vs 64-bit mismatch. "
                "The debugger must match the target process bit-width. "
                "Check: (1) Is Python running in the same bit-width as the target process? "
                "(2) Is mg_engine.dll compiled for the correct architecture (x86/x64)?")
            diagnostics.append("Other possible causes: target process already has a debugger attached, "
                "insufficient privileges (run as Admin), or the process is protected (UWP/anti-cheat).")
        import sys
        import platform
        return jsonify({
            "status": "error",
            "message": err_str,
            "diagnostics": diagnostics,
            "python_bits": 64 if sys.maxsize > 2**32 else 32,
            "platform": platform.machine(),
        })


@app.route("/api/debugger/stop", methods=["POST"])
def api_debugger_stop():
    """Stop C++ debugger"""
    if state.g_debugger:
        state.g_debugger.stop()
        state.g_debugger = None
    return jsonify({"status": "ok"})


@app.route("/api/debugger/breakpoint/set", methods=["POST"])
def api_debugger_bp_set():
    """Set hardware/guard-page breakpoint via C++ engine"""
    if not state.g_hProcess:
        return jsonify({"error": "no process attached"})
    if not state.g_debugger:
        return jsonify({"error": "debugger not started"})
    addr_str = request.json.get("address", "")
    size = request.json.get("size", 4)
    mode_str = request.json.get("mode", "write")  # write / read / access
    try:
        addr = int(addr_str, 16)
    except ValueError:
        return jsonify({"error": "invalid address"})
    mode_map = {"write": BP_MODE_WRITE, "read": BP_MODE_READ, "access": BP_MODE_ACCESS}
    mode = mode_map.get(mode_str, BP_MODE_WRITE)
    try:
        if mode_str == "access":
            state.g_debugger.set_access_watchpoint(addr, size)
        elif mode_str == "read":
            state.g_debugger.set_read_watchpoint(addr, size)
        else:
            state.g_debugger.set_write_watchpoint(addr, size)
        # Phase 6: add variable node to DFG
        if state.g_dfg:
            state.g_dfg.add_scan_result(addr, value=None, size=size)
        return jsonify({"status": "ok", "message": f"breakpoint set at {addr:#x}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/debugger/breakpoint/clear", methods=["POST"])
def api_debugger_bp_clear():
    """Clear a breakpoint"""
    if not state.g_debugger:
        return jsonify({"status": "ok"})
    addr_str = request.json.get("address", "")
    try:
        addr = int(addr_str, 16)
    except ValueError:
        return jsonify({"error": "invalid address"})
    state.g_debugger.clear_breakpoint(addr)
    return jsonify({"status": "ok"})


@app.route("/api/debugger/breakpoint/clear_all", methods=["POST"])
def api_debugger_bp_clear_all():
    """Clear all breakpoints"""
    if state.g_debugger:
        state.g_debugger.clear_all()
    return jsonify({"status": "ok"})


@app.route("/api/debugger/hits")
def api_debugger_hits():
    """Get breakpoint hit log (RIP + value) and sync to DFG"""
    if not state.g_debugger:
        return jsonify({"hits": [], "count": 0})
    # Phase 6 fix: sync_hits_to_dfg uses watched_addr from hit record directly
    if state.g_dfg and state.g_debugger:
        state.g_debugger.sync_hits_to_dfg()
    hits = state.g_debugger.get_hits(max_count=200)
    return jsonify({"hits": hits, "count": len(hits)})


@app.route("/api/debugger/status")
def api_debugger_status():
    """Get active breakpoint status"""
    if not state.g_debugger:
        return jsonify({"breakpoints": [], "count": 0, "active": False})
    status = state.g_debugger.get_status(max_count=100)
    return jsonify({"breakpoints": status, "count": len(status), "active": True})


# ══════════════════════════════════════════════════════════
# Phase 5: Deobfuscation / Unpacking API
# ══════════════════════════════════════════════════════════

@app.route("/api/deobfuscator/analyze_protection", methods=["POST"])
def api_analyze_protection():
    """Analyze PE protection: packers, entropy, anti-debug, junk code."""
    data = request.json or {}
    pe_path = data.get("pe_path", "")
    module_addr = data.get("module_addr", "")

    deob = state.get_deobfuscator()
    if not deob or not deob.is_available():
        return jsonify({"status": "error", "message": "Deobfuscator not available. Check pefile installation."})

    base_addr = 0
    size = 0
    if module_addr:
        parts = module_addr.split(":")
        if len(parts) >= 2:
            try:
                base_addr = int(parts[0], 16) if parts[0].startswith("0x") else int(parts[0])
                size = int(parts[1])
            except ValueError:
                return jsonify({"status": "error", "message": f"Invalid module_addr: {module_addr}"})

    profile = deob.analyze_protection(
        pe_path=pe_path or None,
        process_handle=state.g_hProcess,
        base_addr=base_addr,
        size=size,
    )

    if not profile:
        return jsonify({"status": "ok", "message": "No protection detected or analysis failed."})

    return jsonify({
        "status": "ok",
        "is_packed": profile.is_packed,
        "packer_name": profile.packer_name,
        "entropy": profile.entropy,
        "has_antidebug": profile.has_antidebug,
        "has_junk_code": profile.has_junk_code,
        "signatures": [s.name for s in profile.signatures],
        "warnings": profile.warnings,
    })


@app.route("/api/deobfuscator/unpack", methods=["POST"])
def api_unpack_module():
    """Unpack a packed module (UPX tool or memory dump)."""
    data = request.json or {}
    pe_path = data.get("pe_path", "")
    module_addr = data.get("module_addr", "")

    deob = state.get_deobfuscator()
    if not deob or not deob.is_available():
        return jsonify({"status": "error", "message": "Deobfuscator not available."})

    base_addr = 0
    size = 0
    if module_addr:
        parts = module_addr.split(":")
        if len(parts) >= 2:
            try:
                base_addr = int(parts[0], 16) if parts[0].startswith("0x") else int(parts[0])
                size = int(parts[1])
            except ValueError:
                return jsonify({"status": "error", "message": f"Invalid module_addr: {module_addr}"})

    unpacked = deob.unpack_module(
        process_handle=state.g_hProcess,
        base_addr=base_addr,
        size=size,
        pe_path=pe_path or None,
    )

    if not unpacked or not unpacked.is_unpacked:
        return jsonify({
            "status": "error",
            "message": "Unpack failed. Check if module is packed or if upx is installed.",
        })

    return jsonify({
        "status": "ok",
        "method": unpacked.method,
        "oep": f"0x{unpacked.oep:08X}",
        "image_base": f"0x{unpacked.image_base:08X}",
        "data_size": len(unpacked.data),
        "warnings": unpacked.warnings,
    })


@app.route("/api/deobfuscator/deobfuscate", methods=["POST"])
def api_deobfuscate_code():
    """Detect and remove junk code from a memory region."""
    data = request.json or {}
    start_addr_str = data.get("start_addr", "")
    size = data.get("size", 0x1000)
    arch = data.get("arch", "x86_64")

    if not start_addr_str:
        return jsonify({"status": "error", "message": "start_addr required"})

    try:
        addr = int(start_addr_str, 16) if start_addr_str.startswith("0x") else int(start_addr_str)
    except ValueError:
        return jsonify({"status": "error", "message": f"Invalid start_addr: {start_addr_str}"})

    if not state.g_hProcess:
        return jsonify({"status": "error", "message": "No process attached"})

    from memory.operations import safe_read
    code = safe_read(addr, size)
    if not code or len(code) < 4:
        return jsonify({"status": "error", "message": f"Failed to read {size} bytes at 0x{addr:08X}"})

    deob = state.get_deobfuscator()
    if not deob or not deob.is_available():
        return jsonify({"status": "error", "message": "Deobfuscator not available."})

    result = deob.deobfuscate_code(code, start_addr=addr, arch=arch)
    if not result:
        return jsonify({"status": "ok", "message": "No junk code detected."})

    return jsonify({
        "status": "ok",
        "junk_blocks_found": len(result["junk_blocks"]),
        "removed_size": result["removed_size"],
        "original_size": len(result["original"]),
        "clean_size": len(result["clean"]),
        "blocks": [
            {"addr": f"0x{b.addr:08X}", "size": b.size, "pattern": b.pattern_name}
            for b in result["junk_blocks"]
        ],
    })


@app.route("/api/deobfuscator/bypass_antidebug", methods=["POST"])
def api_bypass_antidebug():
    """Detect and bypass anti-debug techniques."""
    data = request.json or {}
    module_addr = data.get("module_addr", "")

    if not module_addr:
        return jsonify({"status": "error", "message": "module_addr required (format: base:size)"})

    parts = module_addr.split(":")
    if len(parts) < 2:
        return jsonify({"status": "error", "message": "module_addr format must be 'base:size'"})

    try:
        base_addr = int(parts[0], 16) if parts[0].startswith("0x") else int(parts[0])
        size = int(parts[1])
    except ValueError:
        return jsonify({"status": "error", "message": f"Invalid module_addr: {module_addr}"})

    if not state.g_hProcess or base_addr == 0 or size == 0:
        return jsonify({"status": "error", "message": "No process attached or invalid module address"})

    deob = state.get_deobfuscator()
    if not deob or not deob.is_available():
        return jsonify({"status": "error", "message": "Deobfuscator not available."})

    result = deob.bypass_antidebug(state.g_hProcess, base_addr, size)
    if not result:
        return jsonify({"status": "error", "message": "Anti-debug bypass failed."})

    return jsonify({
        "status": "ok",
        "techniques_detected": len(result["techniques"]),
        "techniques": [
            {"name": t.name, "confidence": t.confidence, "addresses": [f"0x{a:08X}" for a in t.addresses]}
            for t in result["techniques"]
        ],
        "bypass_results": result["bypass_results"],
    })


# ══════════════════════════════════════════════════════════
# Phase 6: Data Flow Graph (DFG) API
# ══════════════════════════════════════════════════════════

@app.route("/api/dfg/build", methods=["POST"])
def api_dfg_build():
    """Build DFG from current debugger hits and scan results"""
    if not state.g_dfg:
        state.g_dfg = DFGGraph()
    # Add scan results to DFG
    for addr in state.g_scanAddrs:
        state.g_dfg.add_scan_result(addr, value=None, size=state.g_dataSize)
    # Sync debugger hits (Phase 6 fix: auto-group by watched_addr)
    if state.g_debugger:
        state.g_debugger.sync_hits_to_dfg()
    return jsonify({"status": "ok", "stats": state.g_dfg.to_echarts()["stats"]})


@app.route("/api/dfg/graph")
def api_dfg_graph():
    """Get DFG as ECharts Graph data"""
    if not state.g_dfg:
        return jsonify({"nodes": [], "edges": [], "categories": [], "stats": {"node_count": 0, "edge_count": 0}})
    return jsonify(state.g_dfg.to_echarts())


@app.route("/api/dfg/report")
def api_dfg_report():
    """Get DFG structured reverse engineering report"""
    if not state.g_dfg:
        return jsonify({"variables": [], "instructions": [], "stats": {}})
    return jsonify(state.g_dfg.to_report())


@app.route("/api/dfg/variable/<addr_hex>")
def api_dfg_variable(addr_hex):
    """Get all instructions that access a specific variable"""
    if not state.g_dfg:
        return jsonify({"dependencies": []})
    try:
        addr = int(addr_hex, 16)
    except ValueError:
        return jsonify({"error": "invalid address"})
    deps = state.g_dfg.get_variable_dependencies(addr)
    return jsonify({"address": addr_hex, "dependencies": deps})


@app.route("/api/dfg/instruction/<rip_hex>")
def api_dfg_instruction(rip_hex):
    """Get all variables accessed by a specific instruction"""
    if not state.g_dfg:
        return jsonify({"accesses": []})
    try:
        rip = int(rip_hex, 16)
    except ValueError:
        return jsonify({"error": "invalid rip"})
    accesses = state.g_dfg.get_instruction_accesses(rip)
    call_chain = state.g_dfg.get_call_chain(rip)
    return jsonify({"rip": rip_hex, "accesses": accesses, "call_chain": [hex(a) for a in call_chain]})


@app.route("/api/dfg/reset", methods=["POST"])
def api_dfg_reset():
    """Reset DFG"""
    state.g_dfg = DFGGraph()
    return jsonify({"status": "ok"})


# ══════════════════════════════════════════════════════════
# Phase 6: DFG / Angr CFG Integration API
# ══════════════════════════════════════════════════════════

@app.route("/api/dfg/import_cfg", methods=["POST"])
def api_dfg_import_cfg():
    """Import Angr CFG into DFG."""
    data = request.json or {}
    binary_path = data.get("binary_path", "")
    base_addr_str = data.get("base_addr", "")
    function_start_str = data.get("function_start", "")

    if not state.g_dfg:
        state.g_dfg = DFGGraph()

    bridge = state.get_angr_bridge()
    if not bridge or not bridge.is_available():
        return jsonify({"status": "error", "message": "Angr not available. Install: pip install angr"})

    if not bridge.project and binary_path:
        base_addr = None
        if base_addr_str:
            try:
                base_addr = int(base_addr_str, 16) if base_addr_str.startswith("0x") else int(base_addr_str)
            except ValueError:
                return jsonify({"status": "error", "message": f"Invalid base_addr: {base_addr_str}"})
        ok = bridge.load_pe(binary_path, base_addr=base_addr)
        if not ok:
            return jsonify({"status": "error", "message": f"Failed to load binary: {binary_path}"})

    if not bridge.project:
        return jsonify({"status": "error", "message": "No binary loaded. Provide binary_path or call angr_build_cfg first."})

    func_start = None
    if function_start_str:
        try:
            func_start = int(function_start_str, 16) if function_start_str.startswith("0x") else int(function_start_str)
        except ValueError:
            return jsonify({"status": "error", "message": f"Invalid function_start: {function_start_str}"})

    cfg_result = bridge.build_cfg(function_start=func_start)
    if not cfg_result:
        return jsonify({"status": "error", "message": "Angr CFG build failed."})

    stats = state.g_dfg.import_cfg_from_angr(cfg_result)
    return jsonify({
        "status": "ok",
        "imported": stats,
        "dfg_nodes": len(state.g_dfg.nodes),
        "dfg_edges": len(state.g_dfg.edges),
    })


@app.route("/api/dfg/compare_cfg", methods=["POST"])
def api_dfg_compare_cfg():
    """Compare DFG with Angr CFG."""
    data = request.json or {}
    binary_path = data.get("binary_path", "")
    base_addr_str = data.get("base_addr", "")

    if not state.g_dfg:
        return jsonify({"status": "error", "message": "DFG not built. Call /api/dfg/build or /api/dfg/import_cfg first."})

    bridge = state.get_angr_bridge()
    if not bridge or not bridge.is_available():
        return jsonify({"status": "error", "message": "Angr not available. Install: pip install angr"})

    if not bridge.project and binary_path:
        base_addr = None
        if base_addr_str:
            try:
                base_addr = int(base_addr_str, 16) if base_addr_str.startswith("0x") else int(base_addr_str)
            except ValueError:
                return jsonify({"status": "error", "message": f"Invalid base_addr: {base_addr_str}"})
        bridge.load_pe(binary_path, base_addr=base_addr)

    if not bridge.project:
        return jsonify({"status": "error", "message": "No binary loaded. Provide binary_path or call angr_build_cfg first."})

    cfg_result = bridge.build_cfg()
    if not cfg_result:
        return jsonify({"status": "error", "message": "Angr CFG build failed."})

    comparison = state.g_dfg.compare_with_angr_cfg(cfg_result)
    summary = state.g_dfg.get_comparison_summary()

    return jsonify({
        "status": "ok",
        "summary": summary,
        "confirmed_edges": len(comparison.confirmed_edges),
        "static_only_edges": len(comparison.static_only_edges),
        "dynamic_only_edges": len(comparison.dynamic_only_edges),
        "anomalies": comparison.anomalous_dataflow[:10],
    })


@app.route("/api/dfg/anomalies")
def api_dfg_anomalies():
    """Find anomalous dataflow paths in DFG."""
    if not state.g_dfg:
        return jsonify({"status": "error", "message": "DFG not built."})

    anomalies = state.g_dfg.find_anomalous_dataflow()
    return jsonify({
        "status": "ok",
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    })


# ============================================================
# Phase 7: Automated Reverse Engineering Pipeline Routes
# ============================================================

# Global pipeline reference (in-memory only, per-process)
_auto_pipeline = None

@app.route("/api/auto-reverse/start", methods=["POST"])
def api_auto_reverse_start():
    """Start automated reverse engineering pipeline."""
    from core.reverse_pipeline import ReversePipeline, PipelineConfig
    
    global _auto_pipeline
    
    if not state.g_hProcess:
        return jsonify({"status": "error", "message": "No process attached"})
    
    data = request.json or {}
    strategy = data.get("strategy", "general")
    duration = data.get("duration", 30)
    max_bp = data.get("max_breakpoints", 4)
    max_gp = data.get("max_guard_pages", 8)
    
    # Build scan results from current state
    scan_results = []
    for addr in state.g_scanAddrs[:100]:
        d = safe_read(addr, state.g_dataSize)
        v = format_value(d, state.g_scanType) if d else "???"
        scan_results.append({"address": addr, "value": v, "type": state.g_scanType})
    
    pipeline = ReversePipeline(debugger=state.get_debugger())
    pipeline.config.strategy = strategy
    pipeline.config.collection_duration = duration
    pipeline.config.max_breakpoints = max_bp
    pipeline.config.max_guard_pages = max_gp
    pipeline.config.auto_generate_ai = True
    
    # Progress callback to update status (no-op for now, frontend polls)
    def on_progress(data):
        pass
    pipeline.on_progress = on_progress
    
    result = pipeline.start({
        "strategy": strategy,
        "scan_results": scan_results,
        "duration": duration,
        "blocking": False,
        "auto_ai": True,
    })
    
    if not result.get("success"):
        return jsonify({"status": "error", "message": result.get("error", "Unknown error")})
    
    _auto_pipeline = pipeline
    
    return jsonify({
        "status": "ok",
        "stage": "collecting",
        "selected": result.get("selected", []),
        "selected_count": len(result.get("selected", [])),
        "duration": duration,
        "message": f"Collecting data for {duration}s",
    })


@app.route("/api/auto-reverse/status")
def api_auto_reverse_status():
    """Get current automated reverse pipeline status."""
    global _auto_pipeline
    
    if _auto_pipeline is None:
        return jsonify({"stage": "idle", "message": "No active pipeline"})
    
    status = _auto_pipeline.get_status()
    
    # If collection is complete, try to finalize automatically
    if status.get("stage") == "collecting" and not _auto_pipeline.collector.is_collecting:
        # Collection done, auto-finalize
        result = _auto_pipeline.finalize()
        status = _auto_pipeline.get_status()
        status["auto_finalized"] = True
        if result.get("success") and result.get("ai_task"):
            status["ai_task"] = result["ai_task"]
    
    return jsonify(status)


@app.route("/api/auto-reverse/stop", methods=["POST"])
def api_auto_reverse_stop():
    """Stop the automated reverse pipeline."""
    global _auto_pipeline
    
    if _auto_pipeline:
        _auto_pipeline.cancel()
        return jsonify({"status": "ok", "message": "Pipeline stopped"})
    return jsonify({"status": "error", "message": "No active pipeline"})


@app.route("/api/auto-reverse/finalize", methods=["POST"])
def api_auto_reverse_finalize():
    """Finalize pipeline and generate AI report."""
    global _auto_pipeline
    
    if _auto_pipeline is None:
        return jsonify({"status": "error", "message": "No active pipeline"})
    
    result = _auto_pipeline.finalize()
    
    if result.get("success"):
        return jsonify({
            "status": "ok",
            "stage": "completed",
            "ai_task": result.get("ai_task"),
            "report": result.get("report"),
        })
    return jsonify({"status": "error", "message": result.get("error", "Finalize failed")})


@app.route("/api/auto-reverse/prompt")
def api_auto_reverse_prompt():
    """Get the AI prompt content for the current pipeline."""
    global _auto_pipeline
    
    if _auto_pipeline is None:
        return jsonify({"status": "error", "message": "No active pipeline"})
    
    if _auto_pipeline.prompt is None:
        return jsonify({"status": "error", "message": "Prompt not generated yet. Call finalize first."})
    
    return jsonify({"status": "ok", "prompt": _auto_pipeline.prompt, "task_id": "pipeline"})


# ============================================================
# Kimi Code AI Prompt Generator Routes
# ============================================================

@app.route("/api/ai/status")
def api_ai_status():
    """Check Kimi Code Prompt Generator status"""
    try:
        # Prompt Generator is always available (no API key needed)
        return jsonify({"status": "ok", "connected": True, "mode": "prompt_generator"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/ai/generate", methods=["POST"])
def api_ai_generate():
    """Generate Kimi CLI prompt for code analysis"""
    code = request.json.get("code", "")
    language = request.json.get("language", "cpp")
    context = request.json.get("context", "")
    error = request.json.get("error", "")
    prompt_type = request.json.get("type", "analyze")
    if not code:
        return jsonify({"status": "error", "message": "no code provided"})
    try:
        gen = KimiCodePromptGenerator()
        if prompt_type == "explain":
            prompt = gen.explain_code(code, language)
        elif prompt_type == "fix":
            if not error:
                return jsonify({"status": "error", "message": "error description required for fix"})
            prompt = gen.suggest_fix(code, error, language)
        else:
            prompt = gen.analyze_code(code, language, context)
        return jsonify({"status": "ok", "prompt": prompt})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/ai/generate-project", methods=["POST"])
def api_ai_generate_project():
    """Generate Kimi CLI prompt for project-wide collaborative analysis"""
    context = request.json.get("context", "")
    max_files = request.json.get("max_files", 10)
    try:
        gen = KimiCodePromptGenerator()
        prompt = gen.analyze_project(root_dir=".", context=context, max_files=max_files)
        # Save to .kimi/prompts/ for easy access
        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".kimi", "prompts")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "project_analysis.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(prompt)
        return jsonify({
            "status": "ok",
            "prompt": prompt,
            "saved_to": out_path,
            "message": f"Project prompt saved to {out_path}"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})



@app.route("/api/ai/generate-reverse", methods=["POST"])
def api_ai_generate_reverse():
    """Generate Kimi CLI prompt for reverse engineering from DFG data"""
    if not state.g_dfg:
        return jsonify({"status": "error", "message": "DFG not built"})
    try:
        hits = []
        if state.g_debugger:
            hits = state.g_debugger.get_hits(max_count=50)
        report = state.g_dfg.to_report()
        gen = KimiCodePromptGenerator()
        prompt = gen.reverse_engineering_assist(hits, json.dumps(report, indent=2, default=str))
        return jsonify({"status": "ok", "prompt": prompt})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})



# ============================================================
# Provider Management Routes (Multi-Provider Support)
# ============================================================

try:
    from core.agents.provider_manager import ProviderManager
    _provider_manager = ProviderManager()
except ImportError:
    _provider_manager = None
    print("[WARNING] ProviderManager not available (core.agents moved to recycle)")

@app.route("/api/providers")
def api_providers_list():
    """List all available AI providers"""
    if _provider_manager is None:
        return jsonify({"status": "error", "message": "ProviderManager not available (core.agents moved to recycle)"})
    try:
        providers = _provider_manager.list_providers()
        return jsonify({
            "status": "ok",
            "providers": providers,
            "active_provider": _provider_manager.active_provider,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/providers/<provider_name>/set", methods=["POST"])
def api_providers_set(provider_name):
    """Set active AI provider"""
    try:
        success = _provider_manager.set_active(provider_name)
        if success:
            # Also update the orchestrator if it exists
            if state.g_debugger and hasattr(state.g_debugger, 'd'):
                pass  # No global orchestrator in server state
            return jsonify({
                "status": "ok",
                "active_provider": provider_name,
                "message": f"Switched to {provider_name}",
            })
        return jsonify({"status": "error", "message": f"Provider '{provider_name}' not found"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/providers/<provider_name>/test")
def api_providers_test(provider_name):
    """Test provider availability"""
    try:
        provider = _provider_manager.get_provider(provider_name)
        if not provider:
            return jsonify({"status": "error", "message": f"Provider '{provider_name}' not found"})
        
        available = provider.is_available()
        return jsonify({
            "status": "ok",
            "provider": provider_name,
            "available": available,
            "name": provider.config.name,
            "type": provider.config.type.value,
            "capabilities": provider.get_capabilities(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})



# ============================================================
# Phase 8: One-Click Automated Workflow API
# ============================================================

from core.workflow_engine import WorkflowEngine, WorkflowConfig, WorkflowState

_workflow_engine = None

@app.route("/api/workflow/start", methods=["POST"])
def api_workflow_start():
    """Start one-click automated reverse engineering workflow."""
    global _workflow_engine
    
    if not state.g_hProcess:
        return jsonify({"status": "error", "message": "No process attached"})
    
    data = request.json or {}
    
    # Stop existing workflow if running
    if _workflow_engine and _workflow_engine._is_running:
        _workflow_engine.cancel()
    
    _workflow_engine = WorkflowEngine()
    
    # Configure
    config = WorkflowConfig(
        strategy=data.get("strategy", "general"),
        collection_duration=data.get("duration", 30),
        max_breakpoints=data.get("max_breakpoints", 4),
        max_guard_pages=data.get("max_guard_pages", 8),
        auto_ai=data.get("auto_ai", True),
        ai_provider=data.get("ai_provider", "lmstudio"),
        auto_retry=data.get("auto_retry", True),
        max_retries=data.get("max_retries", 2),
    )
    _workflow_engine.config = config
    
    # Progress callback (logs to console for now, can be extended to WebSocket)
    def on_progress(data):
        print(f"[Workflow] {data.get('stage', 'unknown')}: {data.get('message', '')}")
    
    _workflow_engine.on_progress = on_progress
    
    # Start workflow
    result = _workflow_engine.start(blocking=False)
    
    if result.get("status") == "ok":
        return jsonify({
            "status": "ok",
            "state": _workflow_engine.state.value,
            "message": "Workflow started",
            "config": {
                "strategy": config.strategy,
                "duration": config.collection_duration,
                "max_breakpoints": config.max_breakpoints,
                "ai_provider": config.ai_provider,
            },
        })
    
    return jsonify(result)


@app.route("/api/workflow/status")
def api_workflow_status():
    """Get current workflow status."""
    global _workflow_engine
    
    if _workflow_engine is None:
        return jsonify({"status": "ok", "state": "idle", "message": "No active workflow"})
    
    status = _workflow_engine.get_status()
    status["status"] = "ok"
    
    # Add report preview if available
    if _workflow_engine.report_path:
        status["report_path"] = _workflow_engine.report_path
        # Read first 1000 chars of report
        try:
            with open(_workflow_engine.report_path, "r", encoding="utf-8", errors="ignore") as f:
                status["report_preview"] = f.read(1000)
        except:
            pass
    
    return jsonify(status)


@app.route("/api/workflow/pause", methods=["POST"])
def api_workflow_pause():
    """Pause the running workflow."""
    global _workflow_engine
    
    if _workflow_engine is None:
        return jsonify({"status": "error", "message": "No active workflow"})
    
    result = _workflow_engine.pause()
    return jsonify(result)


@app.route("/api/workflow/resume", methods=["POST"])
def api_workflow_resume():
    """Resume a paused workflow."""
    global _workflow_engine
    
    if _workflow_engine is None:
        return jsonify({"status": "error", "message": "No active workflow"})
    
    result = _workflow_engine.resume()
    return jsonify(result)


@app.route("/api/workflow/cancel", methods=["POST"])
def api_workflow_cancel():
    """Cancel the running workflow."""
    global _workflow_engine
    
    if _workflow_engine is None:
        return jsonify({"status": "error", "message": "No active workflow"})
    
    result = _workflow_engine.cancel()
    return jsonify(result)


@app.route("/api/workflow/report")
def api_workflow_report():
    """Get the final workflow report."""
    global _workflow_engine
    
    if _workflow_engine is None:
        return jsonify({"status": "error", "message": "No active workflow"})
    
    report = _workflow_engine.get_report()
    if report:
        return jsonify({"status": "ok", "report": report})
    
    return jsonify({"status": "error", "message": "Report not available yet"})


@app.route("/api/pattern/detect", methods=["POST"])
def api_pattern_detect():
    """Detect execution patterns from breakpoint hit history."""
    from core.pattern_engine import PatternEngine
    
    engine = PatternEngine()
    engine.add_hits_from_state()
    
    # Also try debugger hits
    try:
        debugger = state.get_debugger()
        if debugger and hasattr(debugger, 'get_hits'):
            hits = debugger.get_hits()
            for hit in hits:
                engine.add_hit(
                    timestamp=hit.get('timestamp', time.time()),
                    address=hit.get('address', 0),
                    value=hit.get('value', 0),
                    bp_type=hit.get('type', 'write'),
                    source_bp=hit.get('bp_id', ''),
                    context=hit.get('context', {})
                )
    except Exception:
        pass
    
    if not engine.hits:
        return jsonify({
            "status": "no_data",
            "message": "No breakpoint hits available. Use set_breakpoint and wait for hits, or get_breakpoint_hits first.",
            "patterns": [],
            "summary": {"total_patterns": 0, "total_hits": 0, "unique_addresses": 0},
        })
    
    patterns = engine.detect_patterns()
    summary = engine.get_summary()
    
    return jsonify({
        "status": "ok",
        "patterns": [p.to_dict() for p in patterns],
        "summary": summary,
    })


# ============================================================
# Phase 9: LLM Agent API (Auto Agent Tab) - DEPRECATED: use intent_agent.py
# ============================================================

try:
    from core.agent_engine import AgentEngine, AgentState
    _agent_engine: Optional[AgentEngine] = None
except ImportError:
    AgentEngine = None  # type: ignore
    AgentState = None  # type: ignore
    _agent_engine = None

@app.route("/api/agent/start", methods=["POST"])
def api_agent_start():
    """Start LLM Agent task."""
    global _agent_engine

    if _agent_engine is None:
        return jsonify({"status": "error", "message": "AgentEngine deprecated. Use /api/intent_agent/start instead."})

    if not state.g_hProcess:
        return jsonify({"status": "error", "message": "No process attached"})

    data = request.json or {}
    task = data.get("task", "").strip()
    if not task:
        return jsonify({"status": "error", "message": "Task description is required"})

    # Stop existing agent if running
    if _agent_engine and _agent_engine.is_running:
        _agent_engine.stop()
        time.sleep(0.5)

    _agent_engine = AgentEngine()

    # Parse hint
    hint = {}
    hint_raw = data.get("hint", {})
    if isinstance(hint_raw, dict):
        hint = hint_raw
    elif isinstance(hint_raw, str):
        try:
            hint = json.loads(hint_raw)
        except Exception:
            pass

    # Configure
    _agent_engine.configure(
        task=task,
        hint=hint,
        max_steps=data.get("max_steps", 15),
        provider_name=data.get("provider", "lmstudio"),
        require_confirm_for_write=data.get("confirm_write", True),
    )

    # Progress callback (logs to console)
    def on_progress(data):
        print(f"[Agent] {data.get('stage', 'unknown')}: {data.get('message', '')}")

    _agent_engine.on_progress = on_progress

    # Start
    result = _agent_engine.start(blocking=False)
    return jsonify(result)


@app.route("/api/agent/status")
def api_agent_status():
    """Get current Agent status (poll endpoint)."""
    global _agent_engine

    if _agent_engine is None:
        return jsonify({"status": "ok", "state": "idle", "message": "No active agent"})

    status = _agent_engine.get_status()
    status["status"] = "ok"
    # 前端使用 confirm_request 字段名
    if "pending_confirm" in status:
        status["confirm_request"] = status.pop("pending_confirm")
    return jsonify(status)


@app.route("/api/agent/stop", methods=["POST"])
def api_agent_stop():
    """Stop the running agent."""
    global _agent_engine

    if _agent_engine is None:
        return jsonify({"status": "error", "message": "No active agent"})

    _agent_engine.stop()
    return jsonify({"status": "ok", "state": "cancelled", "message": "Agent stopped"})


@app.route("/api/agent/confirm", methods=["POST"])
def api_agent_confirm():
    """Confirm/reject a pending write operation."""
    global _agent_engine

    if _agent_engine is None:
        return jsonify({"status": "error", "message": "No active agent"})

    data = request.json or {}
    approved = data.get("approved", False)
    result = _agent_engine.confirm(approved)
    return jsonify(result)


# ============================================================
# Phase 2: Interactive Intent Agent API
# ============================================================

_intent_agent: Optional[IntentAgent] = None
_intent_agent_messages: List[Dict] = []  # Buffer for frontend polling


@app.route("/api/intent/start", methods=["POST"])
def api_intent_start():
    """Start an interactive reverse engineering session with IntentAgent."""
    global _intent_agent, _intent_agent_messages

    if not state.g_hProcess or not state.g_pid:
        return jsonify({"status": "error", "message": "No process attached"})

    data = request.json or {}

    # Cancel existing session
    if _intent_agent and _intent_agent.state != AgentState.DONE:
        _intent_agent.cancel()
        time.sleep(0.3)

    _intent_agent_messages = []

    # Get process info
    process_name = ""
    exe_path = ""
    try:
        if psutil:
            p = psutil.Process(state.g_pid)
            process_name = p.name()
            exe_path = p.exe()
    except Exception:
        pass

    # Create agent with provider and autonomy config
    provider = data.get("provider", "lmstudio")
    autonomy = data.get("autonomy", "interactive")
    _intent_agent = IntentAgent(provider=provider, autonomy=autonomy)

    # Callback: when agent sends a message, store it for frontend polling
    def on_message(msg: AgentMessage):
        msg_dict = {
            "type": msg.type.value,
            "title": msg.title,
            "content": msg.content,
            "data": msg.data,
            "requires_response": msg.requires_response,
            "response_hint": msg.response_hint,
            "options": msg.options,
            "timestamp": time.time(),
        }
        _intent_agent_messages.append(msg_dict)
        print(f"[IntentAgent] {msg.type.value}: {msg.title}")

    def on_progress(data: Dict):
        print(f"[IntentAgent] {data.get('type', 'unknown')}: {data.get('message', '')}")

    _intent_agent.on_agent_message = on_message
    _intent_agent.on_progress = on_progress

    # Start analysis phase (non-blocking, runs in background thread)
    _intent_agent.attach_process(state.g_pid, process_name, exe_path)

    return jsonify({
        "status": "ok",
        "state": _intent_agent.state.value,
        "process_name": process_name,
        "pid": state.g_pid,
        "provider": provider,
        "message": "Interactive session started. Poll /api/intent/status for messages.",
    })


@app.route("/api/intent/status")
def api_intent_status():
    """Get current interactive session status and pending messages."""
    global _intent_agent, _intent_agent_messages

    if _intent_agent is None:
        return jsonify({"status": "ok", "state": "idle", "message": "No active session"})

    # Get all messages since last poll (or all if first time)
    # Client should send 'last_seen' to get incremental messages
    last_seen = request.args.get("last_seen", type=float, default=0)
    new_messages = [m for m in _intent_agent_messages if m.get("timestamp", 0) > last_seen]

    status = {
        "status": "ok",
        "state": _intent_agent.state.value,
        "process_name": _intent_agent._process_name,
        "process_type": _intent_agent._process_type,
        "message_count": len(_intent_agent_messages),
        "new_messages": new_messages,
        "has_pending_question": any(m.get("requires_response") for m in _intent_agent_messages[-5:]),
        "experiment_count": len(_intent_agent._context.scan_history),
        "finding_count": len(_intent_agent._context.findings),
        "candidate_count": 0,  # ReAct architecture no longer maintains candidate_addrs
        "provider": _intent_agent._provider_name,
        "autonomy": _intent_agent._autonomy.value,
    }

    return jsonify(status)


@app.route("/api/intent/respond", methods=["POST"])
def api_intent_respond():
    """Submit user response to the IntentAgent."""
    global _intent_agent

    if _intent_agent is None:
        return jsonify({"status": "error", "message": "No active session"})

    data = request.json or {}
    text = data.get("text", "")
    selected_option = data.get("selected_option")
    confirmed = data.get("confirmed")

    if not text and selected_option is None and confirmed is None:
        return jsonify({"status": "error", "message": "Response text or option is required"})

    resp = UserResponse(
        message_id=data.get("message_id", f"resp_{int(time.time())}"),
        text=text,
        selected_option=selected_option,
        confirmed=confirmed,
    )

    result = _intent_agent.provide_user_response(resp)
    return jsonify(result)


@app.route("/api/intent/cancel", methods=["POST"])
def api_intent_cancel():
    """Cancel the interactive session."""
    global _intent_agent

    if _intent_agent is None:
        return jsonify({"status": "error", "message": "No active session"})

    _intent_agent.cancel()
    return jsonify({"status": "ok", "state": "cancelled", "message": "Session cancelled"})


# ──────────────────────────────────────────────────────────────
# Ghidra Integration API
# ──────────────────────────────────────────────────────────────

@app.route("/api/ghidra/status")
def api_ghidra_status():
    """Check if Ghidra is available and configured."""
    try:
        bridge = state.get_ghidra_bridge()
        if bridge is None:
            return jsonify({"status": "not_configured", "message": "Ghidra not initialized"})
        return jsonify({
            "status": "ok",
            "ghidra_home": str(bridge.ghidra_home),
            "project_dir": str(bridge.project_dir),
            "output_dir": str(bridge.output_dir),
            "script_dir": str(bridge.script_dir),
            "cached_results": len(bridge._analysis_results),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/ghidra/analyze", methods=["POST"])
def api_ghidra_analyze():
    """Run Ghidra headless analysis on the attached process's main module.

    Request: {}
    Response: { status, project_id, result, message }
    """
    if not state.g_hProcess or not state.g_pid:
        return jsonify({"status": "error", "message": "No process attached"})

    try:
        bridge = state.get_ghidra_bridge()
        if bridge is None:
            return jsonify({"status": "error", "message": "Ghidra not initialized"})

        # Export main module memory
        dump_path = bridge.export_main_module(state.g_hProcess, state.g_pid)

        # Get project name
        from memory.operations import enum_process_modules
        mods = enum_process_modules(state.g_pid)
        project_name = mods[0].get("name", f"proc_{state.g_pid}") if mods else f"proc_{state.g_pid}"

        # Run analysis (async via thread to not block)
        import threading
        def _run():
            try:
                result = bridge.analyze_binary(dump_path, project_name=project_name)
                # Import to knowledge base
                store = state.get_memory_store()
                if store:
                    project_id = f"{project_name}_{state.g_pid}"
                    bridge.import_to_knowledge_base(project_id, store.graph, result)
                logger.info(f"[Ghidra] Analysis complete: {project_name}")
            except Exception as e:
                logger.exception(f"[Ghidra] Analysis failed: {e}")

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        return jsonify({
            "status": "ok",
            "project_id": f"{project_name}_{state.g_pid}",
            "dump_path": dump_path,
            "message": "Ghidra analysis started in background. Check /api/ghidra/query for results.",
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/ghidra/query_function")
def api_ghidra_query_function():
    """Query which function contains an address.

    Query params: address (hex or decimal)
    """
    addr_str = request.args.get("address", "")
    if not addr_str:
        return jsonify({"status": "error", "message": "address parameter required"})

    try:
        addr = int(addr_str, 16) if addr_str.startswith("0x") or addr_str.startswith("0X") else int(addr_str)
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid address format"})

    try:
        bridge = state.get_ghidra_bridge()
        if bridge is None:
            return jsonify({"status": "error", "message": "Ghidra not initialized"})

        result = bridge.query_function_at_address(addr)
        if result.found:
            return jsonify({
                "status": "ok",
                "found": True,
                "function_name": result.function_name,
                "function_address": f"0x{result.function_address:08X}",
                "offset_in_function": f"0x{result.offset_in_function:X}",
                "decompiled_snippet": result.decompiled_snippet[:500] if result.decompiled_snippet else "",
                "pcode_summary": result.pcode_summary[:1000] if result.pcode_summary else "",
            })
        else:
            return jsonify({"status": "ok", "found": False, "message": "Address not in any known function"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/ghidra/decompile")
def api_ghidra_decompile():
    """Get decompiled code for a function address.

    Query params: address (hex or decimal)
    """
    addr_str = request.args.get("address", "")
    if not addr_str:
        return jsonify({"status": "error", "message": "address parameter required"})

    try:
        addr = int(addr_str, 16) if addr_str.startswith("0x") or addr_str.startswith("0X") else int(addr_str)
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid address format"})

    try:
        bridge = state.get_ghidra_bridge()
        if bridge is None:
            return jsonify({"status": "error", "message": "Ghidra not initialized"})

        code = bridge.get_decompiled_code(addr)
        if code:
            return jsonify({"status": "ok", "address": f"0x{addr:08X}", "code": code})
        else:
            return jsonify({"status": "ok", "code": "", "message": "No decompiled code available"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/ghidra/pcode")
def api_ghidra_pcode():
    """Get P-Code summary for a function address.

    Query params: address (hex or decimal)
    """
    addr_str = request.args.get("address", "")
    if not addr_str:
        return jsonify({"status": "error", "message": "address parameter required"})

    try:
        addr = int(addr_str, 16) if addr_str.startswith("0x") or addr_str.startswith("0X") else int(addr_str)
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid address format"})

    try:
        bridge = state.get_ghidra_bridge()
        if bridge is None:
            return jsonify({"status": "error", "message": "Ghidra not initialized"})

        summary = bridge.get_pcode_summary(addr)
        if summary:
            return jsonify({"status": "ok", "address": f"0x{addr:08X}", "summary": summary})
        else:
            return jsonify({"status": "ok", "summary": "", "message": "No P-Code available"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/ghidra/enhanced_decompile")
def api_ghidra_enhanced_decompile():
    """Get enhanced decompilation with dynamic register values.

    Query params:
        address (hex or decimal)
        registers (JSON: {"rax": 1234, "rbx": 5678})
    """
    addr_str = request.args.get("address", "")
    registers_str = request.args.get("registers", "{}")
    if not addr_str:
        return jsonify({"status": "error", "message": "address parameter required"})

    try:
        addr = int(addr_str, 16) if addr_str.startswith("0x") or addr_str.startswith("0X") else int(addr_str)
        registers = json.loads(registers_str) if registers_str else {}
    except (ValueError, json.JSONDecodeError) as e:
        return jsonify({"status": "error", "message": f"Invalid parameter: {e}"})

    try:
        bridge = state.get_ghidra_bridge()
        if bridge is None:
            return jsonify({"status": "error", "message": "Ghidra not initialized"})

        decompiler = bridge.get_decompiler_bridge()
        enhanced = decompiler.enhance_for_breakpoint(addr, registers)

        return jsonify({"status": "ok", "address": f"0x{addr:08X}", "enhanced": enhanced})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# ── DecompilerBridge getter (exposed on GhidraBridge) ──

from core.ghidra_bridge import DecompilerBridge

@app.route("/api/ghidra/struct_correct", methods=["POST"])
def api_ghidra_struct_correct():
    """Compare static struct with dynamic access and generate correction.

    Request: { struct_name, dynamic_accesses: [{offset, size, type}] }
    """
    data = request.json or {}
    struct_name = data.get("struct_name", "")
    dynamic_accesses = data.get("dynamic_accesses", [])

    if not struct_name or not dynamic_accesses:
        return jsonify({"status": "error", "message": "struct_name and dynamic_accesses required"})

    try:
        bridge = state.get_ghidra_bridge()
        if bridge is None:
            return jsonify({"status": "error", "message": "Ghidra not initialized"})

        corrector = bridge.get_struct_corrector()

        # Find static struct from last analysis result
        static_struct = None
        result = bridge._get_result()
        if result and result.structures:
            for s in result.structures:
                if s.name == struct_name:
                    static_struct = s
                    break

        correction = corrector.compare_and_correct(
            struct_name=struct_name,
            static_struct=static_struct,
            dynamic_accesses=dynamic_accesses
        )

        # Generate Ghidra script
        script = corrector.generate_ghidra_script(correction)

        # Apply to knowledge base
        store = state.get_memory_store()
        if store:
            project_id = f"{state.g_pid}_struct"
            corrector.apply_to_knowledge_base(correction, project_id, store.graph)

        return jsonify({
            "status": "ok",
            "correction": correction,
            "ghidra_script": script,
            "message": f"Found {len(correction.get('corrections', []))} corrections, "
                       f"{len(correction.get('warnings', []))} warnings",
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# ── Phase 3: Angr / Z3 / Unicorn / Capstone / Frida API Routes ──

@app.route("/api/angr/build_cfg", methods=["POST"])
def api_angr_build_cfg():
    """Use Angr to build CFG from binary or exported memory."""
    data = request.json or {}
    binary_path = data.get("binary_path", "")
    base_addr_str = data.get("base_addr", "")
    arch = data.get("arch", "x86_64")

    try:
        from core.angr_bridge import AngrBridge
        bridge = state.get_angr_bridge()
        if bridge is None or not bridge.is_available():
            return jsonify({"status": "error", "message": "Angr not available. Install: pip install angr"})

        # If no binary_path, try to export from current process
        if not binary_path and state.g_hProcess:
            ghidra = state.get_ghidra_bridge()
            if ghidra:
                binary_path = ghidra.export_main_module(state.g_hProcess, state.g_pid)
            else:
                return jsonify({"status": "error", "message": "No binary_path and GhidraBridge unavailable for export"})
        elif not binary_path:
            return jsonify({"status": "error", "message": "binary_path required or attach a process"})

        base_addr = 0x140000000
        if base_addr_str:
            base_addr = int(base_addr_str, 16) if base_addr_str.startswith("0x") else int(base_addr_str)

        loaded = bridge.load_pe(binary_path, base_addr=base_addr if base_addr else None, arch=arch)
        if not loaded:
            return jsonify({"status": "error", "message": f"Failed to load binary: {binary_path}"})

        cfg = bridge.build_cfg()
        if not cfg:
            return jsonify({"status": "error", "message": "CFG build returned no results"})

        # Import to knowledge base
        store = state.get_memory_store()
        if store:
            project_id = f"angr_{state.g_pid or 'manual'}"
            bridge.import_cfg_to_knowledge_base(project_id, store.graph)

        return jsonify({
            "status": "ok",
            "architecture": cfg.architecture,
            "base_address": f"0x{cfg.base_address:08X}",
            "functions": len(cfg.functions),
            "basic_blocks": len(cfg.basic_blocks),
            "functions_sample": [
                {"addr": f"0x{f.address:08X}", "name": f.name, "blocks": len(f.blocks)}
                for f in cfg.functions[:10]
            ],
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/angr/symbolic_execute", methods=["POST"])
def api_angr_symbolic_execute():
    """Run Angr symbolic execution from a given address."""
    data = request.json or {}
    start_addr_str = data.get("start_addr", "")
    max_steps = data.get("max_steps", 100)
    seed_registers = data.get("seed_registers", {})

    if not start_addr_str:
        return jsonify({"status": "error", "message": "start_addr required"})

    try:
        addr = int(start_addr_str, 16) if start_addr_str.startswith("0x") else int(start_addr_str)
        bridge = state.get_angr_bridge()
        if bridge is None or not bridge.is_available():
            return jsonify({"status": "error", "message": "Angr not available"})
        if not bridge.project:
            return jsonify({"status": "error", "message": "Angr project not loaded. Call /api/angr/build_cfg first."})

        result = bridge.symbolic_execute_at(addr, max_steps=max_steps, seed_registers=seed_registers)
        if not result:
            return jsonify({"status": "error", "message": "Symbolic execution failed"})

        return jsonify({
            "status": "ok",
            "start_address": f"0x{result.start_address:08X}",
            "steps": result.steps,
            "states_reached": result.states_reached,
            "active_states": result.active_states,
            "found_addresses": [f"0x{a:08X}" for a in result.found_addresses[:20]],
            "constraints_sample": result.constraints[:5],
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/z3/solve", methods=["POST"])
def api_z3_solve():
    """Use Z3 solver to solve path constraints."""
    data = request.json or {}
    conditions = data.get("conditions", [])
    variables = data.get("variables", {})

    try:
        solver = state.get_z3_solver()
        if solver is None or not solver.is_available():
            return jsonify({"status": "error", "message": "Z3 not available. Install: pip install z3-solver"})

        # Parse conditions
        parsed_conds = []
        for c in conditions:
            if isinstance(c, str):
                p = solver._parse_constraint_string(c)
                if p:
                    parsed_conds.append(p)
            elif isinstance(c, (list, tuple)) and len(c) == 3:
                parsed_conds.append((c[0], c[1], c[2]))

        result = solver.solve_path_condition(parsed_conds, variables)

        return jsonify({
            "status": "ok",
            "satisfiable": result.satisfiable,
            "values": result.values,
            "model": result.model_str,
            "reason": result.reason,
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/unicorn/verify", methods=["POST"])
def api_unicorn_verify():
    """Use Unicorn emulator to verify code execution safely."""
    data = request.json or {}
    code_hex = data.get("code_hex", "")
    start_addr_str = data.get("start_addr", "")
    input_values = data.get("input_values", {})
    max_steps = data.get("max_steps", 1000)
    arch = data.get("arch", "x86_64")

    if not code_hex or not start_addr_str:
        return jsonify({"status": "error", "message": "code_hex and start_addr required"})

    try:
        code = bytes.fromhex(code_hex.replace(" ", "").replace("\n", ""))
        start_addr = int(start_addr_str, 16) if start_addr_str.startswith("0x") else int(start_addr_str)

        validator = state.get_unicorn_validator()
        if validator is None or not validator.is_available():
            return jsonify({"status": "error", "message": "Unicorn not available. Install: pip install unicorn"})

        result = validator.verify_input(code, start_addr, input_values, arch=arch, max_steps=max_steps)
        if not result:
            return jsonify({"status": "error", "message": "Unicorn verification failed"})

        return jsonify({
            "status": "ok",
            "valid": result.valid,
            "crash": result.crash,
            "steps": result.steps,
            "final_pc": f"0x{result.final_pc:08X}",
            "register_state": {k: f"0x{v:08X}" for k, v in result.register_state.items()},
            "warnings": result.warnings,
            "error_reason": result.error_reason,
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/capstone/disasm")
def api_capstone_disasm():
    """Use Capstone to disassemble a memory region."""
    start_str = request.args.get("start", "")
    end_str = request.args.get("end", "")
    arch = request.args.get("arch", "x86_64")

    if not start_str or not end_str:
        return jsonify({"status": "error", "message": "start and end parameters required"})

    if not state.g_hProcess:
        return jsonify({"status": "error", "message": "No process attached"})

    try:
        start = int(start_str, 16) if start_str.startswith("0x") else int(start_str)
        end = int(end_str, 16) if end_str.startswith("0x") else int(end_str)
        size = end - start

        if size <= 0 or size > 0x10000:
            return jsonify({"status": "error", "message": f"Invalid region size: {size}"})

        from core.winapi import ReadProcessMemory
        data = ReadProcessMemory(state.g_hProcess, start, size)
        if not data:
            return jsonify({"status": "error", "message": f"Failed to read memory at 0x{start:08X}"})

        disasm = state.get_capstone_disasm()
        if disasm is None or not disasm.is_available():
            return jsonify({"status": "error", "message": "Capstone not available. Install: pip install capstone"})

        instructions = disasm.disasm(data, start, arch=arch)
        formatted = disasm.format_disassembly(instructions, start)

        return jsonify({
            "status": "ok",
            "region": f"0x{start:08X} - 0x{end:08X}",
            "architecture": arch,
            "instruction_count": len(instructions),
            "disassembly": formatted,
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/frida/generate_hook", methods=["POST"])
def api_frida_generate_hook():
    """Generate a Frida hook script for a function."""
    data = request.json or {}
    function_name = data.get("function_name", "")
    module_name = data.get("module_name", "")
    log_args = data.get("log_args", True)

    if not function_name:
        return jsonify({"status": "error", "message": "function_name required"})

    try:
        bridge = state.get_frida_bridge()
        if bridge is None or not bridge.is_available():
            return jsonify({"status": "error", "message": "Frida not available. Install: pip install frida"})

        script = bridge.generate_hook_script(function_name, module_name or None, log_args=log_args)

        return jsonify({
            "status": "ok",
            "function_name": function_name,
            "module_name": module_name or "auto",
            "script": script,
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)

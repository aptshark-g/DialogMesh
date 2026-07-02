# -*- coding: utf-8 -*-
"""
core/winapi.py
──────────────
Stub module for Windows API bindings used by core package.

This stub exists solely to satisfy imports during service-layer testing
where the actual Windows API (pywin32 / ctypes wrappers) is not required.
"""

from __future__ import annotations

import ctypes
from typing import Any, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# Process / Memory API stubs
# ═══════════════════════════════════════════════════════════════════════════════

def OpenProcess(*args, **kwargs) -> int:
    return 0

def ReadProcessMemory(*args, **kwargs) -> tuple:
    return (True, b"")

def WriteProcessMemory(*args, **kwargs) -> bool:
    return True

def CloseHandle(*args, **kwargs) -> bool:
    return True

def VirtualQueryEx(*args, **kwargs) -> Any:
    return None

def GetProcessId(*args, **kwargs) -> int:
    return 0

def VirtualAllocEx(*args, **kwargs) -> int:
    return 0

def VirtualFreeEx(*args, **kwargs) -> bool:
    return True

def VirtualProtectEx(*args, **kwargs) -> bool:
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# Thread API stubs
# ═══════════════════════════════════════════════════════════════════════════════

def OpenThread(*args, **kwargs) -> int:
    return 0

def SuspendThread(*args, **kwargs) -> int:
    return 0

def ResumeThread(*args, **kwargs) -> int:
    return 0

def GetThreadContext(*args, **kwargs) -> Any:
    return None

def SetThreadContext(*args, **kwargs) -> bool:
    return True

def CreateToolhelp32Snapshot(*args, **kwargs) -> int:
    return 0

def Thread32First(*args, **kwargs) -> bool:
    return False

def Thread32Next(*args, **kwargs) -> bool:
    return False

def suspend_process(*args, **kwargs) -> bool:
    return True

def resume_process(*args, **kwargs) -> bool:
    return True

def get_main_thread_id(*args, **kwargs) -> Optional[int]:
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Module enumeration stubs
# ═══════════════════════════════════════════════════════════════════════════════

def Module32First(*args, **kwargs) -> bool:
    return False

def Module32Next(*args, **kwargs) -> bool:
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# Structure stubs
# ═══════════════════════════════════════════════════════════════════════════════

class MEMORY_BASIC_INFORMATION:
    def __init__(self):
        self.BaseAddress = 0
        self.AllocationBase = 0
        self.AllocationProtect = 0
        self.RegionSize = 0
        self.State = 0
        self.Protect = 0
        self.Type = 0

class MODULEENTRY32:
    def __init__(self):
        self.dwSize = 0
        self.th32ModuleID = 0
        self.th32ProcessID = 0
        self.GlblcntUsage = 0
        self.ProccntUsage = 0
        self.modBaseAddr = 0
        self.modBaseSize = 0
        self.hModule = 0
        self.szModule = ""
        self.szExePath = ""

class THREADENTRY32:
    def __init__(self):
        self.dwSize = 0
        self.cntUsage = 0
        self.th32ThreadID = 0
        self.th32OwnerProcessID = 0
        self.tpBasePri = 0
        self.tpDeltaPri = 0
        self.dwFlags = 0

class CONTEXT_X86:
    def __init__(self):
        self.Eax = 0
        self.Ebx = 0
        self.Ecx = 0
        self.Edx = 0
        self.Esi = 0
        self.Edi = 0
        self.Ebp = 0
        self.Esp = 0
        self.Eip = 0


# ═══════════════════════════════════════════════════════════════════════════════
# Constant stubs
# ═══════════════════════════════════════════════════════════════════════════════

PROCESS_ALL_ACCESS = 0x1F0FFF

PAGE_NOACCESS = 0x01
PAGE_READONLY = 0x02
PAGE_READWRITE = 0x04
PAGE_READABLE = 0x02
PAGE_EXECUTE = 0x10
PAGE_EXECUTE_READ = 0x20
PAGE_EXECUTE_READWRITE = 0x40
PAGE_GUARD = 0x100
PAGE_NOCACHE = 0x200

MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000

TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
TH32CS_SNAPTHREAD = 0x00000004
THREAD_SUSPEND_RESUME = 0x0002
THREAD_GET_CONTEXT = 0x0008
THREAD_SET_CONTEXT = 0x0010
THREAD_ALL_ACCESS = 0x1F03FF
CONTEXT_FULL = 0x00010007

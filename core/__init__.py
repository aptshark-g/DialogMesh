from core.winapi import (
    # 基础
    OpenProcess, ReadProcessMemory, WriteProcessMemory, CloseHandle,
    VirtualQueryEx, GetProcessId,
    # 内存管理
    VirtualAllocEx, VirtualFreeEx, VirtualProtectEx,
    # 线程/暂停恢复
    OpenThread, SuspendThread, ResumeThread,
    GetThreadContext, SetThreadContext,
    CreateToolhelp32Snapshot,
    Thread32First, Thread32Next,
    suspend_process, resume_process, get_main_thread_id,
    # 模块枚举
    Module32First, Module32Next,
    # 结构体
    MEMORY_BASIC_INFORMATION, MODULEENTRY32, THREADENTRY32, CONTEXT_X86,
    # 常量
    PROCESS_ALL_ACCESS,
    PAGE_NOACCESS, PAGE_READONLY, PAGE_READWRITE, PAGE_READABLE,
    PAGE_EXECUTE, PAGE_EXECUTE_READ, PAGE_EXECUTE_READWRITE,
    PAGE_GUARD, PAGE_NOCACHE,
    MEM_COMMIT, MEM_RESERVE, MEM_RELEASE,
    TH32CS_SNAPMODULE, TH32CS_SNAPMODULE32,
    TH32CS_SNAPTHREAD, THREAD_SUSPEND_RESUME,
    THREAD_GET_CONTEXT, THREAD_SET_CONTEXT, THREAD_ALL_ACCESS,
    CONTEXT_FULL,
)

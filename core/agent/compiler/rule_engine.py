"""规则约束引擎 — 帧库 + 四步消解"""
from dataclasses import dataclass, field
from .models import SlotValue, ParseContext, ConstraintRule


@dataclass
class FrameLibrary:
    """语义框架库 — 预置约束规则"""
    rules: list[ConstraintRule] = field(default_factory=list)

    @classmethod
    def load_default(cls) -> "FrameLibrary":
        lib = FrameLibrary()
        lib.rules = cls._load_expanded_rules()
        return lib

    @classmethod
    def _load_expanded_rules(cls) -> list:
        return [
            ConstraintRule("cause(呛)", "cause", ["碳酸", "辛辣", "气管误入", "过敏"], incompatible_with={"patient": ["辛辣", "过敏"]}),
            ConstraintRule("cause(崩溃)", "cause", ["内存不足", "逻辑错误", "依赖缺失"]),
            ConstraintRule("patient(喝)", "patient", ["饮料", "水", "酒", "药"]),
            ConstraintRule("action(运行)", "action", ["execute", "启动", "执行"]),
            ConstraintRule("action(修改)", "action", ["modify", "更新", "编辑"]),
            ConstraintRule("action(删除)", "action", ["delete", "移除", "清除"]),
            ConstraintRule("agent(工具)", "agent", ["系统", "API", "脚本"], priority=5),
            ConstraintRule("action(debug)", "action", ["debug", "diagnose", "trace", "inspect"]),
            ConstraintRule("action(compile)", "action", ["compile", "build", "assemble", "link"]),
            ConstraintRule("action(deploy)", "action", ["deploy", "release", "publish", "install"]),
            ConstraintRule("action(restart)", "action", ["restart", "reboot", "reload", "recycle"]),
            ConstraintRule("action(run)", "action", ["execute", "run", "launch", "start", "invoke"]),
            ConstraintRule("action(configure)", "action", ["configure", "set up", "initialize", "setup"]),
            ConstraintRule("action(scan)", "action", ["scan", "enumerate", "probe", "map"]),
            ConstraintRule("action(test)", "action", ["test", "validate", "verify"]),
            ConstraintRule("action(clean)", "action", ["clean", "purge", "sanitize", "clear"]),
            ConstraintRule("action(check)", "action", ["check", "inspect", "examine", "review"]),
            ConstraintRule("action(monitor)", "action", ["monitor", "watch", "track", "observe"]),
            ConstraintRule("action(enable)", "action", ["enable", "activate", "turn on"]),
            ConstraintRule("action(disable)", "action", ["disable", "deactivate", "turn off", "stop"]),
            ConstraintRule("action(schedule)", "action", ["schedule", "plan", "arrange", "set"]),
            ConstraintRule("action(backup)", "action", ["backup", "save", "archive", "preserve"]),
            ConstraintRule("action(restore)", "action", ["restore", "recover", "revert", "rollback"]),
            ConstraintRule("action(update)", "action", ["update", "upgrade", "patch", "refresh"]),
            ConstraintRule("action(show)", "action", ["show", "display", "print", "output"]),
            ConstraintRule("action(list)", "action", ["list", "enumerate", "catalog", "index"]),
            ConstraintRule("action(analyze)", "action", ["analyze", "investigate", "study", "examine"]),
            ConstraintRule("action(compare)", "action", ["compare", "contrast", "differentiate", "benchmark"]),
            ConstraintRule("action(predict)", "action", ["predict", "forecast", "project", "estimate"]),
            ConstraintRule("action(document)", "action", ["document", "record", "log", "report"]),
            ConstraintRule("action(query)", "action", ["query", "search", "find", "locate"]),
            ConstraintRule("action(create)", "action", ["create", "generate", "produce", "initialize"]),
            ConstraintRule("action(explain)", "action", ["explain", "describe", "clarify", "elaborate"]),
            ConstraintRule("action(greet)", "action", ["greet", "say hello", "introduce", "welcome"]),
            ConstraintRule("action(affirm)", "action", ["affirm", "agree", "confirm", "acknowledge"]),
            ConstraintRule("action(answer)", "action", ["answer", "respond", "reply", "resolve"]),
            ConstraintRule("patient(program)", "patient", ["program", "application", "software", "module", "component", "service"]),
            ConstraintRule("patient(script)", "patient", ["script", "code", "source", "file", "executable"]),
            ConstraintRule("patient(memory)", "patient", ["memory", "RAM", "cache", "buffer", "heap", "stack"]),
            ConstraintRule("patient(cpu)", "patient", ["CPU", "processor", "core", "thread", "compute"]),
            ConstraintRule("patient(disk)", "patient", ["disk", "storage", "volume", "partition", "filesystem"]),
            ConstraintRule("patient(network)", "patient", ["network", "connection", "port", "socket", "interface"]),
            ConstraintRule("patient(config)", "patient", ["config", "configuration", "setting", "parameter", "option"]),
            ConstraintRule("patient(log)", "patient", ["log", "logfile", "history", "record", "traceback"]),
            ConstraintRule("patient(process)", "patient", ["process", "daemon", "service", "task", "job"]),
            ConstraintRule("patient(debug)", "patient", ["bug", "defect", "error", "crash", "fault", "segfault"]),
            ConstraintRule("patient(question)", "patient", ["question", "query", "inquiry", "request"]),
            ConstraintRule("patient(report)", "patient", ["report", "result", "outcome", "finding"]),
            ConstraintRule("patient(info)", "patient", ["information", "data", "detail", "spec"]),
            ConstraintRule("agent(user)", "agent", ["user", "human", "operator", "admin", "developer"]),
            ConstraintRule("agent(system)", "agent", ["system", "OS", "platform", "environment"]),
            ConstraintRule("agent(tool)", "agent", ["tool", "script", "program", "utility", "daemon"]),
            ConstraintRule("agent(api)", "agent", ["API", "interface", "service", "endpoint"]),
            ConstraintRule("agent(module)", "agent", ["module", "component", "library", "plugin"]),
            ConstraintRule("agent(network)", "agent", ["network", "connection", "server", "client", "host"]),
            ConstraintRule("cause(crash)", "cause", ["crash", "segmentation fault", "segfault", "abort", "panic"]),
            ConstraintRule("cause(timeout)", "cause", ["timeout", "latency", "delay", "hang", "stall"]),
            ConstraintRule("cause(error)", "cause", ["error", "exception", "failure", "bug", "defect"]),
            ConstraintRule("cause(memory)", "cause", ["memory full", "OOM", "memory leak", "allocation error"]),
            ConstraintRule("cause(disk)", "cause", ["disk full", "IO error", "corruption", "bad sector"]),
            ConstraintRule("cause(network)", "cause", ["network failure", "connection lost", "DNS failure", "timeout"]),
            ConstraintRule("cause(permission)", "cause", ["permission denied", "access denied", "forbidden", "unauthorized"]),
            ConstraintRule("cause(config)", "cause", ["misconfiguration", "wrong config", "invalid setting", "bad value"]),
            ConstraintRule("cause(dependency)", "cause", ["dependency missing", "library not found", "version mismatch"]),
            ConstraintRule("cause(ssl)", "cause", ["SSL error", "certificate error", "handshake failure", "TLS error"]),
            ConstraintRule("result(success)", "result", ["success", "completed", "done", "passed", "OK"]),
            ConstraintRule("result(failure)", "result", ["failure", "failed", "error", "aborted", "rejected"]),
            ConstraintRule("result(warning)", "result", ["warning", "caution", "notice", "attention"]),
            ConstraintRule("result(output)", "result", ["output", "result", "response", "return value"]),
            ConstraintRule("result(change)", "result", ["changed", "updated", "modified", "applied"]),
            ConstraintRule("action(调试)", "action", ["调试", "诊断", "追踪", "除错"]),
            ConstraintRule("action(配置)", "action", ["配置", "设置", "设定", "搭建", "部署"]),
            ConstraintRule("action(分析)", "action", ["分析", "检查", "审查", "评估"]),
            ConstraintRule("action(查看)", "action", ["查看", "显示", "展示", "列出", "输出"]),
            ConstraintRule("action(创建)", "action", ["创建", "建立", "生成", "新建", "添加"]),
            ConstraintRule("action(测试)", "action", ["测试", "验证", "确认"]),
            ConstraintRule("action(扫描)", "action", ["扫描", "枚举", "探测", "搜索"]),
            ConstraintRule("action(监控)", "action", ["监控", "监视", "观察", "跟踪"]),
            ConstraintRule("action(重启)", "action", ["重启", "重新启动", "重载", "重置"]),
            ConstraintRule("action(备份)", "action", ["备份", "保存", "归档", "存储"]),
            ConstraintRule("action(恢复)", "action", ["恢复", "还原", "撤回", "回退"]),
            ConstraintRule("action(比较)", "action", ["比较", "对比", "区分", "区别"]),
            ConstraintRule("patient(程序)", "patient", ["程序", "应用程序", "软件", "模块", "组件"]),
            ConstraintRule("patient(内存)", "patient", ["内存", "RAM", "缓存", "缓冲区", "栈", "堆"]),
            ConstraintRule("patient(磁盘)", "patient", ["磁盘", "硬盘", "存储", "卷", "分区"]),
            ConstraintRule("patient(网络)", "patient", ["网络", "连接", "端口", "接口", "网卡"]),
            ConstraintRule("patient(文件)", "patient", ["文件", "文档", "目录", "路径", "配置"]),
            ConstraintRule("patient(日志)", "patient", ["日志", "记录", "历史", "报告"]),
            ConstraintRule("patient(进程)", "patient", ["进程", "服务", "守护进程", "任务"]),
            ConstraintRule("patient(数据库)", "patient", ["数据库", "数据源", "表", "连接池"]),
            ConstraintRule("cause(超时)", "cause", ["超时", "延迟", "阻塞", "挂起"]),
            ConstraintRule("cause(错误)", "cause", ["错误", "异常", "失败", "缺陷"]),
            ConstraintRule("cause(内存)", "cause", ["内存不足", "OOM", "内存泄漏", "分配失败"]),
            ConstraintRule("cause(磁盘)", "cause", ["磁盘满", "IO错误", "损坏", "坏道"]),
            ConstraintRule("cause(网络)", "cause", ["网络故障", "连接断开", "DNS解析", "超时"]),
            ConstraintRule("cause(权限)", "cause", ["权限不足", "访问被拒", "禁止", "未授权"]),
            ConstraintRule("cause(配置)", "cause", ["配置错误", "设置无效", "参数错误"]),
            ConstraintRule("cause(依赖)", "cause", ["依赖缺失", "库未找到", "版本不匹配"]),
        ]

    def query(self, slot_name: str, value: str = "", domain: str = "general") -> list[ConstraintRule]:
        results = [r for r in self.rules if r.slot_name == slot_name]
        if domain != "general":
            results = [r for r in results if r.domain == domain or r.domain == "general"]
        return results

    def get_frame(self, frame_name: str) -> list[ConstraintRule]:
        return [r for r in self.rules if r.frame_name == frame_name]

    def add(self, rule: ConstraintRule):
        self.rules.append(rule)


class RuleConstraintEngine:
    """只对 confidence < 0.75 的维度做功"""
    CONFIDENCE_THRESHOLD = 0.75

    def __init__(self, frame_library: FrameLibrary):
        self.library = frame_library

    def refine(self, slots: dict[str, SlotValue], context: ParseContext) -> dict[str, SlotValue]:
        result = dict(slots)
        for slot_name, slot in slots.items():
            if slot.confidence >= self.CONFIDENCE_THRESHOLD:
                continue
            candidates = self._resolve(slot_name, slot, slots, context)
            if candidates:
                result[slot_name] = self._select_best(candidates)
        return result

    def _resolve(
        self, slot_name: str, slot: SlotValue,
        all_slots: dict, context: ParseContext
    ) -> list[tuple[str, float]]:
        # Step 1: 约束框架匹配
        frame_name = f"{slot_name}({slot.value})"
        rules = self.library.get_frame(frame_name)
        if not rules:
            return []

        candidates: dict[str, float] = {}
        for rule in rules:
            for c in rule.candidates:
                candidates[c] = candidates.get(c, 0) + 1.0 / len(rule.candidates)

        # Step 2: 跨维度交叉验证
        for rule in rules:
            for other_slot, excluded_values in rule.incompatible_with.items():
                if other_slot in all_slots:
                    ov = all_slots[other_slot].value
                    if ov in excluded_values:
                        candidates = {k: v for k, v in candidates.items() if k not in excluded_values}

        # Step 3: 上下文补充
        for entity_list in context.entities.values():
            for entity in entity_list:
                if entity not in candidates:
                    candidates[entity] = 0.5

        # Step 4: 排序输出
        if not candidates:
            return []
        sorted_c = sorted(candidates.items(), key=lambda x: -x[1])
        top_score = sorted_c[0][1]
        result = []
        for value, score in sorted_c[:3]:
            normalized = score / top_score if top_score > 0 else 0
            conf = 0.7 + normalized * 0.2
            result.append((value, min(conf, 0.9)))
        return result

    def _select_best(self, candidates: list[tuple[str, float]]) -> SlotValue:
        return SlotValue(
            value=candidates[0][0], confidence=candidates[0][1],
            source="rule", overridden=True
        )

    def resolve_all(self, slots: dict[str, SlotValue], context: ParseContext) -> dict[str, SlotValue]:
        """全量消解: 跳过 LLM 置信度（当所有维度 confidence < 0.75 时使用）"""
        result = dict(slots)
        for slot_name, slot in slots.items():
            candidates = self._resolve(slot_name, slot, slots, context)
            if candidates:
                result[slot_name] = self._select_best(candidates)
        return result

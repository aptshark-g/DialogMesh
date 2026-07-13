"""Chinese locale."""
LOCALE = {
    # App
    "app.title": "DialogMesh v4",
    "app.tagline": "认知运行时",

    # CLI - Runtime
    "cli.starting": "正在启动认知运行时...",
    "cli.started": "运行时已启动，{count} 个适配器",
    "cli.stopped": "运行时已停止",
    "cli.not_running": "运行时未启动",
    "cli.event_sent": "事件已发送: {text}",
    "cli.start_failed": "启动失败: {error}",

    # CLI - Status
    "cli.status.header": "{path}: {triggers} 次触发, {success} 成功, {failure} 失败, {latency:.0f}ms 总延迟",

    # CLI - Pipeline
    "cli.pipeline.created": "流水线 '{name}' 已创建",
    "cli.pipeline.not_found": "流水线 '{name}' 不存在",
    "cli.pipeline.added": "已添加 {module} [{type}] 到 '{pipeline}'",
    "cli.pipeline.connected": "已连接 {from_mod} -> {to_mod}",
    "cli.pipeline.param_set": "已设置 {module}.{key} = {value}",
    "cli.pipeline.exported": "已导出 '{name}' 到 {path}",
    "cli.pipeline.default_created": "默认 v4 DAG 已创建: {nodes} 个节点, {edges} 条边",
    "cli.pipeline.no_pipelines": "暂无流水线",

    # CLI - Inspect
    "cli.inspect.error": "查看错误: {error}",
    "cli.inspect.unknown": "未知查看命令: {cmd}",
    "cli.no_observations": "暂无观测数据",
    "cli.no_skills": "暂无技能",
    "cli.no_knowledge": "(暂无冻结知识)",
    "cli.no_hypotheses": "(暂无假说)",

    # CLI - Events
    "cli.events.replayed": "已重放 {count} 个事件",
    "cli.events.no_events": "暂无事件",
    "cli.events.showing": "显示 {shown}/{total} 个事件",

    # CLI - Maintenance
    "cli.maint.gc_done": "GC 完成",
    "cli.maint.nodes": "节点: {count}",
    "cli.maint.edges": "边: {count}",
    "cli.maint.tiers": "分层: 热={hot}, 温={warm}, 冷={cold}, 归档={archive}",

    # CLI - Search
    "cli.search.results": "搜索: {keyword} ({count} 个结果)",
    "cli.search.no_results": "未找到: {keyword}",

    # CLI - Export
    "cli.export.knowledge": "已导出 {count} 条知识到 {path}",
    "cli.export.skills": "已导出 {count} 个技能到 {path}",

    # CLI - Snapshot
    "cli.snapshot.restored": "快照 {id} 已找到且有效",
    "cli.snapshot.not_found": "快照 {id} 未找到",
    "cli.snapshot.no_snapshots": "暂无快照",

    # CLI - Config
    "cli.config.set": "已设置 {key} = {value} (仅本次运行时生效)",

    # CLI - Health
    "cli.health.pass": "通过",
    "cli.health.fail": "失败",
    "cli.health.info": "信息",
    "cli.health.all_pass": "所有检查通过",
    "cli.health.some_fail": "部分检查失败",

    # TUI
    "tui.dashboard.title": "DialogMesh v4 认知运行时",
    "tui.dashboard.engine_off": "引擎未启动",
    "tui.dashboard.obs_pool": "观测池: {count} 个包",
    "tui.dashboard.last_ctx": "上次上下文: {intent} ({items} 项)",
    "tui.observations.title": "观测数据",
    "tui.hypotheses.title": "假说竞争 (活跃)",
    "tui.knowledge.title": "知识库 (已冻结)",
    "tui.skills.title": "技能工坊",
    "tui.world.title": "语义世界模型",
    "tui.world.not_loaded": "世界图未加载",
    "tui.context.title": "上下文工程 (上次 IR)",
    "tui.context.no_data": "(尚未编译上下文)",
    "tui.events.title": "事件日志 (最近 20 条)",
    "tui.events.total": "总计: {total} 个事件, {unconsumed} 个未消费",
    "tui.world.graph_stats": "图: {world} ({nodes} 节点, {edges} 边)",

    # Commands / Help
    "help.usage": "命令: 输入文本=发送事件, status=查看状态, checkpoint=触发检查点, quit=退出",
}

def t(key, **kwargs):
    text = LOCALE.get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text

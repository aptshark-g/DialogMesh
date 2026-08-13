# 前端契约登记 — 全量格式清单（2026-08-06）

> 目的: 用户要求"把前端所有的格式都先记录"——类型契约 / API 端点 / 状态
> 存储三层全量登记, 作为前后端格式对齐的基准（此前格式不匹配反复出现:
> 类型落后、字段缺失、内存态缺失导致状态刷新吞掉前端操作）。
> 关联: FE_DEEP_AUDIT_ROUND2_20260806.md（编译归零 + 契约修复）。

## 一、三层结构总览

| 层 | 文件 | 数量 | 说明 |
|---|---|---:|---|
| 类型契约 | src/types/*.ts | 8 文件 | api.ts 主契约 130+ 类型, 其余按域拆分 |
| API 端点 | src/api/*.ts | 3 文件 | v6.ts 主端点 ~85 函数, v4.ts 5, session.ts 10 |
| 状态存储 | src/stores/*.ts | 9 store | Zustand 客户端状态（服务端状态 + UI 状态混存） |

> 端点→后端对照: v6.ts 全部 /v6/* + /v3/health; session.ts 全部 /v3/session/*;
> v4.ts /v4/* + /v3/*。后端注册见 core/agent/api/v6_app.py（_try_include 17 项
> + 固定路由）。

## 二、类型契约全量（机器提取, 字段级）

> 来源: 2026-08-06 脚本扫描 src/types/*.ts（ASCII 提取, 字段/类型简写）。

```text

=== types/api.ts ===
  [interface] CreateSessionResponse:
      session_id: string;
      created_at: string;
      ws_url: string;
      status: 'active' | 'initializing' | 'error';
      capabilities: string[];
      session_ttl_seconds: number;
  [interface] SendMessageResponse:
      message_id: string;
      session_id: string;
      status: 'accepted' | 'rejected' | 'error';
      content: string;
      response_format: string;
      intent: string;
      task_graph: TaskGraphNode[] | null;
      clarifications: ClarificationItem[];
      suggestions: string[];
      latency_ms: number;
      error: string | null;
  [interface] ClarifyResponse:
      status: 'accepted' | 'rejected' | 'error';
      clarification_id: string;
      intent: string;
      clarifications: ClarificationItem[];
      suggestions: string[];
      error: string | null;
  [interface] HistoryRecord:
      message_id: string;
      role: 'user' | 'assistant' | 'system';
      content: string;
      timestamp: string;
      metadata?: Record<string, unknown>;
      intent?: string;
      latency_ms?: number;
  [interface] HistoryResponse:
      session_id: string;
      messages: HistoryRecord[];
      has_more: boolean;
      total_turns: number;
  [interface] SessionStatusResponse:
      session_id: string;
      state: 'idle' | 'processing' | 'clarifying' | 'error' | 'closed' | 'active' | 'waiting_clarification' | 'responding';
      current_turn: number;
      pending_clarification: boolean;
      last_activity_at: string;
      expires_at: string;
      resolved_entities: Record<string, unknown>;
      cognitive_profile: Record<string, unknown>;
      fsm: string | Record<string, unknown>;
  [interface] HealthResponse:
      status: string;
      [key: string]: unknown;
  [interface] ClarificationItem:
      id: string;
      field: string;
      question: string;
      type: 'choice' | 'text' | 'confirm';
      options?: string[];
      required: boolean;
      context?: string;
  [interface] TaskGraphNode:
      id: string;
      name: string;
      type: string;
      status: 'pending' | 'running' | 'completed' | 'failed';
      dependencies: string[];
      progress?: number;
      result?: string;
      params?: Record<string, any>;
      checkpoint?: boolean;
  [interface] ConnectionStatus:
      connected: boolean;
      connecting: boolean;
      error: string | null;
      lastPingAt: string | null;
  [type] SessionState: 
  [interface] SessionSummary:
      session_id: string;
      created_at: string;
      last_activity_at: string;
      state: string;
      current_turn: number;
      message_preview?: string;
  [type] ClientMessageType: 
  [interface] WebSocketClientMessage:
      type: ClientMessageType;
      payload: Record<string, unknown>;
      client_timestamp?: number;
      request_id?: string;
  [interface] WebSocketServerEvent:
      event_type: ServerEventType;
      payload: Record<string, unknown>;
      server_timestamp: number;
      request_id?: string;
      session_id?: string;
  [type] WsClientMessageType: 
  [type] WsServerEventType: 
  [interface] WsPingPayload:
      echo?: string;
  [interface] WsMessagePayload:
      content: string;
      context?: Record<string, unknown>;
  [interface] WsClarifyPayload:
      clarification_id: string;
      answers: Record<string, unknown>;
  [interface] WsHeartbeatPayload:
      interval_ms?: number;
      timestamp?: number;
  [interface] ConnectionState:
      connected: boolean;
      connecting: boolean;
      reconnecting: boolean;
      lastPingAt: string | null;
      error: string | null;
  [interface] Message:
      id: string;
      role: 'user' | 'assistant' | 'system';
      content: string;
      timestamp: number;
      status?: 'sending' | 'sent' | 'error' | 'streaming';
      intent?: string;
      taskGraph?: TaskGraphNode[];
      clarifications?: ClarificationItem[];
      suggestions?: string[];
      latencyMs?: number;
      thinkingSteps?: ThinkingStepPayload[];
  [interface] ChatMessage:
      id: string;
      role: 'user' | 'assistant' | 'system';
      content: string;
      timestamp: number;
      status?: 'sending' | 'sent' | 'error' | 'streaming';
      intent?: string;
      metadata?: {
      intent?: string;
      taskGraph?: TaskGraphNode[];
      clarifications?: ClarificationItem[];
      suggestions?: string[];
      latencyMs?: number;
      thinkingSteps?: ThinkingStepPayload[];
  [interface] ThinkingStep:
      step: number;
      description: string;
      timestamp: number;
  [interface] CognitiveProfile:
      reasoning_depth: number;
      context_window_usage: number;
      entity_count: number;
      topic_tree_depth: number;
      coherence_score: number;
  [interface] FSMState:
      current_state: string;
      previous_state: string;
      transitions: number;
      state_history: string[];
  [interface] TaskNode:
      node_id: string;
      parent_id: string | null;
      type: 'intent' | 'clarification' | 'execution' | 'validation';
      status: 'pending' | 'active' | 'completed' | 'failed';
      description: string;
      dependencies: string[];
      result?: unknown;
      latency_ms?: number;
  [interface] SessionBaseState:
      sessionId: string | null;
      wsConnected: boolean;
      wsConnecting: boolean;
      wsUrl: string | null;
      restBaseUrl: string;
      sessionState: SessionState | null;
      pendingClarification: boolean;
      currentTurn: number;
      cognitiveProfile: CognitiveProfile | null;
      fsm: FSMState | null;
      messages: Message[];
      isLoading: boolean;
      error: string | null;
      capabilities: string[];
      sessionTtl: number;
      expiresAt: string | null;
      lastActivityAt: string | null;
  [interface] SessionActions:
      setRestBaseUrl: (url: string) => void;
      setSessionId: (id: string | null) => void;
      setWsUrl: (url: string | null) => void;
      setWsConnected: (connected: boolean) => void;
      setWsConnecting: (connecting: boolean) => void;
      setSessionState: (state: SessionState | null) => void;
      setPendingClarification: (pending: boolean) => void;
      setCurrentTurn: (turn: number) => void;
      setCognitiveProfile: (profile: CognitiveProfile | null) => void;
      setFsm: (fsm: FSMState | null) => void;
      setCapabilities: (caps: string[]) => void;
      setSessionTtl: (ttl: number) => void;
      setExpiresAt: (expires: string | null) => void;
      setLastActivityAt: (activity: string | null) => void;
      addMessage: (message: Message) => void;
      updateMessage: (id: string, updates: Partial<Message>) => void;
      removeMessage: (id: string) => void;
      clearMessages: () => void;
      appendMessageContent: (id: string, content: string) => void;
      updateTaskGraph: (taskGraph: TaskNode[]) => void;
      setIsLoading: (loading: boolean) => void;
      setError: (error: string | null) => void;
      clearError: () => void;
      resetSession: () => void;
      initializeSession: (response: CreateSessionResponse) => void;
      syncFromStatus: (status: SessionStatusResponse) => void;
  [type] SessionStore: 
  [interface] ServerWebSocketEvent:
      type: ServerEventType;
      payload: Record<string, unknown>;
      server_timestamp: number;
      request_id?: string;
  [interface] ClientWebSocketMessage:
      type: ClientMessageType;
      payload: Record<string, unknown>;
      client_timestamp?: number;
      request_id?: string;
  [type] WebSocketClientType: 
  [interface] EventRequest:
      event_id: string;
      kind: string;
      payload: Record<string, unknown>;
      trace_id: string;
  [interface] EventResponse:
      status: string;
      event_id: string;
      response: string;
      llm_metrics?: Record<string, unknown>;
  [interface] IngestResponse:
      status: string;
      source_path: string;
      observation_count: number;
      type_distribution: Record<string, unknown>;
  [interface] StatusResponse:
      async: Record<string, unknown>;
      slow: Record<string, unknown>;
      deep: Record<string, unknown>;
  [interface] InspectResponse:
      module: string;
      count?: number;
      items?: unknown[];
      [key: string]: unknown;
  [interface] CheckpointResponse:
      status: string;
      results: { adapter: string; ok: boolean }[];
  [interface] V6ProfileResponse:
      oceAN_dims: Record<string, number>;
      mbti: string;
      turn_count: number;
      top_dimensions: string[];
      bfi_history: number;
      bfi_latest: Record<string, number>;
  [interface] V6ProfileEditRequest:
      dim?: string;
      value?: number;
      mbti?: string;
  [interface] V6ProfileEditResponse:
      updated: string[];
      feedback: string[];
  [interface] V6TraceResponse:
      reason_distribution: Record<string, number>;
      avg_confidence: number;
      total: number;
  [interface] V6AbcResponse:
      [key: string]: unknown;
  [interface] V6MindResponse:
      [key: string]: unknown;
  [interface] V6GraphNode:
      id: string;
      label?: string;
      type?: string;
      size?: number;
      temperature?: string;
      entities?: string[];
      state?: Record<string, unknown>;
  [interface] V6GraphEdge:
      source: string;
      target: string;
      type: string;
      weight: number;
  [interface] V6GraphResponse:
      nodes: V6GraphNode[];
      edges: V6GraphEdge[];
      subgraph_nodes: string[];
  [interface] V6DiscourseBlock:
      id: string;
      tree_id: string;
      topic: string;
      temperature: string;
      edus: number;
      children: string[];
      parent: string | null;
  [interface] V6DiscourseTreeResponse:
      blocks: V6DiscourseBlock[];
      total: number;
  [interface] V6ObjectNode:
      id: string;
      lifespan: string;
      relations: string[];
  [interface] V6ObjectEdge:
      source: string;
      target: string;
      type: string;
  [interface] V6ObjectsResponse:
      nodes: V6ObjectNode[];
      edges: V6ObjectEdge[];
      total_objects: number;
  [interface] V6Rule:
      name: string;
      premise: Record<string, unknown>;
      conclusion: Record<string, unknown>;
      confidence: number;
      hits: number;
      misses: number;
      source: string;
  [interface] V6RulesResponse:
      rules: V6Rule[];
      total: number;
  [interface] V6RuleEditRequest:
      name: string;
      conclusion?: Record<string, unknown>;
      confidence?: number;
  [interface] V6RuleEditResponse:
      updated: string;
      conclusion: Record<string, unknown>;
      confidence: number;
  [interface] V6FeedbackRequest:
      turn: number;
      correct: boolean;
      rule_name: string;
  [interface] V6FeedbackResponse:
      updated: boolean;
      rule?: string;
      hit?: boolean;
      mind_updated?: boolean;
      error?: string;
  [interface] V6PersistenceResponse:
      annotation_store: unknown;
      unified_store: unknown;
      oceAN_saved: boolean;
      rules_saved: boolean;
  [interface] V6SessionListItem:
      name: string;
      size: number;
  [type] V6SessionData: 
  [interface] V4WebSocketEvent:
      event_type: V4ServerEventType;
      payload: Record<string, unknown>;
      server_timestamp: number;
      request_id?: string;
  [interface] V4WebSocketMessage:
      type: 'message' | 'ping' | 'heartbeat';
      payload: Record<string, unknown>;
      client_timestamp?: number;
  [interface] V6ProviderInfo:
      name: string;
      model: string;
      healthy: boolean;
      stats?: Record<string, unknown>;
  [interface] V6ProvidersResponse:
      active: V6ProviderInfo;
      failover: {
      primary: string;
      fallback: string;
      active_idx: number;
      failures: number;
  [interface] V6ProviderSwitchRequest:
      provider?: string;
      base_url?: string;
      model?: string;
      api_key?: string;
  [interface] V6ProviderSwitchResponse:
      switched: string;
      model: string;
      healthy: boolean;
  [interface] V6TokensResponse:
      current: { turns: number; est_tokens: number };
      all_sessions: { count: number; est_tokens: number };
      rate: Record<string, string>;
  [interface] V6MetricsResponse:
      engine_uptime?: number;
      subsystems_loaded?: number;
      subsystems_total?: number;
      total_turn_count?: number;
      [key: string]: unknown;
  [interface] V6ContextConfigRequest:
      token_budget?: number;
      domain_P?: number;
      domain_C?: number;
      domain_K?: number;
      domain_E?: number;
      domain_B?: number;
  [interface] V6RouterMode:
      name: string;
      complexity: string;
      cost: string;
      latency: string;
  [interface] V6RouterModesResponse:
      available: boolean;
      modes: V6RouterMode[];
      active: string;
      force_mode: string | null;
      disabled: { remote: boolean; small_model: boolean };
      cost_budget: string;
      route_stats: Record<string, number>;
      complexity: { evaluator_available: boolean; last_score: number | null };
      degradation_chain: string[];
  [interface] V6RouterModesRequest:
      mode?: string;
      disable_remote?: boolean;
      disable_small_model?: boolean;
      cost_budget?: string;
  [interface] V6RelationsResponse:
      [key: string]: unknown;
  [interface] V6CausalResponse:
      [key: string]: unknown;
  [interface] V6BehaviorResponse:
      [key: string]: unknown;
  [interface] V6EngineeringResponse:
      [key: string]: unknown;
  [interface] V6PipelineResponse:
      [key: string]: unknown;
  [interface] V6ExtractionResponse:
      [key: string]: unknown;
  [interface] V6PerspectivesResponse:
      [key: string]: unknown;
  [interface] V6ParameterItem:
      name: string;
      value: number | string | boolean;
      description?: string;
      range?: [number, number];
      editable: boolean;
  [interface] V6ParametersResponse:
      parameters: V6ParameterItem[];
      total: number;
  [interface] V6ParameterEditRequest:
      parameters: Record<string, number | string | boolean>;
  [interface] V6ContextResponse:
      intent_category?: string;
      entries?: { domain: string; type: string; content: string; confidence: number; estimated_tokens: number }[];
      total_tokens?: number;
      [key: string]: unknown;
  [interface] V6MindFullResponse:
      [key: string]: unknown;
  [interface] V6PersistenceGraphsResponse:
      graphs: { name: string; node_count: number; edge_count: number; updated_at: string }[];
  [interface] V6GatewayModel:
      id: string;
      display: string;
      context: number;
      cost_in: number;
      cost_out: number;
      max_output?: number;
      capabilities?: string[];
  [interface] V6GatewayProvider:
      name: string;
      display_name: string;
      configured: boolean;
      healthy: boolean | null;
      base_url: string;
      models: V6GatewayModel[] | null;
      api_key?: string;
  [interface] V6GatewayProvidersResponse:
      providers: V6GatewayProvider[];
      active_provider: string;
      active_model: string;
  [interface] V6GatewayProviderConfigRequest:
      api_key?: string;
      base_url?: string;
  [interface] V6GatewayProviderConfigResponse:
      name: string;
      configured: boolean;
      healthy: boolean;
      models_fetched: number;
  [interface] V6GatewayTestResponse:
      name: string;
      healthy: boolean;
      latency_ms: number;
      models_available: number;
      error: string | null;
  [interface] V6GatewayModelsResponse:
      name: string;
      models: V6GatewayModel[];
  [interface] V6GatewayActiveRequest:
      provider: string;
      model: string;
  [interface] V6GatewayActiveResponse:
      active_provider: string;
      active_model: string;
      healthy: boolean;
      switched_at: string;
  [interface] V6GatewayConfig:
      active_provider: string;
      active_model: string;
      failover_chain: string[];
      auto_failover: boolean;
      max_retries: number;
      timeout_ms: number;
      stats: Record<string, {
      calls: number;
      errors: number;
      avg_latency_ms: number;
      total_tokens: number;
  [interface] V6GatewayConfigRequest:
      failover_chain?: string[];
      auto_failover?: boolean;
      max_retries?: number;
      timeout_ms?: number;
  [interface] V6GatewayUsageSession:
      provider: string;
      model: string;
      turns: number;
      prompt_tokens: number;
      completion_tokens: number;
      cost_estimate: string;
      latency_avg_ms: number;
  [interface] V6GatewayUsage:
      current_session: V6GatewayUsageSession;
      all_sessions: {
      total_tokens: number;
      total_cost: string;
      by_provider: Record<string, { tokens: number; cost: string }>;
  [interface] V6GatewayStats:
      requests: number;
      tokens: number;
      latency_p50: number;
      latency_p95: number;
      latency_p99: number;
      cache_hit_rate: number;
      errors_by_provider: Record<string, number>;
      requests_by_model: Record<string, number>;
  [interface] V6GatewayHealth:
      status: string;
      providers_total: number;
      providers_healthy: number;
      circuits: Record<string, string>;
  [interface] V6ServiceStatus:
      name: string;
      url: string;
      healthy: boolean;
      latency_ms: number | null;
      version: string | null;
      error: string | null;
  [interface] V6MetaStatsResponse:
      queue_size: number;
      pending: number;
      reviewed: number;
      decisions_total: number;
      self_audit: {
      accuracy: number;
      by_verdict: Record<string, number>;
  [interface] V6MetaQueueResponse:
      [key: string]: unknown;
  [interface] V6VersionCommit:
      id: string;
      ts: number;
      author: string;
      before: string;
      after: string;
      reason: string;
      verify: string;
  [interface] V6VersionsResponse:
      target: string;
      commits: V6VersionCommit[];
  [interface] V6InertiaResponse:
      total_patterns: number;
      stable: number;
      confirmed: number;
      breaking: number;
      by_weight: Record<string, number>;
      constraints: string[];
  [interface] V6BehaviorPattern:
      trigger: string;
      predicted: string;
      confidence: number;
      support: number;
      verdict: string;
  [interface] V6BehaviorPatternsResponse:
      patterns: V6BehaviorPattern[];
      stats: {
      total_patterns: number;
      user_approved: number;
  [interface] V6BehaviorFeedbackRequest:
      pattern_id: string;
      correct: boolean;
  [interface] V6Annotation:
      id: string;
      text: string;
      timestamp: string;
      author: string;
  [interface] V6AnnotationsResponse:
      annotations: V6Annotation[];
      total: number;
  [interface] V6AnnotationStatsResponse:
      total: number;
      by_author: Record<string, number>;
      by_date: Record<string, number>;
  [interface] V6ProfileCorrection:
      id: string;
      ts: number;
      author: string;
      before: string;
      after: string;
      reason: string;
      verify: string;
  [interface] V6ProfileCorrectionsResponse:
      corrections: V6ProfileCorrection[];
      total: number;
  [interface] V6MetaRetrospectDelta:
      value_change: number;
      direction?: 'increase' | 'decrease';
  [interface] V6MetaRetrospectResponse:
      target: string;
      delta: V6MetaRetrospectDelta;
      verdict: string;
  [interface] V6BehaviorPrediction:
      trigger: string;
      predicted: string;
      conf: number;
  [interface] V6BehaviorPredictResponse:
      recent_actions: string[];
      predictions: Record<string, V6BehaviorPrediction>;
  [interface] V6BeliefEntry:
      posterior: number;
      locked: boolean;
  [interface] V6BeliefResponse:
      total_hypotheses: number;
      locked: number;
      avg_evidence: number;
      by_hypothesis: Record<string, V6BeliefEntry>;
  [interface] V6OceanParamsResponse:
      applied: Record<string, string>;
      ocean: Record<string, number>;
  [interface] V6SubgraphEntry:
      domain: string;
      content: string;
  [interface] V6SubgraphResponse:
      perspective: string;
      domains: Record<string, number>;
      entries: V6SubgraphEntry[];
      total_tokens: number;
      budget: number;
  [interface] V6RecursiveMapResponse:
      total_nodes: number;
      by_level: Record<string, number>;
      high_coupling: number;
      expanded: number;
  [interface] V6RecursiveMapControlRequest:
      node: string;
      action: 'expand' | 'collapse';
  [interface] V6RecursiveMapControlResponse:
      node: string;
      action: string;
      expanded: boolean;
  [interface] V6EngineeringModule:
      name: string;
      type: string;
  [interface] V6EngineeringModulesResponse:
      modules: V6EngineeringModule[];
  [interface] V6EngineeringConstraintEditRequest:
      name: string;
      action: 'add_constraint' | 'remove_constraint';
      constraint: string;
  [interface] V6EngineeringConstraintEditResponse:
      updated: string;
      constraint: string;
  [interface] V6GraphEditRequest:
      action: 'update_weight' | 'add_edge' | 'remove_edge' | 'set_node';
      source?: string;
      target?: string;
      weight?: number;
      edge_type?: string;
      node_id?: string;
      node_state?: Record<string, unknown>;
  [interface] V6GraphEditResponse:
      edited?: 'edge' | 'node';
      source?: string;
      target?: string;
      weight?: number;
      node?: string;
      state?: Record<string, unknown>;
      error?: string;
  [interface] V6DiscourseTreeEditRequest:
      action: 'reclassify' | 'merge' | 'split' | 'rename';
      block_id: string;
      temperature?: string;
      topic?: string;
      parent_id?: string;
  [interface] V6DiscourseTreeEditResponse:
      edited?: 'temperature' | 'topic' | 'parent';
      block?: string;
      before?: string;
      after?: string;
      error?: string;
  [interface] V6ObjectEditRequest:
      action: 'relate' | 'unrelate' | 'rename' | 'set_lifespan';
      source?: string;
      target?: string;
      relation_type?: string;
      lifespan?: string;
      new_name?: string;
  [interface] V6ObjectEditResponse:
      edited?: 'relation_added' | 'relation_removed' | false;
      source?: string;
      target?: string;
      type?: string;
      reason?: string;
      error?: string;
  [interface] V6RelationEditRequest:
      action: 'update' | 'add' | 'remove';
      source?: string;
      target?: string;
      kind?: string;
      strength?: number;
  [interface] V6RelationEditResponse:
      edited?: 'relation' | 'added';
      source?: string;
      target?: string;
      error?: string;
  [interface] V6IrEditRequest:
      domain: string;
      entry_type?: string;
      content: string;
      confidence?: number;
  [interface] V6IrEditResponse:
      edited?: 'ir_entry_added';
      domain?: string;
      type?: string;
      error?: string;
  [interface] V6GatewayProviderAddRequest:
      name: string;
      base_url: string;
      api_key?: string;
      kind?: string;
      models?: V6GatewayModel[];
  [interface] V6GatewayProviderMutationResponse:
      error?: string;
      fallback?: string;
      [key: string]: unknown;
  [interface] V6SyncResponse:
      status?: string;
      pending?: number;
      block_id?: string;
      text?: string;
  [interface] V6CausalChainEvent:
      event: string;
      depth: number;
  [interface] V6CausalChainResponse:
      chain?: V6CausalChainEvent[];
      remaining?: number;
      tracked_chains?: number;
      avg_chain_length?: number;
      p90_chain_length?: number;
  [type] V6DegradationLevel: 
  [interface] V6TtlResponse:
      by_state?: Record<string, number>;
      total?: number;
      error?: string;
  [interface] V6TtlTickResponse:
      promoted?: string[];
      demoted?: string[];
      error?: string;
  [interface] V6SubgraphCacheResponse:
      size?: number;
      hits?: number;
      stale?: number;
      error?: string;

=== types/task.ts ===
  [type] TaskNodeType: | 'intent' | 'clarification' | 'execution' | 'validation' | 'decision' | 'parallel' | 'merge';
  [type] TaskExecutionStatus: | 'idle' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';
  [interface] TaskEdge:
      id: string;
      source: string;
      target: string;
      type: 'dependency' | 'conditional' | 'parallel';
      label?: string;
      condition?: TaskCondition;
  [interface] TaskCondition:
      type: 'always' | 'on_success' | 'on_failure' | 'custom';
      expression?: string;
      description?: string;
  [interface] TaskGraph:
      id: string;
      version: string;
      nodes: TaskNode[];
      edges: TaskEdge[];
      rootNodeId: string;
      createdAt: string;
      updatedAt: string;
      executionStatus: TaskExecutionStatus;
      overallProgress: number;
      metadata?: Record<string, unknown>;
  [interface] TaskExecutionRecord:
      nodeId: string;
      status: TaskNodeStatus;
      startedAt: string;
      completedAt?: string;
      latencyMs?: number;
      result?: string;
      error?: string;
  [interface] ExecutionPlan:
      graphId: string;
      parallelGroups: string[][];
      criticalPath: string[];
      estimatedDurationMs: number;
      riskNodes: string[];

=== types/graph.ts ===
  [interface] GraphNode:
      id: string;
      label: string;
      type?: string;
      intent?: string;
      cluster?: string;
      x?: number;
      y?: number;
      z?: number;
      val?: number;
      color?: string;
      description?: string;
      timestamp?: string;
      metadata?: Record<string, unknown>;
  [interface] GraphEdge:
      id: string;
      source: string;
      target: string;
      label?: string;
      type?: 'dependency' | 'causal' | 'similarity' | 'hierarchical' | 'reference';
      weight?: number;
      color?: string;
      dashed?: boolean;
  [type] ViewMode: 
  [interface] ClusterNode:
      id: string;
      label: string;
      nodeCount: number;
      centerX: number;
      centerY: number;
      color: string;
      density: number;
      topics: string[];
  [type] IntentColorKey: | 'scan-memory' | 'read-memory' | 'write-memory' | 'hack-value' | 'explain' | 'provide-code' | 'unknown';

=== types/chat.ts ===

=== types/profile.ts ===
  [interface] CognitiveDimension:
      key: string;
      label: string;
      value: number; // 0-100
      max: number;
      description?: string;
  [interface] CognitiveProfile:
      id: string;
      sessionId: string;
      timestamp: string;
      dimensions: CognitiveDimension[];
      overallScore: number;
      confidenceLevel: 'low' | 'medium' | 'high';
      summary?: string;
  [interface] ProfileStats:
      reasoningDepth: number;
      metacognition: number;
      expressionClarity: number;
      contextWindowUsage: number;
      entityCount: number;
      topicTreeDepth: number;
      coherenceScore: number;
      responseLatencyMs: number;
  [interface] IntentDistribution:
      intent: string;
      count: number;
      percentage: number;
      color: string;
      trend: 'up' | 'down' | 'stable';
      trendValue: number;
  [interface] EntityCloudItem:
      id: string;
      text: string;
      weight: number;
      category: string;
      color: string;
      frequency: number;
      relatedEntities: string[];
  [interface] RadarDataPoint:
      dimension: string;
      fullMark: number;
      value: number;

=== types/analytics.ts ===
  [interface] TrendDataPoint:
      date: string;
      label: string;
      turns: number;
      messages: number;
      avgLatency: number;
  [interface] TrendSeries:
      data: TrendDataPoint[];
      domain: [number, number];
  [interface] IntentDistributionItem:
      intent: string;
      label: string;
      count: number;
      color: string;
      percentage: number;
  [interface] IntentDistributionData:
      items: IntentDistributionItem[];
      total: number;
  [interface] WordCloudItem:
      text: string;
      weight: number;
      color: string;
  [interface] WordCloudData:
      words: WordCloudItem[];
      maxWeight: number;
      minWeight: number;
  [interface] SessionAnalytics:
      sessionId: string;
      createdAt: string;
      totalTurns: number;
      intents: Record<string, number>;
      keywords: string[];
      avgLatencyMs: number;
  [interface] GlobalAnalytics:
      sessionCount: number;
      totalTurns: number;
      totalMessages: number;
      avgLatencyMs: number;
      trendData: TrendDataPoint[];
      intentDistribution: IntentDistributionItem[];
      wordCloud: WordCloudData;
      activeSessionIds: string[];

=== types/ui.ts ===
  [interface] ConnectionState:
      status: 'connecting' | 'open' | 'closing' | 'closed' | 'error';
      latencyMs: number | null;
      lastError: string | null;

=== api/v6.ts ===
  fn getProfile()
  fn editProfile()
  fn getTrace()
  fn getAbc()
  fn getMind()
  fn getMindFull()
  fn getGraph()
  fn getDiscourseTree()
  fn getObjects()
  fn getRelations()
  fn getCausal()
  fn getBehavior()
  fn getEngineering()
  fn getRules()
  fn editRule()
  fn submitFeedback()
  fn getProviders()
  fn switchProvider()
  fn getTokens()
  fn testProviderConnection()
  fn getMetrics()
  fn updateContextConfig()
  fn getRouterModes()
  fn setRouterModes()
  fn getPipeline()
  fn getExtraction()
  fn getPerspectives()
  fn getParameters()
  fn editParameters()
  fn getContext()
  fn getPersistence()
  fn getHealth()
  fn getPersistenceGraphs()
  fn getSessions()
  fn getSessionData()
  fn getGatewayProviders()
  fn configGatewayProvider()
  fn testGatewayProvider()
  fn fetchGatewayProviderModels()
  fn setGatewayActive()
  fn getGatewayConfig()
  fn updateGatewayConfig()
  fn getGatewayUsage()
  fn getGatewayStats()
  fn getGatewayHealth()
  fn reloadGateway()
  fn addGatewayProvider()
  fn removeGatewayProvider()
  fn checkServiceStatus()
  fn checkDialogMeshStatus()
  fn checkSwitchGatewayStatus()
  fn getMetaStats()
  fn getMetaQueue()
  fn triggerMetaScan()
  fn triggerMetaRetrospect()
  fn getVersions()
  fn rollbackVersion()
  fn getInertia()
  fn getBehaviorPatterns()
  fn submitBehaviorFeedback()
  fn getBehaviorPredictions()
  fn getBelief()
  fn applyOceanParams()
  fn getSubgraph()
  fn getRecursiveMap()
  fn controlRecursiveMap()
  fn getEngineeringModules()
  fn editEngineeringConstraints()
  fn editGraph()
  fn editDiscourseTree()
  fn editObjects()
  fn editRelations()
  fn editIr()
  fn getAnnotations()
  fn addAnnotation()
  fn getAnnotationStats()
  fn getProfileCorrections()
  fn reviewProfileCorrections()
  fn submitProfileCorrections()
  fn getSync()
  fn getCausalChain()
  fn getDegradation()
  fn getTtl()
  fn tickTtl()
  fn getSubgraphCache()
  fn sendChatMessage()
  fn respondCheckpoint()

=== api/v4.ts ===
  fn sendEvent()
  fn ingestDocument()
  fn getStatus()
  fn inspectSystem()
  fn triggerCheckpoint()
  fn getHealth()
  fn getV4WsUrl()

=== api/session.ts ===
  fn createSession()
  fn sendMessage()
  fn submitClarification()
  fn getHistory()
  fn getSessionStatus()
  fn editDAG()
  fn saveTaskGraph()
  fn getTaskGraph()
  fn getHealth()

=== stores/analyticsStore.ts ===
  store useAnalyticsStore

=== stores/chatStore.ts ===
  store useChatStore

=== stores/graphStore.ts ===
  store useGraphStore

=== stores/overlayStore.ts ===
  store useOverlayStore

=== stores/profileStore.ts ===
  store useProfileStore

=== stores/sessionStore.ts ===
  store useSessionStore

=== stores/taskStore.ts ===
  store useTaskStore

=== stores/themeStore.ts ===
  store useThemeStore

=== stores/uiStore.ts ===
  store useUIStore
```

## 三、API 端点全量（v6.ts / v4.ts / session.ts）

> 完整函数清单在上节扫描输出内（=== api/xxx === 段）。端点→页面消费矩阵:

| 域 | 端点 | 消费页面 |
|---|---|---|
| 会话 | POST /v3/session; POST /v3/session/{id}/message; GET/PUT /v3/session/{id}/task-graph; POST .../dag-edit | ChatPage/ChatOverlay/TaskPlanningPage |
| 画像 | GET/PUT /v6/profile; /v6/trace; /v6/abc; /v6/mind; /v6/mind/full | CognitiveProfilePage |
| 图谱 | GET /v6/graph; /v6/discourse-tree; /v6/objects; PUT /v6/edit/*（graph/discourse-tree/objects/relations/ir）| ConversationGraphPage |
| 深层链 | /v6/relations; /v6/causal; /v6/behavior; /v6/engineering; /v6/behavior/patterns; /v6/behavior/predict; /v6/belief | DeepChainPage/BehaviorPage/EngineeringPage |
| 规则/反馈 | GET/PUT /v6/rules; POST /v6/feedback | EngineeringPage/SettingsPage |
| 提供商/网关 | /v6/providers*; /v6/gateway/*（providers/config/usage/stats/health/reload/active/cost/error-catalog）| GatewayPage/SettingsPage |
| 管道/参数 | /v6/pipeline; /v6/extraction; /v6/perspectives; /v6/parameters; /v6/context; /v6/router/modes | PipelinePage |
| 持久化 | /v6/persistence; /v6/persistence/graphs; /v6/subgraph; /v6/recursive-map | PipelinePage/DeepChainPage |
| 元认知 | /v6/meta/stats; /v6/meta/queue; /v6/meta/scan; /v6/meta/retrospect; /v6/versions/* | MetaCenterPage |
| 行为链 | /v6/inertia; /v6/behavior/feedback; /v6/behavior/predict; /v6/causal-chain | BehaviorPage |
| 注解/修正 | /v6/annotations*; /v6/profile/corrections* | DeepChainPage/Profile |
| 运维 | /v6/sync; /v6/ttl; /v6/degradation; /v6/subgraph-cache; /v6/metrics; /v3/health; /v4/status | SettingsPage/GatewayPage/PipelinePage |
| v4 通道 | /v4/event; /v4/ingest; /v4/checkpoint; /v4/inspect | ChatOverlay(useChat 归档)/Dashboard |

## 四、状态存储全量（Zustand stores）

| store | 状态域 | 消费方 | 持久化 |
|---|---|---|---|
| sessionStore | 会话/WS/消息/FSM/画像 | ChatPage/overlay/Dashboard | sessionStorage(chatStore) |
| chatStore | 消息/会话/思考态/activeProvider | ChatPage/ChatOverlay | sessionStorage(dm_chat_store) |
| graphStore | 图谱 nodes/edges/选中/模式/筛选 | ConversationGraphPage | 无（每页重拉）|
| taskStore | 任务图/执行状态/选中 | TaskPlanningPage | 无（后端 PUT）|
| profileStore | 画像列表/聚合/雷达 | CognitiveProfilePage | 无（每页重拉）|
| analyticsStore | 趋势/意图分布/词云 | DashboardPage | 无 |
| overlayStore | 聊天悬浮窗开合/未读 | ChatOverlay | 无 |
| uiStore | sidePanel 开合/标题/宽度 | Layout/SidePanel | 无 |
| themeStore | 主题 dark/light | 全局 | localStorage(dialogmesh-theme) |

## 五、状态分层审计 — 内存态 vs 持久化（用户核心关切）

### 5.1 问题定义（实测证据）

后端数据目前分三档:

1. **有内存态**（engine 属性, 进程内活对象）: `_discourse_tree` /
   `_behavior_graph` / `_meta_cognition` / `_tiered_storage` / `_world_objects` /
   `_registry` / `_decider` —— 前端读它们走 kernel dispatch（真数据）。
2. **直接落盘**（无内存态, 每次读文件）: `v3_sessions.json` / `task_graphs/*.json`
   / `providers/*.json` / 规则 / 参数 / 注解 —— `kernel_dispatch._disk_json()`。
3. **现构建**（每次请求重建）: 蓝图 DAG（`engine.build()` 每次消息处理现构建 →
   `sm.run_dag()` 执行 → 结果写 session 文件）。

**用户报告的具体问题**: LLM 规划图 → 后端直接把 task_graph 落盘
（v3_session_api.py:399-407 `json.dump`）→ 前端 TaskPlanningPage 编辑 →
保存 PUT 落盘 → 若消息处理/后台刷新再次写盘或前端重新 GET → **用户编辑被
状态刷新吞掉**（无内存态工作区 + 无版本冲突检测）。

### 5.2 受影响清单（初步, 待专项深挖）

| 数据 | 现状 | 风险 |
|---|---|---|
| task_graph（任务规划图）| 直接落盘 task_graphs/{sid}.json | **高** — 编辑易被重写覆盖 |
| 蓝图 DAG（LLM 规划）| 每次消息现构建, 无持久视图 | 中 — 前端看不到当前规划视图 |
| 图谱编辑（/v6/edit/*）| api_viz_edit 直接改引擎对象 | 中 — 无 before/after 回滚 UI |
| 规则/参数编辑 | 直接落盘 | 低 — 单值覆盖, 冲突少 |
| 注解/画像修正 | 直接落盘 | 中 — 多用户/多端并发会丢 |

### 5.3 业界成熟经验（回答"是否需要看专门经验"）

**是, 这类问题业界已有标准解法, 应当参考（不是重新发明）**:

1. **乐观更新 + 服务端确认**（React Query/SWR mutation 模式）: 前端先改本地
   状态 → 发请求 → 成功/失败回滚。任务图/图谱编辑应走此模式, 而不是
   "提交后重新拉全量"。
2. **内存态工作区 + 版本冲突检测**（etag/version 号）: 后端为可编辑资源
   （task_graph/dag）维护内存态 + `version` 字段; PUT 带 version, 不匹配返回
   409 冲突 → 前端提示"已被更新, 是否覆盖"。**这正是"操作被刷新吞掉"的标准
   解法**。
3. **CQRS / 事件溯源**（我们的 EventBus v2 + EventLog 已具备底座）: 写操作
   是"事件", 内存态是投影（projection）。前端编辑 = 追加编辑事件（不覆盖）,
   刷新 = 重放事件 → 永不吞操作。A17（记录永不可删）哲学同构。
4. **写缓冲/草稿层**（localStorage 或 store 内草稿）: 前端编辑先存本地草稿,
   网络/后端冲突时恢复草稿。TaskPlanningPage 已存 `confirmed_tg_{sid}` 到
   sessionStorage（雏形, 未形成闭环）。
5. **TanStack Query 缓存失效策略**: 按资源键（`['task-graph', sid]`）缓存,
   写后 invalidate 而不是整页刷新。

**本项目取舍建议**（对齐既有哲学）:
- 后端: 可编辑资源（task_graph / dag / 图谱）补**内存态工作区**（engine 持有）
  + `version` 字段 + PUT 冲突检测（409）。与 EventBus/持久化三层一致:
  内存态=热, 落盘=温/冷（tiered_storage 已存在可复用）。
- 前端: 写操作统一走**乐观更新 + 版本号**, 冲突弹"覆盖/保留本地"选择;
  编辑类页面（TaskPlanning/ConversationGraph）禁止"提交后全量刷新"路径。
- 这是 B5 绑定验证的**前置契约**（无版本检测前, 绑定后的编辑体验仍是坏的）。

## 六、登记维护约定

- 前端类型/端点/store 变更时, 更新本文档对应段（脚本可重跑生成）。
- 契约漂移的修复顺序: 先对齐类型（B4 已做一批）→ 再补后端字段 →
  最后做状态分层（§五）。
- 状态分层施工列为本阶段 B 的 P0（task_graph 版本化 + 前端乐观更新）。

---

## 七、施工更新（2026-08-06 晚）— task_graph 版本化完成 ✅

> 施工记录: `TASK_GRAPH_VERSIONING_IMPL_20260806.md`（阶段 B P0）。

### 契约变化（§三 端点矩阵更新）

| 端点 | 旧契约 | 新契约 |
|---|---|---|
| GET /v3/session/{id}/task-graph | `{nodes, edges}` | `{nodes, edges, version}`（内存优先/盘兜底） |
| PUT /v3/session/{id}/task-graph | `{nodes, edges}` 无条件覆盖 | `{nodes, edges, version?}`: 带 version=乐观更新+冲突检测; 不带=强制覆盖（向后兼容）; 过期 version → **409** `{error, current_version, nodes, edges}` |

### 前端对应
- `api/session.ts`: `TaskGraphData` / `TaskGraphConflictError` / `saveTaskGraph(..., version?)`
- `TaskPlanningPage`: versionRef + 自动保存带 version + 冲突提示条（覆盖服务端/放弃本地）

### 同型遗留（阶段 B P1）
- ConversationGraphPage /v6/edit/*（图谱编辑无版本）— 同方案推广

### 2026-08-06 更新（B1+B6 已完成 ✅, 记录 B1_B6_IMPL_20260806.md）

**B1 图谱编辑版本化（/v6/edit/*）**:
- 5 个编辑端点（graph/discourse-tree/objects/relations/ir）请求加
  `version?: number`; 落后 → 409 `{error, current_version}`
- 4 个 GET（graph/discourse-tree/objects/relations）返回 `version`
- 共享 `engine._viz_version`（内存态=热）
- 前端: `VizConflictError` + ConversationGraphPage 冲突条（覆盖服务端/加载最新）
- 验证: 5 新测试 + api 110/110 全绿

**B6 RightDock 三屏结构**:
- uiStore: `DockContentKey` + mode(auto/fixed) + 宽度拖拽（280–560, localStorage）
- RightDock: 路由联动 tab + 手动固定 + 6 内容（画像/上下文/工程链/任务/图例/思考流）
- Layout 接入; tsc 归零 + build 绿


### 2026-08-13 网关数据契约补充（switch /v1/* 透传）

- /v6/gateway/cost → switch /v1/usage: total_requests/total_tokens/by_provider + cost:{total, by_key, by_model, tenant_count} — 真实 token/请求/费用（按 key/model 分摊, usage_log.jsonl 持久化, 重启不丢）。
- /v6/gateway/error-catalog → switch /v1/error-catalog: 错误码 YAML（AUTH_FAILED/RATE_LIMITED/UPSTREAM_TIMEOUT/CONTEXT_WINDOW_EXCEEDED/...）。
- /v6/gateway/usage（既有）: 本地会话 monitor（data/monitor 估算）, 与网关真实计费（cost）不同源 — 页面"当前会话/累计用量"= 本地估算, "网关真实统计与计费"卡片 = cost/stats 透传。
- /v6/gateway/stats 真实字段: tokens_prompt/tokens_completion/cache_hits/cache_misses/requests_by_provider/requests_by_model/errors_by_provider/latency_by_provider/rate_limit_hits/circuit_opens/stream_requests/active_connections/uptime_seconds（V6GatewayStats 已对齐）。

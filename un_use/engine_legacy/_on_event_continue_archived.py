# ??: engine._on_event_continue (X6, 2026-08-04) ? 461 ????
# ??: on_event_sm ????????, ??????? (?? rg ???),
#       ????????? _compile_context (???, ? AttributeError)?
# A17 ??????: ????, ??/?????????
# ???: core/agent/runtime/engine.py L1122-1582

    def _on_event_continue(self, event, pcr_output=None, parse_result=None, unified_result=None, text=""):
        """Phase 2 of on_event — V4 Router after PCR."""
        # ---- V4.0 Cognitive Coordinate Router ----
        route = None
        if self._router_v4 is not None and text:
            try:
                result, route = self._router_v4.route(text, pcr_output=pcr_output)
                logger.debug('RouterV4: zone=%s cost=%dms', route.zone, route.cost_ms)
                self._publish("route_generated", {"zone": route.zone, "strategy": route.strategy})
                if self._decider:
                    from core.agent.state.global_decider import Command
                    self._decider.evolve(self._decider.decide(
                        Command(type="routing", payload={"zone": route.zone, "strategy": route.strategy})
                    ))
            except Exception as e:
                logger.debug('RouterV4 failed: %s', e)

        # ---- Intent Parser (Layer 1) ----
        parse_result = None
        intent_context = None
        if self._intent_parser is not None and text:
            try:
                # Build IntentContext from PCR output
                if pcr_output:
                    from core.agent.v3_common.models import IntentContext
                    intent_context = IntentContext.from_pcr_output(pcr_output)
                else:
                    intent_context = IntentContext()

                parse_result = self._intent_parser.parse(
                    user_input=text,
                    intent_context=intent_context,
                    parse_context=self._build_parse_context(),
                )
                self._last_intent_context = intent_context
                self._last_parse_result = parse_result
                cat = str(getattr(parse_result.intent, 'category', 'UNKNOWN')) if hasattr(parse_result, 'intent') else 'UNKNOWN'
                self._publish("intent_parsed", {"category": cat})
                if self._decider and parse_result:
                    from core.agent.state.global_decider import Command
                    cat = str(getattr(parse_result.intent, 'category', 'UNKNOWN')) if hasattr(parse_result, 'intent') else 'UNKNOWN'
                    self._decider.evolve(self._decider.decide(
                        Command(type="intent", payload={"category": cat})
                    ))
            except Exception as e:
                logger.warning('IntentParser failed: %s', e)

        # ---- Planning (Layer 1.5) ----
        plan_result = None
        if self._planner is not None and parse_result:
            try:
                intent = parse_result.intent if hasattr(parse_result, 'intent') else None
                if intent:
                    from core.agent.v3_legacy.data_models import IntentContext_v3
                    from core.agent.planner.skill_registry import SkillRegistry
                    plan_ctx = IntentContext_v3()
                    if pcr_output:
                        plan_ctx.expectation = getattr(pcr_output, 'expectation', None)
                        plan_ctx.complexity = getattr(pcr_output, 'complexity_level', 0.5)
                        plan_ctx.cognitive_profile = getattr(pcr_output, 'cognitive_profile', None)

                    # Skill matching
                    blueprint = None
                    if self._skill_matcher:
                        try:
                            intent_str = str(getattr(intent, 'category', intent))
                            blueprint = self._skill_matcher.match(intent_str)
                        except: pass

                    # Run async plan() in executor
                    import asyncio
                    loop = asyncio.new_event_loop()
                    try:
                        plan_result = loop.run_until_complete(
                            self._planner.plan(
                                intent=intent,
                                intent_context=plan_ctx,
                                blueprint=blueprint,
                            )
                        )
                    finally:
                        loop.close()
                    self._last_plan_result = plan_result
                    self._publish("plan_generated")
                    if self._decider and plan_result:
                        from core.agent.state.global_decider import Command
                        tg = getattr(plan_result, 'task_graph', None)
                        task_count = len(getattr(tg, 'nodes', [])) if tg else 0
                        self._decider.evolve(self._decider.decide(
                            Command(type="planning", payload={"task_count": task_count})
                        ))

                    # Submit TaskGraph to scheduler
                    if self._scheduler and hasattr(plan_result, 'task_graph') and plan_result.task_graph:
                        try:
                            self._scheduler.submit(plan_result.task_graph)
                        except: pass
            except Exception as e:
                logger.warning('Planning failed: %s', e)

        # ---- Context Engineering: compile CrossDomainContextIR ----
        self._compile_context(event, pcr_output=pcr_output, parse_result=parse_result, unified_result=unified_result)
        
        # ---- DiscourseBlockTree context injection (3-paradigm compass) ----
        if self._discourse_tree and self._last_context:
            try:
                session_id = getattr(event, 'session_id', 'default')
                tree = self._discourse_tree._trees.get(session_id)
                if tree and tree.blocks:
                    from core.agent.compiler.three_paradigm_context import ThreeParadigmContext
                    compass = ThreeParadigmContext(topic_tree=self._topic_tree)
                    block_list = list(tree.blocks.values())[:8]
                    discourse_ctx = compass.build(block_list, current_text=text,
                                                 max_tokens=2000)
                    if discourse_ctx:
                        from core.agent.context.cross_domain_ir import ContextEntry
                        entry = ContextEntry(
                            source="discourse_tree",
                            content=discourse_ctx,
                            relevance=0.7,
                        )
                        self._last_context.entries.append(entry)
                        logger.debug('Compass context injected: %s chars', len(discourse_ctx))
            except Exception as e:
                logger.debug('Discourse context injection skipped: %s', e)

        # ---- Association Chain L1→L2.5 (cold path, parallel to hot path) ----
        if text and self._l1_extractor:
            try:
                self._run_association_chain(event, text, pcr_output)
            except Exception as e:
                logger.debug('Association chain skipped: %s', e)

        # ---- BehaviorGraph: record event as step ----
        if self._causal_planner is not None:
            try:
                edge_id = self._causal_planner.record_step(
                    event, success=True, correction=False,
                )
                if edge_id:
                    logger.debug("CausalPlanner edge recorded: %s", edge_id)
            except Exception as e:
                logger.warning("CausalPlanner record_step failed: %s", e)
        # Legacy fallback via BehaviorGraphAdapter
        elif self._behavior_graph_adapter is not None:
            try:
                step_id = self._behavior_graph_adapter.record_event(event, success=True)
                if step_id:
                    logger.debug("BehaviorGraphAdapter step recorded: %s", step_id)
            except Exception as e:
                logger.warning("BehaviorGraphAdapter record failed: %s", e)

        # ---- CausalPlanner: trigger causal processing if chain long enough ----
        if self._causal_planner is not None:
            try:
                recent = self._causal_planner.get_recent_chain(max_steps=10)
                if len(recent) > CausalPlanner.MIN_CHAIN_LEN:
                    chain_result = self._causal_planner.process_chain()
                    if chain_result.triggered and chain_result.edge_updates:
                        logger.info(
                            "CausalPlanner triggered: %d priors updated from chain of %d",
                            len(chain_result.edge_updates), len(recent),
                        )
            except Exception as e:
                logger.debug("CausalPlanner trigger failed: %s", e)
        # Legacy fallback via CausalSubstrateAdapter
        elif self._causal_substrate_adapter is not None and self._behavior_graph_adapter is not None:
            try:
                recent = self._behavior_graph_adapter.get_recent_chain(n_steps=10)
                chain_len = len(recent.steps) if recent else 0
                if self._causal_substrate_adapter.should_trigger(chain_len):
                    ctx.world_graph = self._behavior_graph_adapter.graph
                    result = self._causal_substrate_adapter.execute(ctx)
                    if result.ok and result.data.get("triggered"):
                        logger.info(
                            "CausalSubstrate triggered: %d priors updated from chain of %d",
                            result.data.get("entry_count", 0), chain_len,
                        )
            except Exception as e:
                logger.debug("CausalSubstrate trigger failed: %s", e)

        # ---- LLM Generation: compile context → prompt → LLM → response ----

        # v6 Trace: snapshot state before reasoning
        pre_state = None
        if self._trace_v3:
            from core.agent.state.state_object import StateObject, TransitionReason, StateDelta
            pre_state = StateObject(data={
                "turn": self._turn_counter,
                "user_text": text[:200],
            })
            pre_state = self._trace_v3.snapshot(pre_state)

            # OBSERVE: concepts extracted, tree updated
            self._trace_v3.record_transition(
                reason=TransitionReason.OBSERVE,
                from_state=pre_state, to_state=pre_state,
                evidence=[f"Concepts: {concepts[:5] if concepts else []}", f"Text: {text[:60]}"],
                effects=[StateDelta(key="concept_count", operation="set", value=len(concepts))],
                confidence=0.85,
            )
            # Monitor
            if self._monitor:
                self._monitor.record_transition(self._turn_counter, "observe",
                    text[:60],
                    [{"concepts": concepts[:3] if concepts else []}])

            # REJECT: detect if user input signals rejection of previous answer
            reject_signals = ['wrong', 'incorrect', 're-read', 'you are wrong', "you're wrong",
                            'still wrong', 'not correct', 'no,', 'try again']
            if text and any(s in text.lower() for s in reject_signals):
                self._trace_v3.record_transition(
                    reason=TransitionReason.REJECT,
                    from_state=pre_state, to_state=pre_state,
                    evidence=[f"User rejected: {text[:60]}"],
                    effects=[StateDelta(key="reject_count", operation="inc", value=1)],
                    confidence=0.85,
                )
                if self._monitor:
                    self._monitor.record_transition(self._turn_counter, "reject",
                        f"User rejected: {text[:50]}", [])

            # ACTIVATE: DiscourseTree block activated
            sid = (event.refs.get('session_id') if hasattr(event,'refs') and event.refs.get('session_id') else event.payload.get('session_id', 'default')) if hasattr(event, 'payload') else 'default'
            tree = self._discourse_tree._trees.get(sid) if hasattr(self._discourse_tree, '_trees') else None
            if tree:
                self._trace_v3.record_transition(
                    reason=TransitionReason.ACTIVATE,
                    from_state=pre_state, to_state=pre_state,
                    evidence=[f"Blocks: {len(tree.blocks)}", f"Active: {len(tree.active_blocks())}"],
                    effects=[StateDelta(key="tree.block_count", operation="set", value=len(tree.blocks))],
                    confidence=0.75,
                )
                # Monitor ACTIVATE
                if self._monitor:
                    self._monitor.record_tree(self._turn_counter, len(tree.blocks),
                        len(tree.active_blocks()), len(tree.blocks) - 1)

        llm_response = self._call_llm(event, pcr_output=pcr_output, parse_result=parse_result, plan_result=plan_result, unified_result=unified_result)
        if llm_response:
            self._last_llm_response = llm_response

        # ---- Multi-hop subgraph refinement ----
        # If LLM response indicates missing context (asks about specific concepts),
        # expand subgraph for those concepts and re-call LLM. Max 3 rounds.
        llm_response = self._multi_hop_refine(event, llm_response, max_hops=3)
        if llm_response:
            self._last_llm_response = llm_response

        # ---- R5: feed cognitive profile from current turn (Track A + Track B) ----
        self._feed_profile_runtime(text, llm_response)

        # T2 (R1/R3): L3 feedback → tree_annotation + profile_update, after the
        # reply is produced so late intent refinement never blocks the answer.
        if self._last_association is not None:
            intent_result = self._last_association.get("intent_result")
            if intent_result is not None:
                self._apply_l3_feedback(intent_result)

                # ---- Internal Simulation: evaluate last prediction, simulate next ----
        if self._simulation_engine:
            try:
                if self._last_simulation and text:
                    feedback = self._simulation_engine.evaluate(self._last_simulation, text)
                    if feedback.matched:
                        self._simulation_stats["matches"] += 1
                    self._simulation_stats["total"] += 1
                    self._simulation_engine.learn(feedback)
                    if self._monitor:
                        self._monitor.record_simulation(self._turn_counter,
                            feedback.predicted_question, text, feedback.matched, feedback.similarity)
            except Exception as e:
                logger.debug("Sim evaluation skipped: %s", e)

            try:
                if llm_response and self._last_simulation:
                    user_understanding = ""
                    if self._conversation_tracker:
                        topics = self._conversation_tracker.recent_topics(3)
                        user_understanding = "; ".join(topics) if topics else ""
                    profile_summary = str(self._cognitive_profile.track_b)[:200] if self._cognitive_profile else ""
                    self._last_simulation = self._simulation_engine.simulate(
                        last_answer=llm_response,
                        user_understanding=user_understanding,
                        user_profile=profile_summary,
                    )
            except Exception as e:
                logger.debug("Sim generation skipped: %s", e)

        # ---- v6 Trace: record post-reasoning transition ----
        post_state = None
        if self._trace_v3 and llm_response and pre_state:
            from core.agent.state.state_object import Transition, TransitionReason, StateDelta, StateObject
            # INFER: LLM reasoning result
            post_state = self._trace_v3.states[-1] if self._trace_v3.states else StateObject()
            # Dynamic confidence from response quality
            dyn_conf = 0.7
            if len(llm_response) < 30 and any(w in llm_response.lower() for w in ['unsure','guessing','not sure']):
                dyn_conf = 0.35
            elif len(llm_response) < 50:
                dyn_conf = 0.55
            elif len(llm_response) > 500:
                dyn_conf = 0.80
            self._trace_v3.record_transition(
                reason=TransitionReason.INFER,
                from_state=pre_state, to_state=post_state,
                evidence=[f"Answer: {llm_response[:80]}"],
                effects=[
                    StateDelta(key="turn", operation="inc", value=1),
                    StateDelta(key="response_length", operation="set", value=len(llm_response)),
                ],
                confidence=dyn_conf,
            )

            # Monitor: record INFER transition
            if self._monitor:
                self._monitor.record_transition(self._turn_counter, "infer",
                    f"Answer: {llm_response[:60]}",
                    [{"response_len": len(llm_response)}])

        # ---- v6 Trace: reflect after profile update ----
        if self._trace_v3 and llm_response and pre_state:
            ta = getattr(getattr(self, '_cognitive_profile', None), 'track_a', None)
            if ta:
                self._trace_v3.record_transition(
                    reason=TransitionReason.REFLECT,
                    from_state=pre_state, to_state=post_state or pre_state,
                    evidence=[f"Profile updated: inertia={getattr(ta,'cognitive_inertia',0):.2f}"],
                    effects=[
                        StateDelta(key="profile.trust", operation="set", value=getattr(ta,'trust_score',0)),
                    ],
                    confidence=0.6,
                )

            # ---- v6 Contextual Strategy: record what worked ----
            if hasattr(self, '_strategy_engine') and self._strategy_engine:
                from core.agent.v4.cognitive.contextual_strategy import StrategyContext
                ctx = StrategyContext.from_engine(self)
                # Record the explanation strategy effectiveness (inferred from profile delta)
                trust_delta = getattr(ta, 'trust_score', 0.5) - 0.5
                self._strategy_engine.record(
                    "explain_answer",
                    ctx,
                    effectiveness=0.5 + trust_delta * 0.5,
                    confidence_gain=trust_delta,
                )

            # STRENGTHEN: confidence changed — record direction and magnitude
            if self._trace_v3 and ta and abs(trust_delta) > 0.01:
                reason = TransitionReason.STRENGTHEN if trust_delta > 0 else TransitionReason.WEAKEN
                self._trace_v3.record_transition(
                    reason=reason,
                    from_state=pre_state, to_state=post_state or pre_state,
                    evidence=[f"Trust delta: {trust_delta:+.3f}"],
                    effects=[StateDelta(key="trust", operation="set", value=getattr(ta,'trust_score',0.5))],
                    confidence=0.65,
                )
            # Monitor profile
            if self._monitor and ta:
                self._monitor.record_profile(self._turn_counter, ta,
                    {k: v.get('confidence', 0.5) if isinstance(v, dict) else getattr(v, 'value', 0.5)
                     for k, v in getattr(self._cognitive_profile, 'track_b', {}).items()})

            # ---- v6 InteractionGraph: propagate state through architecture ----
            if hasattr(self, '_interaction_graph') and self._interaction_graph and ta:
                trust = getattr(ta, 'trust_score', 0.5)
                deltas = self._interaction_graph.propagate(
                    "Observer",
                    {"confidence": trust, "attention": 0.5 + trust * 0.3},
                )
                if deltas:
                    logger.debug("InteractionGraph: %d deltas from Observer propagation", len(deltas))

        # ---- Behavior chain: feed conversation patterns to CausalPlanner ----
        if self._causal_planner is not None and text:
            try:
                pattern = self._conversation_tracker.behavior_pattern
                topic = self._conversation_tracker.get_current_topic()
                action_type = pattern[-1] if pattern else "unknown"
                action_summary = text[:120]
                if topic and action_type == "drill_down":
                    action_summary = f"[follow-up on: {topic[:60]}] {text[:60]}"
                self._causal_planner.record_step(
                    EventIR(id=f"behavior_{event.id}", kind="conversation.pattern",
                           payload={"text": text, "pattern": action_type, "topic": topic}),
                    success=True, correction=False,
                )
                logger.debug("Behavior chain fed: pattern=%s topic=%s", action_type, topic[:40] if topic else None)
            except Exception as e:
                logger.debug("CausalPlanner behavior feed skipped: %s", e)

        # ---- Feedback collection ----
        if self._feedback_signal and pas.success_count > 0:
            self._feedback_signal.with_implicit(accepted=(pas.failure_count == 0))

        # ---- Event counter and Slow Path auto-trigger ----
        if self._event_counter is not None:
            threshold_reached = self._event_counter.increment(n=1)
            if threshold_reached:
                logger.info(
                    "Event threshold reached (%d/%d), triggering Slow Path",
                    self._event_counter.count,
                    self._event_counter.threshold,
                )
                self.trigger_checkpoint()
                self._event_counter.reset()
                # Semantic extraction on Slow Path
                self._slow_extract()

        # ---- Path state: async -> IDLE (or BACKLOGGED if queue pressure) ----
        if self._path_state_machine is not None:
            if self._scheduler is not None and self._scheduler.get_queue(PathType.ASYNC):
                self._path_state_machine.transition("async", PathState.BACKLOGGED)
            else:
                self._path_state_machine.mark_success("async")

        # ---- Feed discourse tree compiler for hierarchical topic tracking ----
        if self._topic_tree_source is not None and text:
            try:
                turn_num = self._stats.get('async', PathStats('async')).trigger_count
                self._topic_tree_source.feed_turn(turn_index=int(turn_num), text=text)
            except Exception as e:
                logger.debug('TopicTree feed skipped: %s', e)

        # ---- v6 MetaConsumer: close the learning loop (every 5 turns) ----
        if self._meta_consumer and self._trace_v3 and self._turn_counter % 5 == 0:
            advice = self._meta_consumer.consume(self._trace_v3, self._turn_counter)
            if advice.get("adjust"):
                logger.info(
                    "Meta: %d warnings — %s",
                    len(advice.get("warnings", [])),
                    "; ".join(advice.get("suggestions", [])[:2]),
                )
                # Generate structured ReasoningPolicy (LLM-driven or rule fallback)
                if self._policy_generator:
                    # Use LLM-driven generator if available
                    if hasattr(self, '_llm_policy_generator') and self._llm_policy_generator:
                        trace_text = self._trace_v3.reasoning_path if self._trace_v3 else ""
                        self._active_policy = self._llm_policy_generator.generate(
                            advice, trace_summary=trace_text, turn_count=self._turn_counter
                        )
                    else:
                        self._active_policy = self._policy_generator.generate(advice)
                    # Monitor policy
                    if self._monitor and self._active_policy:
                        self._monitor.record_policy(self._turn_counter, self._active_policy)
                    # Persist learned patterns
                    if self._policy_generator:
                        self._policy_generator._pattern_learner.save()
                    # Mind: learn from trace, profile, and MetaConsumer warnings
                    if self._mind:
                        self._mind.learn(self)
                    logger.info(
                        "Policy: perspective=%s mode=%s depth=%d",
                        self._active_policy.perspective or '-',
                        self._active_policy.explanation_mode or '-',
                        self._active_policy.depth_adjust,
                    )

        return llm_response


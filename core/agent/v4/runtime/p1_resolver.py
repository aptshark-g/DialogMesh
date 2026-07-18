"""P1 Island Resolver — wire all remaining P1 modules into engine.

Modules:
  ViewManager → PerspectivePlanner (persistent camera)
  6 Domain Adapters → ObservationCompiler (behavior/dialogue/document/engineering/memory/user)
  DomainAdapters umbrella → engine registration
"""
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class P1Resolver:
    """Wire P1 islands into engine."""

    @staticmethod
    def wire_view_manager(engine) -> None:
        """P1: wire ViewManager into engine's perspective system."""
        try:
            from core.agent.v4.compiler.view_manager import ViewManager
            engine._view_manager = ViewManager()
            # Store current camera position for context injection
            if hasattr(engine, '_perspectives') and engine._perspectives:
                for p in engine._perspectives:
                    if hasattr(p, 'path'):
                        engine._view_manager.reframe(p.path, depth=2)
            logger.info("ViewManager wired: persistent camera active")
        except Exception as e:
            engine._view_manager = None
            logger.debug("ViewManager skipped: %s", e)

    @staticmethod
    def wire_domain_adapters(engine) -> Dict[str, Any]:
        """P1: wire 6 domain adapters into ObservationCompiler."""
        adapters = {}
        # Map domain names to their factory functions
        domain_factories = {
            "behavior": "core.agent.v4.observation_compiler.behavior_domain_adapter",
            "dialogue": "core.agent.v4.observation_compiler.dialogue_domain_adapter",
            "document": "core.agent.v4.observation_compiler.document_domain_adapter",
            "engineering": "core.agent.v4.observation_compiler.engineering_domain_adapter",
            "memory": "core.agent.v4.observation_compiler.memory_domain_adapter",
            "user": "core.agent.v4.observation_compiler.user_domain_adapter",
        }

        for domain, module_path in domain_factories.items():
            try:
                mod = __import__(module_path, fromlist=[f"create_{domain}_adapter"])
                factory = getattr(mod, f"create_{domain}_adapter", None)
                if factory:
                    adapter = factory()
                    adapters[domain] = adapter
            except Exception as e:
                logger.debug("Domain adapter %s skipped: %s", domain, e)

        # Wire umbrella domain adapters
        try:
            from core.agent.v4.compiler.domain_adapters import DomainAdapters
            umbrella = DomainAdapters()
            for domain, adapter in adapters.items():
                umbrella.register(domain, adapter)
            engine._domain_adapters = umbrella
            logger.info("DomainAdapters wired: %d/%d domains", len(adapters), 6)
        except Exception as e:
            engine._domain_adapters = adapters  # fallback
            logger.debug("DomainAdapters umbrella skipped: %s", e)

        return adapters

    @staticmethod
    def inject_view_in_context(engine, event) -> None:
        """Inject ViewManager camera state into context."""
        if not hasattr(engine, '_view_manager') or not engine._view_manager:
            return
        try:
            vm = engine._view_manager
            view = vm.current_view() if hasattr(vm, 'current_view') else None
            if view and engine._last_context:
                from core.agent.v4.context.cross_domain_ir import IREntry
                engine._last_context.add_entry(domain="K", entry=IREntry(
                    domain="K", type="camera_view",
                    content=f"[VIEW] {view.summary()}"[:300], confidence=0.8))
        except Exception as e:
            logger.debug("View injection skipped: %s", e)

    @staticmethod
    def inject_domain_observations(engine, event) -> None:
        """P1: run domain adapters against current event, inject domain observations."""
        if not hasattr(engine, '_domain_adapters') or not engine._domain_adapters:
            return
        try:
            from core.agent.v4.context.cross_domain_ir import IREntry
            adapters = engine._domain_adapters
            if isinstance(adapters, dict):
                for domain, adapter in adapters.items():
                    if hasattr(adapter, 'process_event'):
                        obs = adapter.process_event(event)
                        if obs and engine._last_context:
                            engine._last_context.add_entry(domain="D", entry=IREntry(
                                domain="D", type=f"{domain}_observation",
                                content=str(obs)[:300], confidence=0.6))
        except Exception as e:
            logger.debug("Domain injection skipped: %s", e)


def wire_p1(engine) -> int:
    """Wire all P1 modules. Returns count of successful wirings."""
    count = 0
    P1Resolver.wire_view_manager(engine)
    if getattr(engine, '_view_manager', None):
        count += 1

    adapters = P1Resolver.wire_domain_adapters(engine)
    count += len(adapters)

    logger.info("P1 wiring complete: %d modules", count)
    return count

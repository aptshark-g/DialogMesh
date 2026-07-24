"""Metacognitive Trigger → Engine Wiring.

Subscribes cold_blocks_high trigger to DiscourseBlockTree compress_cold_blocks.
"""

from core.agent.observability.metacognitive_trigger import MetacognitiveTriggerEngine
from core.agent.compiler.discourse_block_tree import DiscourseBlockTreeManager


def wire_trigger_to_engine(trigger: MetacognitiveTriggerEngine, 
                           discourse_tree: DiscourseBlockTreeManager,
                           llm=None):
    """Connect trigger events to their corresponding engine actions."""

    # Cold blocks > threshold → compress
    def on_cold_blocks(trigger_obj, value, event):
        for session_id in getattr(discourse_tree, '_trees', {}):
            try:
                count = discourse_tree.compress_cold_blocks(session_id, llm=llm)
                import logging
                logging.getLogger(__name__).info(
                    "Triggered compress_cold_blocks: %d upgraded, session=%s",
                    count, session_id)
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(
                    "compress_cold_blocks failed for %s: %s", session_id, e)

    trigger.subscribe("compress_cold_blocks", on_cold_blocks)
    return trigger


def wire_trigger_to_compressor(trigger: MetacognitiveTriggerEngine,
                                compressor):
    """Connect belief_entropy trigger to DerivationCompressor."""

    def on_entropy(trigger_obj, value, event):
        try:
            transitions = getattr(compressor, '_transition_buffer', [])
            if len(transitions) >= 5:
                chain = compressor.compress(
                    transitions[-10:], 
                    getattr(compressor, '_belief_trace', [])[-10:],
                    getattr(compressor, 'llm', None),
                )
                if chain:
                    import logging
                    logging.getLogger(__name__).info(
                        "Triggered compressor: chain %s", chain.get('chain_id', '?'))
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(
                "compressor trigger failed: %s", e)

    trigger.subscribe("compressor_ingest", on_entropy)
    return trigger

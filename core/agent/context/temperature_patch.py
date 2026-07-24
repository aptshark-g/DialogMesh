"""Context Manager Patch — temperature × information_value sorting."""

from core.agent.compiler.three_paradigm_context import ThreeParadigmContext


def patch_context_manager(context_manager):
    """Add temperature-based context sorting to ContextManager."""
    if not hasattr(context_manager, 'entries'):
        return context_manager

    compass = ThreeParadigmContext()

    def sort_context_entries():
        """Re-sort context entries by temperature × value priority."""
        if not context_manager.entries:
            return

        # Convert entries to block-like objects for compass scoring
        class FakeBlock:
            def __init__(self, entry):
                self.raw_text = getattr(entry, 'content', '') or ''
                self.entities = []
                self.status = 'active'
                self.summary = None

        blocks = [FakeBlock(e) for e in context_manager.entries]
        
        # Score each entry
        scored = []
        for i, (entry, block) in enumerate(zip(context_manager.entries, blocks)):
            value = compass._information_value(block)
            scored.append((value, i, entry))

        # Sort by information value descending (high value first)
        scored.sort(key=lambda x: -x[0])
        context_manager.entries = [s[2] for s in scored]

    # Patch
    original_append = getattr(context_manager, 'add_entry', None) or \
                      getattr(context_manager, 'append', None)
    
    if original_append:
        def append_and_sort(*args, **kwargs):
            result = original_append(*args, **kwargs)
            sort_context_entries()
            return result
        if hasattr(context_manager, 'add_entry'):
            context_manager.add_entry = append_and_sort
        else:
            context_manager.append = append_and_sort

    return context_manager

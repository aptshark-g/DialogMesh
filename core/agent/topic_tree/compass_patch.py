"""Topic Tree Patch — three-paradigm compass integration for routing."""

from core.agent.compiler.three_paradigm_context import ThreeParadigmContext


def patch_topic_tree_route(manager_v2):
    """Add three-paradigm compass routing to TopicTreeManagerV2."""
    if hasattr(manager_v2, '_compass'):
        return  # already patched
    
    original_route = manager_v2.route
    compass = ThreeParadigmContext(topic_tree=manager_v2)
    manager_v2._compass = compass
    
    def route_with_compass(text, *args, **kwargs):
        """Route with three-paradigm tags injected."""
        result = original_route(text, *args, **kwargs)
        if result:
            # Attach compass metadata to the matched topic node
            matched_node = getattr(result, 'node', None) or getattr(result, 'topic_node', None)
            if matched_node:
                blocks = getattr(matched_node, 'blocks', [])
                if blocks:
                    compass_ctx = compass.build(blocks, current_text=text, max_tokens=500)
                    result.compass = compass_ctx
        return result
    
    manager_v2.route = route_with_compass
    return manager_v2

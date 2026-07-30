"""v3.2 behavior_graph → merged to core.agent.behavior"""
from core.agent.behavior.graph_store import BehaviorGraph
from core.agent.behavior.models import BehaviorStep, BehaviorEdge, ColdStartSeed
from core.agent.behavior.statistics import GraphStatisticsCollector
from core.agent.behavior.cold_start import ColdStartManager
from core.agent.behavior.causal_discovery import LightweightCausalDiscovery as CausalDiscovery

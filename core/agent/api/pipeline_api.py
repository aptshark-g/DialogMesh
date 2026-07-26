"""v6 Pipeline Parameters API — ParameterRegistry CRUD."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pipeline-params"])


class ParameterEdit(BaseModel):
    key: str
    value: Any

class StrategySwitch(BaseModel):
    strategy: str  # balanced / conservative / aggressive / exploration / recovery


@router.get("/v6/parameters")
async def get_parameters():
    try:
        from core.agent.compiler.parameter_registry import get_registry
        reg = get_registry()
        return {
            "parameters": reg.all(),
            "namespaces": list(reg._namespace_index.keys()),
            "adaptive_count": sum(1 for p in reg._params.values() if p.adaptive),
        }
    except Exception as e:
        logger.debug("ParameterRegistry: %s", e)
        return {"parameters": {}, "namespaces": [], "adaptive_count": 0}


@router.post("/v6/parameters/edit")
async def edit_parameter(req: ParameterEdit):
    try:
        from core.agent.compiler.parameter_registry import get_registry
        reg = get_registry()
        success = reg.set(req.key, req.value)
        return {"key": req.key, "success": success, "value": reg.get(req.key)}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/v6/parameters/strategy")
async def switch_strategy(req: StrategySwitch):
    try:
        from core.agent.compiler.parameter_registry import get_registry
        reg = get_registry()
        count = reg.switch_strategy(req.strategy)
        return {"strategy": req.strategy, "changed": count}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/v6/context")
async def get_context_config():
    return {"context": {"assembler": "active", "budget_limit": 4000, "pruner": "enabled"}}

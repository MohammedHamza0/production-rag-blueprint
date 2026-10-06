"""Context Engineering package: PolicyGuard, IntentRouter, ShapeDetector, and AdaptiveContextManager."""

from src.context.context_manager import AdaptiveContextManager, AssembledContext
from src.context.intent_router import IntentResult, IntentRouter, QueryIntent
from src.context.policy_guard import GuardCheckResult, PolicyGuard
from src.context.shape_detector import ShapeDetector, ShapeResult

__all__ = [
    "PolicyGuard",
    "GuardCheckResult",
    "IntentRouter",
    "QueryIntent",
    "IntentResult",
    "ShapeDetector",
    "ShapeResult",
    "AdaptiveContextManager",
    "AssembledContext",
]

"""
Compound Condition Evaluator

Evaluates compound conditions with AND/OR logic.
"""

from typing import Dict, FrozenSet, List

from ....core.logging_config import get_logger
from .base import BaseConditionEvaluator

logger = get_logger(__name__)

# Signal flags that evaluators set on the context dict to trigger special actions in
# _evaluate_rule().  These must be propagated from sub-context back to the parent
# context after each sub-condition evaluation so that _evaluate_rule() can see them.
_SIGNAL_FLAGS: FrozenSet[str] = frozenset({"_hysteresis_just_deactivated"})


class CompoundConditionEvaluator(BaseConditionEvaluator):
    """
    Evaluates compound conditions with AND/OR logic.

    Supports:
    - AND logic (all conditions must be true)
    - OR logic (at least one condition must be true)
    - Nested compound conditions
    """

    def __init__(self, evaluators: List[BaseConditionEvaluator]):
        """
        Initialize compound evaluator.

        Args:
            evaluators: List of condition evaluators to use for sub-conditions
        """
        self.evaluators = evaluators

    def supports(self, condition_type: str) -> bool:
        """Check if this evaluator supports compound conditions."""
        return condition_type in ("compound", "logic")

    async def evaluate(self, condition: Dict, context: Dict) -> bool:
        """
        Evaluate compound condition.

        Args:
            condition: Condition dictionary with:
                - logic: "AND" or "OR"
                - conditions: List of sub-conditions
            context: Evaluation context (passed to sub-conditions)

        Returns:
            True if compound condition is met, False otherwise
        """
        # Check if this is a compound condition
        logic = condition.get("logic", "AND").upper()

        if logic not in ("AND", "OR"):
            logger.warning(f"Unknown logic operator: {logic}")
            return False

        # Get sub-conditions
        sub_conditions = condition.get("conditions", [])

        if not sub_conditions:
            logger.warning("Compound condition has no sub-conditions")
            return False

        # Evaluate all sub-conditions
        results = []
        for idx, sub_condition in enumerate(sub_conditions):
            # Set condition_index per sub-condition for correct hysteresis state keys.
            # AUT-41: exclude _stale_reasons from shallow copy to prevent duplication
            # during propagation — each sub-condition starts with a clean list.
            sub_context = {k: v for k, v in context.items() if k != "_stale_reasons"}
            sub_context["condition_index"] = idx

            # Find appropriate evaluator for this sub-condition
            cond_type = sub_condition.get("type", "unknown")

            evaluator = None
            for eval_obj in self.evaluators:
                if eval_obj.supports(cond_type):
                    evaluator = eval_obj
                    break

            if evaluator is None:
                logger.warning(f"No evaluator found for condition type: {cond_type}")
                # For AND logic, fail if we can't evaluate
                # For OR logic, continue (might still pass)
                if logic == "AND":
                    return False
                continue

            try:
                result = await evaluator.evaluate(sub_condition, sub_context)
                results.append(result)
                # B1-fix: propagate signal flags from sub-context to parent context.
                # sub_context is a shallow copy — flags set by evaluators (e.g.
                # _hysteresis_just_deactivated) are not visible in the parent context
                # without this step.
                for flag in _SIGNAL_FLAGS:
                    if sub_context.get(flag):
                        context[flag] = True
                # AUT-41: propagate stale reasons from sub-context to parent context
                sub_stale = sub_context.get("_stale_reasons")
                if sub_stale:
                    context.setdefault("_stale_reasons", []).extend(sub_stale)
            except Exception as e:
                logger.error(
                    f"Error evaluating sub-condition {cond_type}: {e}",
                    exc_info=True,
                )
                # On error, treat as False for AND, continue for OR
                if logic == "AND":
                    return False
                results.append(False)

        # Apply logic operator
        if logic == "AND":
            # All must be True
            return all(results) if results else False
        else:  # OR
            # At least one must be True
            return any(results) if results else False

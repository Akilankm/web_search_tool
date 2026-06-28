from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.product_evidence_harness.config import HarnessConfig
from src.product_evidence_harness.constants import TERMINATION_MAX_ITERATIONS, TERMINATION_NEEDS_REVIEW
from src.product_evidence_harness.contracts import AgentActionRecord, ProductSearchState
from src.product_evidence_harness.executor import HarnessExecutor
from src.product_evidence_harness.planner import HarnessPlanner


@dataclass
class BoundedHarnessLoop:
    config: HarnessConfig
    planner: HarnessPlanner
    executor: HarnessExecutor

    def run(self, state: ProductSearchState) -> ProductSearchState:
        for iteration in range(1, self.config.budget.max_iterations + 1):
            state.iteration = iteration
            action = self.planner.next_action(state)
            try:
                output = self.executor.execute(action, state)
                state.actions_taken.append(AgentActionRecord(iteration=iteration, action=action, success=True, output_summary=output))
            except Exception as exc:
                logger.exception("Harness action failed | action={}", action.action_type.value)
                state.actions_taken.append(AgentActionRecord(iteration=iteration, action=action, success=False, output_summary={}, error=str(exc)))
                # Failure should not kill the product; consume outcome and let planner choose a fallback if budget remains.
            if state.termination_reason:
                return state
        state.termination_reason = TERMINATION_MAX_ITERATIONS
        if not state.scorecards:
            state.termination_reason = TERMINATION_NEEDS_REVIEW
        return state

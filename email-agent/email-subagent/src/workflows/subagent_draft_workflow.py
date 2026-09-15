"""
SubagentDraftWorkflow: the subagent's own Temporal-backed execution.

Deliberately a single-activity workflow -- one pipeline doesn't need a
generic graph engine (same reasoning as CodeAnalysisFixWorkflow's own
docstring). Started by this service's own POST /draft handler (see
main.py), one workflow execution per drafting request. The single
activity is a real Claude Haiku call (see ../activities/subagent.py).
"""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..activities.subagent import draft_email_activity


@workflow.defn
class SubagentDraftWorkflow:
    @workflow.run
    async def run(self, to_email: str, subject: str, brief: str) -> dict:
        return await workflow.execute_activity(
            draft_email_activity,
            args=[to_email, subject, brief],
            # Must clear the activity's own draft_delay_seconds pause (90s by
            # default) with room for the model call on top.
            start_to_close_timeout=timedelta(minutes=5),
            # No retries: the activity now takes ~90s and ends in a real,
            # billable Haiku call, so a retry storm would cost three of them
            # and 4+ minutes. Matches MainAgentWorkflow's own reasoning for
            # call_subagent_activity.
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

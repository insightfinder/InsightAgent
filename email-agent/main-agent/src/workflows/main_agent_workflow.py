"""
MainAgentWorkflow: main agent -> (HTTP call to) subagent Pod -> human
confirmation -> real email send.

Unlike the earlier single-process version, "calling the subagent" here
means a real cross-Pod HTTP call (see ../activities/main_agent.py's
call_subagent_activity) -- the two agents are two separately deployed
services, each running its own Temporal worker.
"""
from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..activities.main_agent import call_subagent_activity, send_email_activity


def _split_subject_body(draft: str) -> tuple[str, str]:
    """Best-effort split of the subagent's "Subject: ...\\n\\nbody" draft.
    Pure function -- safe to run directly in workflow code (no I/O)."""
    lines = draft.strip().splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        return lines[0].split(":", 1)[1].strip(), "\n".join(lines[1:]).strip()
    return "Demo Email", draft.strip()


@workflow.defn
class MainAgentWorkflow:
    def __init__(self) -> None:
        self._status = "drafting"  # drafting|awaiting_confirmation|sending|sent|cancelled|failed
        self._draft = ""
        self._confirmed: Optional[bool] = None
        self._send_result: Optional[dict] = None
        self._error: Optional[str] = None

    @workflow.run
    async def run(self, user_message: str, to_email: str, subject: str) -> dict:
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            maximum_interval=timedelta(minutes=1),
            maximum_attempts=3,
        )
        try:
            draft_result = await workflow.execute_activity(
                call_subagent_activity,
                args=[to_email, subject, user_message],
                # Must outlast the subagent's draft_delay_seconds pause
                # (90s by default) plus its model call.
                start_to_close_timeout=timedelta(minutes=5),
                # A failed/timed-out model call is a result to report, not a
                # transient error worth Temporal silently retrying --
                # retrying would quietly re-spend a real Claude Haiku call
                # (same reasoning as CodeAnalysisFixWorkflow's own
                # generate_fix_activity, which uses maximum_attempts=1 for
                # the same reason).
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            self._draft = draft_result["draft"]

            self._status = "awaiting_confirmation"
            await workflow.wait_condition(
                lambda: self._confirmed is not None,
                timeout=timedelta(minutes=10),
            )

            if not self._confirmed:
                self._status = "cancelled"
                return self._result()

            self._status = "sending"
            # The subject the user typed is authoritative; only the body
            # is parsed back out of the draft.
            _, body = _split_subject_body(self._draft)
            self._send_result = await workflow.execute_activity(
                send_email_activity,
                args=[to_email, subject, body],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )
            self._status = "sent"
            return self._result()

        except Exception as e:
            self._status = "failed"
            self._error = str(e)
            return self._result()

    def _result(self) -> dict:
        return {
            "status": self._status,
            "draft": self._draft,
            "confirmed": self._confirmed,
            "send_result": self._send_result,
            "error": self._error,
        }

    @workflow.signal
    def confirm_send(self, confirmed: bool) -> None:
        self._confirmed = confirmed

    @workflow.query
    def get_status(self) -> dict:
        return self._result()

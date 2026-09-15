"""
Activities backing MainAgentWorkflow.

call_subagent_activity: the main agent hands the user's recipient + brief
to the email-subagent -- a SEPARATE Pod/service, not an in-process call --
over HTTP, which drafts the email with a real Claude Haiku call.

Both Pods' spans join into ONE trace: this activity runs in the worker
process, which instruments httpx (see worker.py) so the outgoing request
carries a traceparent header, and the subagent's FastAPI instrumentation
extracts it. That single shared trace ID is what makes the pair show up as
one multi-component trace rather than two unrelated ones.

send_email_activity: a REAL send via smtplib (stdlib), run in a thread
since smtplib is blocking and this is an async activity.
"""
import asyncio
import smtplib
from email.mime.text import MIMEText

import httpx
import structlog
from temporalio import activity

from ..config import get_settings

logger = structlog.get_logger()


@activity.defn
async def call_subagent_activity(to_email: str, subject: str, user_message: str) -> dict:
    settings = get_settings()
    # Longer than the subagent's draft_delay_seconds pause (90s by default);
    # /draft blocks until its workflow finishes.
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(
            f"{settings.subagent_url}/draft",
            json={"to_email": to_email, "subject": subject, "brief": user_message},
        )
        response.raise_for_status()
        result = response.json()
    logger.info("call_subagent_activity completed", draft_chars=len(result.get("draft", "")))
    return result


def _send_smtp(host: str, port: int, username: str, password: str, from_addr: str,
                to: str, subject: str, body: str) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to

    with smtplib.SMTP_SSL(host, port, timeout=30) as server:
        server.login(username, password)
        server.sendmail(from_addr, [to], msg.as_string())


@activity.defn
async def send_email_activity(to: str, subject: str, body: str) -> dict:
    settings = get_settings()
    if not (settings.smtp_username and settings.smtp_password):
        raise RuntimeError("SMTP_USERNAME/SMTP_PASSWORD are not configured")
    from_addr = settings.smtp_from or settings.smtp_username

    await asyncio.to_thread(
        _send_smtp,
        settings.smtp_host, settings.smtp_port,
        settings.smtp_username, settings.smtp_password,
        from_addr, to, subject, body,
    )
    logger.info("send_email_activity completed (real SMTP send)", to=to, subject=subject)
    return {"status": "sent", "to": to, "subject": subject}

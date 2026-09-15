import os
import sys

# Add email-agent/ so `from shared.observability...` works under local
# pytest too (same approach as github-agent's tests/conftest.py).
_AGENT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _AGENT_ROOT not in sys.path:
    sys.path.insert(0, _AGENT_ROOT)

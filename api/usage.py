import time
from typing import Optional
from .models import UsageRecord, ConversationSession

class UsageRecorder:
    def __init__(self, *, client_id: str, endpoint: str, session: Optional[ConversationSession] = None):
        self.client_id = client_id
        self.endpoint = endpoint
        self.session = session
        self.start_ts = time.time()
        self.tool_calls = 0
        self.success = True

    def inc_tool(self, n: int = 1):
        self.tool_calls += n

    def mark_failed(self):
        self.success = False

    def commit(self):
        latency_ms = int((time.time() - self.start_ts) * 1000)
        UsageRecord.objects.create(
            session=self.session,
            client_id=self.client_id,
            endpoint=self.endpoint,
            success=self.success,
            latency_ms=latency_ms,
            tool_calls=self.tool_calls,
        )

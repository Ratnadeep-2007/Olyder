"""Run-scoped cancellation, deadlines and redacted lifecycle events."""
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


class Cancelled(RuntimeError):
    pass


@dataclass
class RunControl:
    deadline: float
    cancelled: object = lambda: False
    sink: object = lambda event: None
    model_provider: object = None
    model_observations: list = field(default_factory=list)
    max_output_bytes: int = 16_000_000
    check_backend: object = None

    def check(self):
        if self.cancelled():
            raise Cancelled('User cancelled execution')
        if time.monotonic() >= self.deadline:
            raise TimeoutError('Overall run deadline exhausted')

    def emit(self, kind, **data):
        # Event observers receive metadata only, never prompts, env or raw logs.
        self.sink({'schema_version':1, 'type':kind, 'timestamp':time.time(), **data})


current = ContextVar('olyder_run_control', default=None)


@contextmanager
def activate(control):
    token = current.set(control)
    try:
        yield control
    finally:
        current.reset(token)

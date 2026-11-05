"""Two brakes on cost and loops.

spend(): a daily cap per kind of paid call, kept on disk so a restart doesn't
reset it. Handoffs: at most N hand-offs per window, so no chain of agents can
ping-pong. By design none can (each agent answers only one other, one way),
and this is the second lock.
"""

import json
import time
from datetime import date

CAPS = {"transcribe": 40, "model": 60}


def spend(path, kind: str, cap: int = None) -> bool:
    cap = CAPS[kind] if cap is None else cap
    today = date.today().isoformat()
    try:
        book = json.loads(path.read_text())
    except (OSError, ValueError):
        book = {}
    used = book.get(today, {}).get(kind, 0)
    if used >= cap:
        return False
    book = {today: {**book.get(today, {}), kind: used + 1}}  # older days dropped
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(book))
    return True


class Handoffs:
    def __init__(self, limit: int = 6, window: float = 600):
        self.limit, self.window, self.times = limit, window, []

    def allow(self) -> bool:
        now = time.monotonic()
        self.times = [t for t in self.times if now - t < self.window]
        if len(self.times) >= self.limit:
            return False
        self.times.append(now)
        return True

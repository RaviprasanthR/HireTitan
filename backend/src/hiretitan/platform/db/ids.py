"""UUIDv7 ids (RFC 9562), generated in the app (data-model conventions).

Layout: 48-bit Unix milliseconds | version 7 | 12-bit counter | variant | 62 random
bits. The counter keeps ids strictly increasing within one millisecond (and if
the wall clock steps back), so ids sort in creation order within this process.
"""

from __future__ import annotations

import os
import threading
import time
from uuid import UUID

_lock = threading.Lock()
_last_ms = 0
_counter = 0
_COUNTER_MAX = 0xFFF


def uuid7() -> UUID:
    global _last_ms, _counter
    with _lock:
        ms = time.time_ns() // 1_000_000
        if ms > _last_ms:
            _last_ms = ms
            _counter = int.from_bytes(os.urandom(2)) & 0x7FF  # leave headroom
        else:
            _counter += 1
            if _counter > _COUNTER_MAX:  # counter overflow: borrow the next ms
                _last_ms += 1
                _counter = 0
        ms, counter = _last_ms, _counter
    rand_b = int.from_bytes(os.urandom(8)) & ((1 << 62) - 1)
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= counter << 64
    value |= 0b10 << 62
    value |= rand_b
    return UUID(int=value)

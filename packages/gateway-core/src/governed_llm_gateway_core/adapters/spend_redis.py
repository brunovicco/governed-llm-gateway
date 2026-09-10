"""Estimated-spend ledger over a RESP server.

Amounts accumulate as integer micro-USD through INCRBY, which is exact and atomic: two
replicas recording concurrently cannot lose a fraction of a cent, and no floating-point
sum drifts. Like the other RESP adapters here, this imports no client library and uses
only core commands, so the server stays the operator's choice.

Each bucket carries an expiry sized to its window. A ledger of estimated spend is
operational evidence, not an accounting record, and keeping it indefinitely would be a
retention decision nobody made.
"""

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Protocol

DEFAULT_KEY_PREFIX = "governed-llm-gateway"

# Add and set the expiry together: an increment that outlived its window would let a
# closed bucket keep refusing requests forever.
_ADD_SCRIPT = """
local total = redis.call('INCRBY', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return total
"""


class RespSpendClient(Protocol):
    """The bounded slice of a RESP client this ledger needs."""

    def get(self, name: str) -> Awaitable[Any]:
        """Return the stored value for one key, or None."""
        ...

    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: Any,
    ) -> Awaitable[Any]:
        """Evaluate one Lua script server-side."""
        ...


@dataclass(frozen=True, slots=True)
class RedisSpendLedger:
    """Shared estimated-spend accumulation keyed by scope and window bucket."""

    client: RespSpendClient
    prefix: str = DEFAULT_KEY_PREFIX

    def __post_init__(self) -> None:
        """Reject a prefix that would let two deployments share a budget by accident."""
        if not self.prefix or self.prefix.strip() != self.prefix:
            raise ValueError("key prefix must be a non-empty normalized string")

    def ledger_key(self, scope: str, window_key: str) -> str:
        """Return the key accumulating one scope's spend in one window."""
        return f"{self.prefix}:spend:{scope}:{window_key}"

    async def observed_micros(self, scope: str, window_key: str) -> int:
        """Return spend already accumulated, treating an absent bucket as zero."""
        raw = await self.client.get(self.ledger_key(scope, window_key))
        if raw is None:
            return 0
        text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        try:
            return int(text)
        except ValueError:
            # A bucket that is not an integer cannot be reasoned about; surfacing it lets
            # the guard fail closed rather than silently treat corruption as zero spend.
            raise ValueError(f"spend bucket {scope}:{window_key} is not an integer") from None

    async def add_micros(
        self,
        scope: str,
        window_key: str,
        amount_micros: int,
        *,
        retention_seconds: int,
    ) -> int:
        """Add atomically and return the new total."""
        if amount_micros < 0:
            raise ValueError("recorded spend must not be negative")
        if retention_seconds <= 0:
            raise ValueError("retention_seconds must be positive")
        total = await self.client.eval(
            _ADD_SCRIPT,
            1,
            self.ledger_key(scope, window_key),
            str(amount_micros),
            str(retention_seconds),
        )
        return int(total)

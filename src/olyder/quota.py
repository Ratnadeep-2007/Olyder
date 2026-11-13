"""Conservative, identity-tracked local token reservations.

A budget is not a provider subscription limit, and external agent spend is unmetered.
"""
from dataclasses import dataclass, field


class QuotaExceeded(RuntimeError):
    pass


class Reservation(int):
    """Numeric token estimate carrying an opaque, one-use budget-specific ticket.

    Subclassing int preserves legacy numeric reporting; callers must pass the
    *original* reservation object into settle/release, not a re-created integer.
    """

    def __new__(cls, amount: int, ticket: int, owner: object):
        obj = int.__new__(cls, amount)
        obj.ticket = ticket
        obj.owner = owner
        return obj


@dataclass
class Budget:
    limit: int
    spent: int = 0
    reserved: int = 0
    calls: int = 0
    _active: dict[int, int] = field(default_factory=dict, init=False, repr=False)
    _next_ticket: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.limit) is not int or self.limit <= 0:
            raise ValueError("Token budget limit must be a positive integer")

    def reserve(self, prompt: str, output_cap: int) -> Reservation:
        if type(output_cap) is not int or output_cap < 0:
            raise ValueError("output_cap must be a nonnegative integer")
        # Heuristic, not an exact tokenization nor provider-account quota read.
        estimated = len(prompt.encode("utf-8")) + output_cap + 200
        if self.spent + self.reserved + estimated > self.limit:
            raise QuotaExceeded(f"Estimated token budget exceeded ({self.spent}/{self.limit} already used)")
        self.reserved += estimated
        self._next_ticket += 1
        self._active[self._next_ticket] = estimated
        return Reservation(estimated, self._next_ticket, self)

    def _consume(self, reservation: Reservation) -> int:
        if (
            not isinstance(reservation, Reservation)
            or reservation.owner is not self
            or self._active.get(reservation.ticket) != int(reservation)
        ):
            raise ValueError("Invalid, foreign, or already consumed quota reservation")
        size = self._active.pop(reservation.ticket)
        self.reserved -= size
        return size

    def settle(self, reservation: Reservation, actual: int | None) -> None:
        if actual is not None and (type(actual) is not int or actual < 0):
            raise ValueError("Provider usage must be a nonnegative integer")
        size = self._consume(reservation)
        # A provider can exceed the estimate; report the actual overage faithfully.
        self.spent += size if actual is None else actual
        self.calls += 1

    def release(self, reservation: Reservation) -> None:
        self._consume(reservation)

    def snapshot(self) -> dict:
        return {"limit": self.limit, "spent": self.spent, "calls": self.calls, "remaining_estimated": max(0, self.limit - self.spent - self.reserved)}

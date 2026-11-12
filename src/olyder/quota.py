"""Conservative, local budget accounting for LLM-backed planning and review."""
from dataclasses import dataclass


class QuotaExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    limit: int
    spent: int = 0
    reserved: int = 0
    calls: int = 0

    def __post_init__(self) -> None:
        if type(self.limit) is not int or self.limit <= 0:
            raise ValueError("Token budget limit must be a positive integer")

    def reserve(self, prompt: str, output_cap: int) -> int:
        if type(output_cap) is not int or output_cap < 0:
            raise ValueError("output_cap must be a nonnegative integer")
        # Conservative heuristic, NOT a guarantee or provider-account quota read.
        estimated = len(prompt.encode("utf-8")) + output_cap + 200
        if self.spent + self.reserved + estimated > self.limit:
            raise QuotaExceeded(f"Estimated token budget exceeded ({self.spent}/{self.limit} already used)")
        self.reserved += estimated
        return estimated

    def settle(self, reservation: int, actual: int | None) -> None:
        if reservation < 0 or reservation > self.reserved:
            raise ValueError("Invalid or duplicate quota settlement")
        if actual is not None and (type(actual) is not int or actual < 0):
            raise ValueError("Provider usage must be a nonnegative integer")
        self.reserved -= reservation
        # A provider may exceed the estimate; report the actual overage faithfully.
        self.spent += reservation if actual is None else actual
        self.calls += 1

    def release(self, reservation: int) -> None:
        if reservation < 0 or reservation > self.reserved:
            raise ValueError("Invalid or duplicate quota release")
        self.reserved -= reservation

    def snapshot(self) -> dict:
        return {"limit": self.limit, "spent": self.spent, "calls": self.calls, "remaining_estimated": max(0, self.limit - self.spent - self.reserved)}

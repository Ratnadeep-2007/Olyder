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

    def reserve(self, prompt: str, output_cap: int) -> int:
        # Conservative heuristic, NOT a guarantee or provider-account quota read.
        estimated = len(prompt.encode("utf-8")) + output_cap + 200
        if self.spent + self.reserved + estimated > self.limit:
            raise QuotaExceeded(f"Estimated token budget exceeded ({self.spent}/{self.limit} already used)")
        self.reserved += estimated
        return estimated

    def settle(self, reservation: int, actual: int | None) -> None:
        self.reserved -= reservation
        self.spent += max(0, reservation if actual is None else actual)
        self.calls += 1

    def release(self, reservation: int) -> None:
        self.reserved -= reservation

    def snapshot(self) -> dict:
        return {"limit": self.limit, "spent": self.spent, "calls": self.calls, "remaining_estimated": max(0, self.limit - self.spent - self.reserved)}

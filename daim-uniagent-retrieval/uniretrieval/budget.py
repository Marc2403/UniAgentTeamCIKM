"""Wall-clock budget guard for the 4-hour TIRA limit."""

import time
from typing import Callable


class Budget:
    def __init__(self, total_seconds: float, reserve_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.total_seconds = total_seconds
        self.reserve_seconds = reserve_seconds
        self._clock = clock
        self._start = clock()

    def elapsed(self) -> float:
        return self._clock() - self._start

    def remaining(self) -> float:
        return self.total_seconds - self.elapsed()

    def allows(self, estimated_seconds: float) -> bool:
        return self.remaining() - self.reserve_seconds >= estimated_seconds


class StageTimer:
    """Running per-item cost of a stage, to decide whether the next item still fits."""

    def __init__(self, budget: Budget, initial_estimate: float) -> None:
        self.budget = budget
        self.initial_estimate = initial_estimate
        self.items = 0
        self.seconds = 0.0

    def estimate(self) -> float:
        return self.seconds / self.items if self.items else self.initial_estimate

    def allows_next(self) -> bool:
        return self.budget.allows(self.estimate())

    def record(self, seconds: float) -> None:
        self.items += 1
        self.seconds += seconds

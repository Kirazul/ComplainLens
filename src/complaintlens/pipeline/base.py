"""Stage runner.

A *stage* is a function ``(ctx) -> StageResult`` that reads and writes a shared context dict.
``run_stages`` times each stage and turns crashes into ``status="error"`` results: one failing
stage must never lose the customer's message. The resulting list of ``StageResult`` is the trace
the console shows (plan §10.1, "Ticket X-ray").
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import Any

from complaintlens.schemas import StageResult

Context = dict[str, Any]
Stage = Callable[[Context], StageResult]


def run_stages(
    stages: Iterable[Stage],
    ctx: Context,
    on_stage: Callable[[StageResult], None] | None = None,
) -> list[StageResult]:
    """Run stages in order, recording a timed result for each; call ``on_stage`` after each one."""
    trace: list[StageResult] = []
    for stage in stages:
        start = time.perf_counter()
        try:
            result = stage(ctx)
        except Exception as exc:
            result = StageResult(
                name=getattr(stage, "stage_name", stage.__name__),
                status="error",
                note=f"{type(exc).__name__}: {exc}",
            )
        result.ms = round((time.perf_counter() - start) * 1000, 2)
        trace.append(result)
        if on_stage:
            on_stage(result)
    ctx["trace"] = trace
    return trace

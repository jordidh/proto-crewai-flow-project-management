import time
from contextvars import ContextVar
from typing import Any

from crewai import CrewOutput
from crewai.tasks.task_output import TaskOutput


def format_duration(seconds: float) -> str:
    """Format seconds as 'Xm Ys'."""
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes}m {secs}s"


def sum_token_usage(usages: list[dict[str, int]]) -> dict[str, int]:
    total: dict[str, int] = {}
    for usage in usages:
        for key, value in usage.items():
            if isinstance(value, int):
                total[key] = total.get(key, 0) + value
    return total


class CrewRunMetrics:
    """Times a crew run and each of its tasks, and logs the run KPIs.

    Wire `start` to @before_kickoff, `finish` to @after_kickoff, and
    `record_task_completed` as the crew's task_callback.
    """

    def __init__(self, crew_name: str) -> None:
        self.crew_name = crew_name
        self.started_at: float | None = None
        self.total_run_time_s: float | None = None
        self.tasks: list[dict[str, Any]] = []
        self._last_mark: float | None = None

    def start(self, inputs: dict[str, Any]) -> dict[str, Any]:
        self.started_at = self._last_mark = time.time()
        self.tasks = []
        _active_run.set(self)
        print(f"[{self.crew_name}] Crew run started")
        return inputs

    def task_completed(self, output: TaskOutput) -> None:
        # Tasks run sequentially, so a task's elapsed time is the time since the
        # crew started or the previous task finished.
        now = time.time()
        elapsed = now - (self._last_mark or now)
        self._last_mark = now
        word_count = len(output.raw.split()) if output.raw else 0
        self.tasks.append(
            {
                "task": output.name,
                "agent": output.agent,
                "elapsed_s": round(elapsed, 2),
                "word_count": word_count,
            }
        )
        print(
            f"[{self.crew_name}] Task completed: {output.name} | Agent: {output.agent} | "
            f"Elapsed: {elapsed:.2f}s | Output: {word_count} words"
        )

    def finish(self, output: CrewOutput) -> CrewOutput:
        self.total_run_time_s = time.time() - (self.started_at or time.time())
        print(f"[{self.crew_name}] Total crew run time: {format_duration(self.total_run_time_s)}")
        print(f"[{self.crew_name}] Tasks completed: {len(output.tasks_output)}")
        print(f"[{self.crew_name}] Token usage: {output.token_usage.model_dump()}")
        return output

    def summary(self, output: CrewOutput, latency_s: float) -> dict[str, Any]:
        return {
            "latency_s": round(latency_s, 2),
            "total_run_time": format_duration(self.total_run_time_s or 0),
            "tasks_completed": len(output.tasks_output),
            "token_usage": output.token_usage.model_dump(),
            "tasks": self.tasks,
        }


_active_run: ContextVar[CrewRunMetrics | None] = ContextVar("active_crew_run", default=None)


def record_task_completed(output: TaskOutput) -> None:
    """Task callback for the running crew.

    A module-level function, because crewai can't checkpoint crews whose callbacks are bound methods.
    """
    run_metrics = _active_run.get()
    if run_metrics:
        run_metrics.task_completed(output)

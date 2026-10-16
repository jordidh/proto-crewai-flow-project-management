#!/usr/bin/env python
import csv
import json
import time
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel

from crewai import CrewOutput
from crewai.flow import Flow, listen, start

from project_management.metrics import format_duration, sum_token_usage

from project_management.crews.initiation_and_governance_crew.initiation_and_governance_crew import (
    InitiationAndGovernanceCrew,
)
from project_management.crews.planning_and_scope_crew.planning_and_scope_crew import (
    PlanningAndScopeCrew,
)
from project_management.crews.risk_and_change_management_crew.risk_and_change_management_crew import (
    RiskAndChangeManagementCrew,
)
from project_management.crews.performance_and_control_crew.performance_and_control_crew import (
    PerformanceAndControlCrew,
)

INITIATION_DIR = Path("output") / "initiation"
INITIATION_ARTIFACTS = {
    "business_case": "business_case.md",
    "project_charter": "project_charter.md",
    "stakeholder_register": "stakeholder_register.md",
    "team_charter": "team_charter.md",
}
PLANNING_DIR = Path("output") / "planning"
PLANNING_ARTIFACTS = {
    "wbs": "wbs.md",
    "backlog": "backlog.md",
    "schedule_model": "schedule_model.json",
    "requirements_specification": "requirements_specification.md",
    "definition_of_done": "definition_of_done.md",
}
CONTROL_DIR = Path("output") / "control"
CONTROL_ARTIFACTS = {
    "risk_register": "risk_register.md",
    "change_log": "change_log.md",
    "change_request_rfc": "change_request_RFC.md",
}
PERFORMANCE_DIR = Path("output") / "performance"
PERFORMANCE_ARTIFACTS = {
    "evm_metrics": "evm_metrics.json",
    "project_dashboard": "project_dashboard.md",
    "status_report": "status_report.md",
}
S_CURVE_PATH = PERFORMANCE_DIR / "s_curve.csv"
RUN_METRICS_PATH = Path("output") / "logs" / "run_metrics.jsonl"
DEFAULT_BRIEF_PATH = Path("input") / "project_brief.md"
DEFAULT_PROGRESS_PATH = Path("input") / "progress_data.md"


class ProjectState(BaseModel):
    project_name: str = ""
    project_brief: str = ""
    trigger_reason: str = "Project inception"
    scope_change_request: str = ""
    emerging_conditions: str = ""
    progress_data: str = ""
    status_date: str = ""
    existing_artifacts: dict[str, str] = {}
    initiation_artifacts: dict[str, str] = {}
    planning_artifacts: dict[str, str] = {}
    control_artifacts: dict[str, str] = {}
    change_decision: str = ""
    performance_artifacts: dict[str, str] = {}
    s_curve: list[dict] = []
    flow_started_at: float = 0.0
    run_metrics: dict[str, dict] = {}


class ProjectManagementFlow(Flow[ProjectState]):

    def _kickoff_crew(self, crew_base, inputs: dict) -> CrewOutput:
        """Kick off a crew, timing its latency and recording its run metrics."""
        started = time.time()
        result = crew_base.crew().kickoff(inputs=inputs)
        latency = time.time() - started
        crew_name = type(crew_base).__name__
        self.state.run_metrics[crew_name] = crew_base.run_metrics.summary(result, latency)
        print(f"[{crew_name}] Latency: {latency:.2f}s")
        return result

    def _latest_artifact(self, key: str) -> str:
        """Return the artifact produced in this run, or the saved one if this run didn't produce it."""
        for artifacts in (
            self.state.initiation_artifacts,
            self.state.planning_artifacts,
            self.state.control_artifacts,
        ):
            if artifacts.get(key):
                return artifacts[key]
        return self.state.existing_artifacts.get(key, "")

    @start()
    def load_project_context(self, crewai_trigger_payload: dict = None):
        self.state.flow_started_at = time.time()
        payload = crewai_trigger_payload or {}
        if payload:
            print(f"Using trigger payload: {payload}")

        self.state.project_name = payload.get("project_name", "Sample Project")
        self.state.trigger_reason = payload.get("trigger_reason", "Project inception")
        self.state.scope_change_request = payload.get("scope_change_request", "")
        self.state.emerging_conditions = payload.get("emerging_conditions", "")
        self.state.status_date = payload.get("status_date", date.today().isoformat())
        if "progress_data" in payload:
            progress_data = payload["progress_data"]
            self.state.progress_data = (
                progress_data if isinstance(progress_data, str) else json.dumps(progress_data, indent=2)
            )
        elif DEFAULT_PROGRESS_PATH.exists():
            self.state.progress_data = DEFAULT_PROGRESS_PATH.read_text()
        if "project_brief" in payload:
            self.state.project_brief = payload["project_brief"]
        elif DEFAULT_BRIEF_PATH.exists():
            self.state.project_brief = DEFAULT_BRIEF_PATH.read_text()
        else:
            raise ValueError(
                f"No project brief provided. Pass 'project_brief' in the trigger "
                f"payload or create {DEFAULT_BRIEF_PATH}."
            )

        for directory, artifacts in (
            (INITIATION_DIR, INITIATION_ARTIFACTS),
            (PLANNING_DIR, PLANNING_ARTIFACTS),
            (CONTROL_DIR, CONTROL_ARTIFACTS),
            (PERFORMANCE_DIR, PERFORMANCE_ARTIFACTS),
        ):
            for key, filename in artifacts.items():
                path = directory / filename
                if path.exists():
                    self.state.existing_artifacts[key] = path.read_text()

        print(f"Project: {self.state.project_name} ({self.state.trigger_reason})")

    @listen(load_project_context)
    def run_initiation_and_governance(self):
        print("Running Initiation and Governance Crew")
        inputs = {
            "project_name": self.state.project_name,
            "project_brief": self.state.project_brief,
            "trigger_reason": self.state.trigger_reason,
            "current_date": date.today().isoformat(),
        }
        for key in INITIATION_ARTIFACTS:
            inputs[f"existing_{key}"] = self.state.existing_artifacts.get(key, "")

        result = self._kickoff_crew(InitiationAndGovernanceCrew(), inputs)

        for task_output in result.tasks_output:
            self.state.initiation_artifacts.update(task_output.pydantic.model_dump())

    @listen(run_initiation_and_governance)
    def save_initiation_artifacts(self):
        INITIATION_DIR.mkdir(parents=True, exist_ok=True)
        for key, filename in INITIATION_ARTIFACTS.items():
            (INITIATION_DIR / filename).write_text(self.state.initiation_artifacts[key])
            print(f"Saved {INITIATION_DIR / filename}")

    @listen(save_initiation_artifacts)
    def run_planning_and_scope(self):
        print("Running Planning and Scope Crew")
        trigger_reason = (
            "Scope modification" if self.state.scope_change_request else "Baseline planning"
        )
        inputs = {
            "project_name": self.state.project_name,
            "trigger_reason": trigger_reason,
            "scope_change_request": self.state.scope_change_request,
            "business_case": self.state.initiation_artifacts["business_case"],
            "project_charter": self.state.initiation_artifacts["project_charter"],
            "team_charter": self.state.initiation_artifacts["team_charter"],
            "current_date": date.today().isoformat(),
        }
        for key in PLANNING_ARTIFACTS:
            inputs[f"existing_{key}"] = self.state.existing_artifacts.get(key, "")

        result = self._kickoff_crew(PlanningAndScopeCrew(), inputs)

        wbs_and_schedule, requirements_and_dod = (t.pydantic for t in result.tasks_output)
        self.state.planning_artifacts.update(
            wbs=wbs_and_schedule.wbs,
            backlog=wbs_and_schedule.backlog,
            schedule_model=json.dumps(
                wbs_and_schedule.schedule_model.model_dump(), indent=2
            ),
            **requirements_and_dod.model_dump(),
        )

    @listen(run_planning_and_scope)
    def save_planning_artifacts(self):
        PLANNING_DIR.mkdir(parents=True, exist_ok=True)
        for key, filename in PLANNING_ARTIFACTS.items():
            content = self.state.planning_artifacts[key]
            # The WBS or the backlog is empty when the approach does not need it
            if content.strip():
                (PLANNING_DIR / filename).write_text(content)
                print(f"Saved {PLANNING_DIR / filename}")

    @listen(save_planning_artifacts)
    def run_risk_and_change_management(self):
        print("Running Risk and Change Management Crew")
        if self.state.scope_change_request:
            trigger_reason = "Change request"
        elif self.state.emerging_conditions:
            trigger_reason = "Emerging issues or risks"
        else:
            trigger_reason = "Baseline risk assessment"
        inputs = {
            "project_name": self.state.project_name,
            "trigger_reason": trigger_reason,
            "change_request": self.state.scope_change_request,
            "emerging_conditions": self.state.emerging_conditions,
            "business_case": self.state.initiation_artifacts["business_case"],
            "project_charter": self.state.initiation_artifacts["project_charter"],
            "current_date": date.today().isoformat(),
        }
        for key in ("wbs", "backlog", "schedule_model"):
            inputs[key] = self._latest_artifact(key)
        for key in CONTROL_ARTIFACTS:
            inputs[f"existing_{key}"] = self.state.existing_artifacts.get(key, "")

        result = self._kickoff_crew(RiskAndChangeManagementCrew(), inputs)

        risk_register, change_evaluation = (t.pydantic for t in result.tasks_output)
        self.state.control_artifacts.update(
            risk_register=risk_register.risk_register,
            change_log=change_evaluation.change_log,
            change_request_rfc=change_evaluation.change_request_rfc,
        )
        self.state.change_decision = change_evaluation.decision
        print(
            f"Change decision: {change_evaluation.decision} "
            f"(critical path delay {change_evaluation.critical_path_delay_days} days, "
            f"cost delta {change_evaluation.cost_delta_percent}%)"
        )

    @listen(run_risk_and_change_management)
    def save_control_artifacts(self):
        CONTROL_DIR.mkdir(parents=True, exist_ok=True)
        for key, filename in CONTROL_ARTIFACTS.items():
            content = self.state.control_artifacts[key]
            # The RFC is only issued when a tolerance threshold is breached
            if content.strip():
                (CONTROL_DIR / filename).write_text(content)
                print(f"Saved {CONTROL_DIR / filename}")

    @listen(save_control_artifacts)
    def run_performance_and_control(self):
        print("Running Performance and Control Crew")
        trigger_reason = (
            "Periodic performance review"
            if self.state.progress_data
            else "Baseline performance measurement (no actuals reported)"
        )
        inputs = {
            "project_name": self.state.project_name,
            "trigger_reason": trigger_reason,
            "status_date": self.state.status_date,
            "progress_data": self.state.progress_data,
            "current_date": date.today().isoformat(),
        }
        for key in (
            "business_case",
            "stakeholder_register",
            "wbs",
            "backlog",
            "schedule_model",
            "risk_register",
            "change_log",
        ):
            inputs[key] = self._latest_artifact(key)
        for key in PERFORMANCE_ARTIFACTS:
            inputs[f"existing_{key}"] = self.state.existing_artifacts.get(key, "")

        result = self._kickoff_crew(PerformanceAndControlCrew(), inputs)

        evm_metrics, dashboard_and_report = (t.pydantic for t in result.tasks_output)
        self.state.performance_artifacts.update(
            evm_metrics=json.dumps(evm_metrics.model_dump(), indent=2),
            **dashboard_and_report.model_dump(),
        )
        self.state.s_curve = [point.model_dump() for point in evm_metrics.s_curve]
        print(f"EVM at {evm_metrics.status_date}: CPI={evm_metrics.cpi} SPI={evm_metrics.spi}")

    @listen(run_performance_and_control)
    def save_performance_artifacts(self):
        PERFORMANCE_DIR.mkdir(parents=True, exist_ok=True)
        for key, filename in PERFORMANCE_ARTIFACTS.items():
            (PERFORMANCE_DIR / filename).write_text(self.state.performance_artifacts[key])
            print(f"Saved {PERFORMANCE_DIR / filename}")

        with S_CURVE_PATH.open("w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["period", "date", "cumulative_pv", "cumulative_ev", "cumulative_ac"]
            )
            writer.writeheader()
            writer.writerows(self.state.s_curve)
        print(f"Saved {S_CURVE_PATH}")

    @listen(save_performance_artifacts)
    def log_run_metrics(self):
        flow_duration = time.time() - self.state.flow_started_at
        crews = self.state.run_metrics
        run_metrics = {
            "run_timestamp": datetime.now().isoformat(timespec="seconds"),
            "project_name": self.state.project_name,
            "trigger_reason": self.state.trigger_reason,
            "flow_duration_s": round(flow_duration, 2),
            "flow_duration": format_duration(flow_duration),
            "tasks_completed": sum(c["tasks_completed"] for c in crews.values()),
            "token_usage": sum_token_usage([c["token_usage"] for c in crews.values()]),
            "crews": crews,
        }

        print("=" * 60)
        print(f"Flow duration: {flow_duration:.2f}s ({run_metrics['flow_duration']})")
        for crew_name, c in crews.items():
            print(
                f"  {crew_name}: latency {c['latency_s']}s | run time {c['total_run_time']} | "
                f"tasks {c['tasks_completed']} | tokens {c['token_usage']['total_tokens']}"
            )
            for t in c["tasks"]:
                print(f"    - {t['task']}: {t['elapsed_s']}s | {t['word_count']} words")
        print(f"Tasks completed: {run_metrics['tasks_completed']}")
        print(f"Token usage: {run_metrics['token_usage']}")
        print("=" * 60)

        RUN_METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with RUN_METRICS_PATH.open("a") as f:
            f.write(json.dumps(run_metrics) + "\n")
        print(f"Appended run metrics to {RUN_METRICS_PATH}")


def kickoff():
    ProjectManagementFlow().kickoff()


def plot():
    ProjectManagementFlow().plot()


def run_with_trigger():
    """
    Run the flow with trigger payload.
    """
    import json
    import sys

    if len(sys.argv) < 2:
        raise Exception("No trigger payload provided. Please provide JSON payload as argument.")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("Invalid JSON payload provided as argument")

    flow = ProjectManagementFlow()

    try:
        result = flow.kickoff({"crewai_trigger_payload": trigger_payload})
        return result
    except Exception as e:
        raise Exception(f"An error occurred while running the flow with trigger: {e}")


if __name__ == "__main__":
    kickoff()

#!/usr/bin/env python
import csv
import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from crewai import CrewOutput
from crewai.flow import Flow, listen, or_, router, start

from project_management.metrics import format_duration, sum_token_usage
from project_management.project_setup import ProjectSetup, commit_changes, load_project_setup

from project_management.crews.initiation_and_governance_crew.initiation_and_governance_crew import (
    InitiationAndGovernanceCrew,
)
from project_management.crews.planning_and_scope_crew.planning_and_scope_crew import (
    PlanningAndScopeCrew,
    WbsAndSchedule,
)
from project_management.crews.risk_and_change_management_crew.risk_and_change_management_crew import (
    ChangeEvaluation,
    RiskAndChangeManagementCrew,
)
from project_management.crews.performance_and_control_crew.performance_and_control_crew import (
    PerformanceAndControlCrew,
)

# Output paths are relative to the output folder of the project given in the project setup
INITIATION_DIR = Path("initiation")
INITIATION_ARTIFACTS = {
    "business_case": "business_case.md",
    "project_charter": "project_charter.md",
    "stakeholder_register": "stakeholder_register.md",
    "team_charter": "team_charter.md",
}
PLANNING_DIR = Path("planning")
PLANNING_ARTIFACTS = {
    "wbs": "wbs.md",
    "backlog": "backlog.md",
    "schedule_model": "schedule_model.json",
    "requirements_specification": "requirements_specification.md",
    "definition_of_done": "definition_of_done.md",
}
CONTROL_DIR = Path("control")
CONTROL_ARTIFACTS = {
    "risk_register": "risk_register.md",
    "change_log": "change_log.md",
}
# Each RFC is saved as rfcs/<RFC ID>.md, and its status (pending, approved, rejected) is
# tracked in the register so several RFCs can be pending at the same time
RFC_DIR = CONTROL_DIR / "rfcs"
RFC_REGISTER_PATH = CONTROL_DIR / "rfc_register.json"
PERFORMANCE_DIR = Path("performance")
PERFORMANCE_ARTIFACTS = {
    "evm_metrics": "evm_metrics.json",
    "project_dashboard": "project_dashboard.md",
    "status_report": "status_report.md",
}
# Baseline documents the performance measurement depends on (cost and schedule baselines)
PERFORMANCE_BASELINES = {"business_case", "schedule_model"}
S_CURVE_PATH = PERFORMANCE_DIR / "s_curve.csv"
RUN_METRICS_PATH = Path("logs") / "run_metrics.jsonl"
# Input file names, in the input folder of the project
DEFAULT_BRIEF_NAME = "project_brief.md"
DEFAULT_PROGRESS_NAME = "progress_data.md"


def normalize_rfc_id(value: str | int) -> str:
    """Accept '7', '007', or 'RFC-007' and return 'RFC-007'."""
    number = str(value).strip().upper().removeprefix("RFC-")
    if not number.isdigit():
        raise ValueError(f"Invalid RFC identifier {value!r}: expected a number such as 7 or RFC-007.")
    return f"RFC-{int(number):03d}"


def load_rfc_register(output_dir: Path) -> dict[str, dict]:
    path = output_dir / RFC_REGISTER_PATH
    return json.loads(path.read_text()) if path.exists() else {}


def next_rfc_id(register: dict[str, dict], output_dir: Path) -> str:
    numbers = [int(rfc_id.removeprefix("RFC-")) for rfc_id in register]
    numbers += [int(path.stem.removeprefix("RFC-")) for path in (output_dir / RFC_DIR).glob("RFC-*.md")]
    return normalize_rfc_id(max(numbers, default=0) + 1)


class ProjectState(BaseModel):
    project_code: str = ""
    project_name: str = ""
    project_brief: str = ""
    trigger_reason: str = "Project inception"
    scope_change_request: str = ""
    # The RFC this run raises or decides on, and the decision given in the payload
    rfc_identifier: str = ""
    rfc_decision: Literal["", "approved", "rejected"] = ""
    emerging_conditions: str = ""
    progress_data: str = ""
    status_date: str = ""
    existing_artifacts: dict[str, str] = {}
    initiation_artifacts: dict[str, str] = {}
    planning_artifacts: dict[str, str] = {}
    control_artifacts: dict[str, str] = {}
    change_decision: str = ""
    affected_artifacts: list[str] = []
    performance_artifacts: dict[str, str] = {}
    s_curve: list[dict] = []
    saved_files: list[str] = []
    commit: str = ""
    flow_started_at: float = 0.0
    run_metrics: dict[str, dict] = {}


class ProjectManagementFlow(Flow[ProjectState]):
    project: ProjectSetup | None = None

    def _output_path(self, path: Path) -> Path:
        return self.project.output_dir / path

    def _record_saved(self, path: Path):
        """Record a written file, relative to the project folder, to log and commit it."""
        self.state.saved_files.append(str(path.relative_to(self.project.folder)))
        print(f"Saved {path}")

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

    def _existing_inputs(self, artifacts: dict[str, str]) -> dict[str, str]:
        return {f"existing_{key}": self.state.existing_artifacts.get(key, "") for key in artifacts}

    def _save_artifacts(self, directory: Path, filenames: dict[str, str], produced: dict[str, str]):
        """Write the artifacts produced in this run, skipping empty and unchanged ones."""
        directory = self._output_path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        for key, content in produced.items():
            path = directory / filenames[key]
            # The WBS, backlog, or RFC is empty when the approach or the decision does not need it
            if not content.strip():
                continue
            if content == self.state.existing_artifacts.get(key):
                print(f"Unchanged {path}")
                continue
            path.write_text(content)
            self._record_saved(path)

    def _run_initiation_crew(self, affected: set[str] | None = None) -> dict[str, str]:
        inputs = {
            "project_name": self.state.project_name,
            "project_brief": self.state.project_brief,
            "trigger_reason": self.state.trigger_reason,
            "change_request": self.state.scope_change_request if affected else "",
            "business_case": self._latest_artifact("business_case"),
            "project_charter": self._latest_artifact("project_charter"),
            "current_date": date.today().isoformat(),
            **self._existing_inputs(INITIATION_ARTIFACTS),
        }
        result = self._kickoff_crew(InitiationAndGovernanceCrew(affected), inputs)

        produced = {}
        for task_output in result.tasks_output:
            produced.update(task_output.pydantic.model_dump())
        return produced

    def _run_planning_crew(self, affected: set[str] | None = None) -> dict[str, str]:
        trigger_reason = (
            "Scope modification" if self.state.scope_change_request else "Baseline planning"
        )
        inputs = {
            "project_name": self.state.project_name,
            "trigger_reason": trigger_reason,
            "scope_change_request": self.state.scope_change_request,
            "business_case": self._latest_artifact("business_case"),
            "project_charter": self._latest_artifact("project_charter"),
            "team_charter": self._latest_artifact("team_charter"),
            "current_date": date.today().isoformat(),
            **self._existing_inputs(PLANNING_ARTIFACTS),
        }
        result = self._kickoff_crew(PlanningAndScopeCrew(affected), inputs)

        produced = {}
        for task_output in result.tasks_output:
            output = task_output.pydantic
            if isinstance(output, WbsAndSchedule):
                produced.update(
                    wbs=output.wbs,
                    backlog=output.backlog,
                    schedule_model=json.dumps(output.schedule_model.model_dump(), indent=2),
                )
            else:
                produced.update(output.model_dump())
        return produced

    def _run_risk_and_change_crew(self, affected: set[str] | None = None):
        rfc_id = self.state.rfc_identifier
        if self.state.rfc_decision == "approved":
            trigger_reason = f"Approved change request ({rfc_id})"
            change_approval = (
                f"The Change Control Board approved {rfc_id}. Record the approval in the RFC "
                f"decision section and set the status of {rfc_id} to approved in the Change "
                "Log; do not log it as a new change."
            )
        elif self.state.rfc_decision == "rejected":
            trigger_reason = f"Rejected change request ({rfc_id})"
            change_approval = (
                f"The Change Control Board rejected {rfc_id}. Record the rejection in the RFC "
                f"decision section and set the status of {rfc_id} to rejected in the Change "
                "Log; do not log it as a new change. The baselines stay unchanged, so leave "
                "the affected artifacts empty."
            )
        else:
            if self.state.scope_change_request:
                trigger_reason = "Change request"
            elif self.state.emerging_conditions:
                trigger_reason = "Emerging issues or risks"
            else:
                trigger_reason = "Baseline risk assessment"
            change_approval = (
                "Not decided yet: a change that breaches a tolerance threshold stays "
                "pending until the Change Control Board approves its RFC."
            )
        inputs = {
            "project_name": self.state.project_name,
            "trigger_reason": trigger_reason,
            "change_request": self.state.scope_change_request,
            "change_approval": change_approval,
            "rfc_identifier": rfc_id,
            "existing_change_request_rfc": self.state.existing_artifacts.get("change_request_rfc", ""),
            "emerging_conditions": self.state.emerging_conditions,
            "business_case": self._latest_artifact("business_case"),
            "project_charter": self._latest_artifact("project_charter"),
            "current_date": date.today().isoformat(),
            **{key: self._latest_artifact(key) for key in ("wbs", "backlog", "schedule_model")},
            **self._existing_inputs(CONTROL_ARTIFACTS),
        }
        result = self._kickoff_crew(RiskAndChangeManagementCrew(affected), inputs)

        for task_output in result.tasks_output:
            output = task_output.pydantic
            if isinstance(output, ChangeEvaluation):
                self.state.control_artifacts.update(
                    change_log=output.change_log,
                    change_request_rfc=output.change_request_rfc,
                )
                self.state.change_decision = output.decision
                affected_artifacts = set(output.affected_artifacts)
                # The schedule model is derived from the WBS and backlog, so it changes with them
                if affected_artifacts & {"wbs", "backlog"}:
                    affected_artifacts.add("schedule_model")
                self.state.affected_artifacts = sorted(affected_artifacts)
                print(
                    f"Change decision: {output.decision} "
                    f"(critical path delay {output.critical_path_delay_days} days, "
                    f"cost delta {output.cost_delta_percent}%) | "
                    f"affected artifacts: {', '.join(self.state.affected_artifacts) or 'none'}"
                )
            else:
                self.state.control_artifacts.update(output.model_dump())

    def _save_control(self):
        """Save the risk register, change log, and RFC, and record the RFC status in the register."""
        self._save_artifacts(CONTROL_DIR, CONTROL_ARTIFACTS, {
            key: content for key, content in self.state.control_artifacts.items() if key in CONTROL_ARTIFACTS
        })

        rfc = self.state.control_artifacts.get("change_request_rfc", "")
        rfc_id = self.state.rfc_identifier
        register = load_rfc_register(self.project.output_dir)
        if self.state.rfc_decision:
            register[rfc_id].update(status=self.state.rfc_decision, decided_on=date.today().isoformat())
        elif rfc.strip():
            register[rfc_id] = {
                "status": "pending",
                "raised_on": date.today().isoformat(),
                "change_request": self.state.scope_change_request,
            }
        else:
            return  # No RFC raised or decided in this run
        self._save_artifacts(RFC_DIR, {"change_request_rfc": f"{rfc_id}.md"}, {"change_request_rfc": rfc})
        register_path = self._output_path(RFC_REGISTER_PATH)
        register_path.write_text(json.dumps(register, indent=2) + "\n")
        self._record_saved(register_path)
        print(f"{rfc_id} is {register[rfc_id]['status']} ({register_path})")

    def _load_rfc_decision(self, payload: dict):
        """Set the RFC this run decides on, or allocate the ID for an RFC this run may raise."""
        register = load_rfc_register(self.project.output_dir)
        if "rfc_identifier" not in payload:
            if "rfc_approved" in payload:
                pending = [rfc_id for rfc_id, rfc in register.items() if rfc["status"] == "pending"]
                raise ValueError(
                    f"'rfc_approved' needs the 'rfc_identifier' of the RFC to decide on. "
                    f"Pending RFCs: {', '.join(pending) or 'none'}."
                )
            self.state.rfc_identifier = next_rfc_id(register, self.project.output_dir)
            return

        rfc_id = normalize_rfc_id(payload["rfc_identifier"])
        if not isinstance(payload.get("rfc_approved"), bool):
            raise ValueError(f"Deciding on {rfc_id} needs 'rfc_approved': true or false.")
        if self.state.scope_change_request:
            raise ValueError(f"Deciding on {rfc_id} takes the change from the RFC; drop 'scope_change_request'.")
        if rfc_id not in register:
            raise ValueError(f"Unknown RFC {rfc_id}. Known RFCs: {', '.join(register) or 'none'}.")
        if register[rfc_id]["status"] != "pending":
            raise ValueError(f"{rfc_id} was already {register[rfc_id]['status']}.")

        self.state.rfc_identifier = rfc_id
        self.state.rfc_decision = "approved" if payload["rfc_approved"] else "rejected"
        rfc = self._output_path(RFC_DIR / f"{rfc_id}.md").read_text()
        self.state.existing_artifacts["change_request_rfc"] = rfc
        self.state.scope_change_request = register[rfc_id].get("change_request") or rfc

    def _load_change_request(self, payload: dict) -> str:
        """Return the change request given inline or as a file name in the project's input folder."""
        filename = payload.get("scope_change_request_file")
        if not filename:
            return payload.get("scope_change_request", "")
        if payload.get("scope_change_request"):
            raise ValueError("Pass either 'scope_change_request' or 'scope_change_request_file', not both.")
        input_dir = self.project.input_dir
        path = input_dir / filename
        if path.resolve().parent != input_dir.resolve():
            raise ValueError(f"'scope_change_request_file' must be a file name in {input_dir}/, got {filename!r}.")
        if not path.is_file():
            raise ValueError(f"Change request file not found: {path}")
        print(f"Using change request from {path}")
        return path.read_text()

    @start()
    def load_project_context(self, crewai_trigger_payload: dict = None):
        self.state.flow_started_at = time.time()
        payload = crewai_trigger_payload or {}
        if payload:
            print(f"Using trigger payload: {payload}")

        if not payload.get("project_code"):
            raise ValueError("No project code provided: run 'uv run run_with_trigger <PROJECT_CODE> [<json payload>]'.")
        self.project = load_project_setup(payload["project_code"])
        self.state.project_code = self.project.code
        self.state.project_name = self.project.name
        print(f"Project folder: {self.project.folder}")
        brief_path = self.project.input_dir / DEFAULT_BRIEF_NAME
        progress_path = self.project.input_dir / DEFAULT_PROGRESS_NAME

        self.state.scope_change_request = self._load_change_request(payload)
        self.state.emerging_conditions = payload.get("emerging_conditions", "")
        self.state.status_date = payload.get("status_date", date.today().isoformat())
        if "progress_data" in payload:
            progress_data = payload["progress_data"]
            self.state.progress_data = (
                progress_data if isinstance(progress_data, str) else json.dumps(progress_data, indent=2)
            )
        elif progress_path.exists():
            self.state.progress_data = progress_path.read_text()
        if "project_brief" in payload:
            self.state.project_brief = payload["project_brief"]
        elif brief_path.exists():
            self.state.project_brief = brief_path.read_text()
        else:
            raise ValueError(
                f"No project brief provided. Pass 'project_brief' in the trigger "
                f"payload or create {brief_path}."
            )

        for directory, artifacts in (
            (INITIATION_DIR, INITIATION_ARTIFACTS),
            (PLANNING_DIR, PLANNING_ARTIFACTS),
            (CONTROL_DIR, CONTROL_ARTIFACTS),
            (PERFORMANCE_DIR, PERFORMANCE_ARTIFACTS),
        ):
            for key, filename in artifacts.items():
                path = self._output_path(directory / filename)
                if path.exists():
                    self.state.existing_artifacts[key] = path.read_text()

        self._load_rfc_decision(payload)

        if "trigger_reason" in payload:
            self.state.trigger_reason = payload["trigger_reason"]
        elif self.state.rfc_decision:
            self.state.trigger_reason = (
                f"{self.state.rfc_decision.capitalize()} change request ({self.state.rfc_identifier})"
            )
        elif self.state.scope_change_request:
            self.state.trigger_reason = "Change request"

        print(f"Project: {self.state.project_code} {self.state.project_name} ({self.state.trigger_reason})")

    @router(load_project_context)
    def route_trigger(self):
        has_baseline = "schedule_model" in self.state.existing_artifacts
        if self.state.scope_change_request and has_baseline:
            return "change_request"
        return "full_cycle"

    # Full cycle: inception, or any run without a change request against a saved baseline

    @listen("full_cycle")
    def run_initiation_and_governance(self):
        print("Running Initiation and Governance Crew")
        self.state.initiation_artifacts.update(self._run_initiation_crew())

    @listen(run_initiation_and_governance)
    def save_initiation_artifacts(self):
        self._save_artifacts(INITIATION_DIR, INITIATION_ARTIFACTS, self.state.initiation_artifacts)

    @listen(save_initiation_artifacts)
    def run_planning_and_scope(self):
        print("Running Planning and Scope Crew")
        self.state.planning_artifacts.update(self._run_planning_crew())

    @listen(run_planning_and_scope)
    def save_planning_artifacts(self):
        self._save_artifacts(PLANNING_DIR, PLANNING_ARTIFACTS, self.state.planning_artifacts)

    @listen(save_planning_artifacts)
    def run_risk_and_change_management(self):
        print("Running Risk and Change Management Crew")
        self._run_risk_and_change_crew()

    @listen(run_risk_and_change_management)
    def save_control_artifacts(self):
        self._save_control()

    # Change request: evaluate the change against the saved baseline, then update only what it affects

    @listen("change_request")
    def evaluate_change(self):
        if self.state.rfc_decision:
            # The risk register was already reassessed when the RFC was raised
            print(f"Recording the {self.state.rfc_decision} {self.state.rfc_identifier} (Risk and Change Management Crew)")
            self._run_risk_and_change_crew(affected={"change_log", "change_request_rfc"})
        else:
            print("Evaluating the change request (Risk and Change Management Crew)")
            self._run_risk_and_change_crew()

    @listen(evaluate_change)
    def save_change_control_artifacts(self):
        self._save_control()

    @router(save_change_control_artifacts)
    def route_change_decision(self):
        if self.state.rfc_decision:
            approved = self.state.rfc_decision == "approved"
        else:
            approved = self.state.change_decision == "fast_track_replan"
            if self.state.change_decision == "formal_rfc":
                rfc_id = self.state.rfc_identifier
                print(
                    f"Formal RFC {rfc_id} raised: the baselines stay unchanged until the Change "
                    f"Control Board decides. Re-run with the trigger payload "
                    f"{{\"rfc_identifier\": \"{rfc_id}\", \"rfc_approved\": true}} to apply it, "
                    f"or \"rfc_approved\": false to reject it."
                )
        if approved and self.state.affected_artifacts:
            return "change_approved"
        return "change_closed"

    @listen("change_approved")
    def update_affected_baselines(self):
        affected = set(self.state.affected_artifacts)
        if affected & INITIATION_ARTIFACTS.keys():
            print(f"Updating initiation artifacts: {', '.join(sorted(affected & INITIATION_ARTIFACTS.keys()))}")
            produced = self._run_initiation_crew(affected)
            # A task produces two documents; keep only the affected one(s)
            self.state.initiation_artifacts.update(
                {key: content for key, content in produced.items() if key in affected}
            )
        if affected & PLANNING_ARTIFACTS.keys():
            print(f"Updating planning artifacts: {', '.join(sorted(affected & PLANNING_ARTIFACTS.keys()))}")
            produced = self._run_planning_crew(affected)
            self.state.planning_artifacts.update(
                {key: content for key, content in produced.items() if key in affected}
            )

    @listen(update_affected_baselines)
    def save_updated_baselines(self):
        self._save_artifacts(INITIATION_DIR, INITIATION_ARTIFACTS, self.state.initiation_artifacts)
        self._save_artifacts(PLANNING_DIR, PLANNING_ARTIFACTS, self.state.planning_artifacts)

    @router(save_updated_baselines)
    def route_performance_update(self):
        if set(self.state.affected_artifacts) & PERFORMANCE_BASELINES:
            return "baseline_changed"
        return "baseline_unchanged"

    # Performance measurement, after a full cycle or a change that moved the cost or schedule baseline

    @listen(or_(save_control_artifacts, "baseline_changed"))
    def run_performance_and_control(self):
        print("Running Performance and Control Crew")
        if self.state.affected_artifacts:
            trigger_reason = "Re-baseline after an approved change"
        elif self.state.progress_data:
            trigger_reason = "Periodic performance review"
        else:
            trigger_reason = "Baseline performance measurement (no actuals reported)"
        inputs = {
            "project_name": self.state.project_name,
            "trigger_reason": trigger_reason,
            "status_date": self.state.status_date,
            "progress_data": self.state.progress_data,
            "current_date": date.today().isoformat(),
            **self._existing_inputs(PERFORMANCE_ARTIFACTS),
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
        self._save_artifacts(PERFORMANCE_DIR, PERFORMANCE_ARTIFACTS, self.state.performance_artifacts)

        s_curve_path = self._output_path(S_CURVE_PATH)
        with s_curve_path.open("w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["period", "date", "cumulative_pv", "cumulative_ev", "cumulative_ac"]
            )
            writer.writeheader()
            writer.writerows(self.state.s_curve)
        self._record_saved(s_curve_path)

    @listen(or_(save_performance_artifacts, "change_closed", "baseline_unchanged"))
    def log_run_metrics(self):
        flow_duration = time.time() - self.state.flow_started_at
        crews = self.state.run_metrics
        run_metrics = {
            "run_timestamp": datetime.now().isoformat(timespec="seconds"),
            "project_code": self.state.project_code,
            "project_name": self.state.project_name,
            "trigger_reason": self.state.trigger_reason,
            "change_decision": self.state.change_decision,
            # The allocated ID is only meaningful when this run raised or decided on an RFC
            "rfc_identifier": self.state.rfc_identifier
            if self.state.rfc_decision or self.state.control_artifacts.get("change_request_rfc", "").strip()
            else "",
            "rfc_decision": self.state.rfc_decision,
            "affected_artifacts": self.state.affected_artifacts,
            "saved_files": self.state.saved_files,
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
        print(f"Files saved: {len(self.state.saved_files)}")
        print("=" * 60)

        run_metrics_path = self._output_path(RUN_METRICS_PATH)
        run_metrics_path.parent.mkdir(parents=True, exist_ok=True)
        with run_metrics_path.open("a") as f:
            f.write(json.dumps(run_metrics) + "\n")
        print(f"Appended run metrics to {run_metrics_path}")

    @listen(log_run_metrics)
    def commit_project_changes(self):
        """Commit the documents this run changed, and its run metrics, in the project's repository."""
        summary = [f"Trigger: {self.state.trigger_reason}"]
        if self.state.change_decision:
            summary.append(f"Change decision: {self.state.change_decision}")
        if self.state.rfc_decision:
            summary.append(f"{self.state.rfc_identifier}: {self.state.rfc_decision}")
        summary.append("Changed documents:")
        summary += [f"- {path}" for path in self.state.saved_files]
        if not self.state.saved_files:
            summary.append("- none")
        message = f"{self.state.project_code}: {self.state.trigger_reason}\n\n" + "\n".join(summary)

        run_metrics_path = self._output_path(RUN_METRICS_PATH).relative_to(self.project.folder)
        paths = [*self.state.saved_files, str(run_metrics_path)]
        self.state.commit = commit_changes(self.project, paths, message)
        if self.state.commit:
            print(f"Committed {len(paths)} files to {self.project.folder} ({self.state.commit})")
        else:
            print(f"Nothing to commit in {self.project.folder}")


def kickoff():
    """Disabled: 'crewai run' calls this, but every run must name the project it works on."""
    raise SystemExit(
        "'crewai run' is disabled: each run works on one project of the project setup document. "
        "Run 'uv run run_with_trigger <PROJECT_CODE> [<json payload>]' instead."
    )


def plot():
    ProjectManagementFlow().plot()


def run_with_trigger():
    """
    Run the flow on a project of the project setup document:
    uv run run_with_trigger <PROJECT_CODE> [<json payload>]
    """
    import json
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("Usage: uv run run_with_trigger <PROJECT_CODE> [<json payload>]")

    try:
        trigger_payload = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    except json.JSONDecodeError:
        raise Exception("Invalid JSON payload provided as argument")
    trigger_payload["project_code"] = sys.argv[1]

    flow = ProjectManagementFlow()

    try:
        result = flow.kickoff({"crewai_trigger_payload": trigger_payload})
        return result
    except Exception as e:
        raise Exception(f"An error occurred while running the flow with trigger: {e}")


if __name__ == "__main__":
    kickoff()

from math import isclose
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, after_kickoff, agent, before_kickoff, crew, task
from crewai.tasks.task_output import TaskOutput
from pydantic import BaseModel, Field

from project_management.metrics import CrewRunMetrics, record_task_completed


class ChangelogEntry(BaseModel):
    version: str
    date: str
    change_description: str


class WorkPackageEvm(BaseModel):
    id: str = Field(..., description="WBS code or backlog item ID")
    name: str
    bac: float
    percent_complete: float = Field(..., description="Physical percent complete (0-100)")
    pv: float
    ev: float
    ac: float


class SCurvePoint(BaseModel):
    period: str = Field(..., description="Reporting period label, e.g. week or sprint")
    date: str = Field(..., description="Period end date (YYYY-MM-DD)")
    cumulative_pv: float
    cumulative_ev: float | None = Field(..., description="Null for periods after the status date")
    cumulative_ac: float | None = Field(..., description="Null for periods after the status date")


class EvmMetrics(BaseModel):
    title: str
    project_name: str
    version: str
    date: str
    changelog: list[ChangelogEntry]
    status_date: str
    currency: str
    bac: float
    pv: float
    ev: float
    ac: float
    cv: float
    sv: float
    cpi: float | None = Field(..., description="Null when AC is zero")
    spi: float | None = Field(..., description="Null when PV is zero")
    eac: float
    eac_method: str = Field(..., description="Formula used for EAC, e.g. BAC / CPI")
    etc: float
    vac: float
    tcpi: float | None = Field(..., description="Null when BAC equals AC")
    work_packages: list[WorkPackageEvm]
    s_curve: list[SCurvePoint]
    assumptions: list[str]


class DashboardAndReport(BaseModel):
    project_dashboard: str = Field(..., description="Project Dashboard markdown document")
    status_report: str = Field(..., description="Status Report markdown document")


def _close(actual: float | None, expected: float) -> bool:
    return actual is not None and isclose(actual, expected, rel_tol=0.01, abs_tol=0.01)


def validate_evm_formulas(result: TaskOutput) -> tuple[bool, Any]:
    """Reject EVM metrics whose derived values don't follow from PV, EV, AC, BAC, and EAC."""
    m: EvmMetrics | None = result.pydantic
    if m is None:
        return (False, "Return the EVM metrics in the requested structured format")
    errors = []
    if not _close(m.cv, m.ev - m.ac):
        errors.append("CV must equal EV - AC")
    if not _close(m.sv, m.ev - m.pv):
        errors.append("SV must equal EV - PV")
    if m.ac and not _close(m.cpi, m.ev / m.ac):
        errors.append("CPI must equal EV / AC")
    if m.pv and not _close(m.spi, m.ev / m.pv):
        errors.append("SPI must equal EV / PV")
    if not _close(m.etc, m.eac - m.ac):
        errors.append("ETC must equal EAC - AC")
    if not _close(m.vac, m.bac - m.eac):
        errors.append("VAC must equal BAC - EAC")
    if m.bac != m.ac and not _close(m.tcpi, (m.bac - m.ev) / (m.bac - m.ac)):
        errors.append("TCPI must equal (BAC - EV) / (BAC - AC)")
    if errors:
        return (False, "Recalculate the EVM metrics: " + "; ".join(errors))
    return (True, result)


@CrewBase
class PerformanceAndControlCrew:
    """Performance and Control Crew

    Triggered on periodic cadences or following adjustments to tasks, effort, and actual expenses.
    """

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self) -> None:
        self.run_metrics = CrewRunMetrics(type(self).__name__)

    @before_kickoff
    def start_run_metrics(self, inputs):
        return self.run_metrics.start(inputs)

    @after_kickoff
    def finish_run_metrics(self, output):
        return self.run_metrics.finish(output)

    @agent
    def evm_kpi_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["evm_kpi_analyst"],  # type: ignore[index]
        )

    @agent
    def reporting_dashboard_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["reporting_dashboard_agent"],  # type: ignore[index]
        )

    @task
    def task_calculate_evm_metrics(self) -> Task:
        return Task(
            config=self.tasks_config["task_calculate_evm_metrics"],  # type: ignore[index]
            output_pydantic=EvmMetrics,
            guardrail=validate_evm_formulas,
        )

    @task
    def task_generate_dashboard_and_reports(self) -> Task:
        return Task(
            config=self.tasks_config["task_generate_dashboard_and_reports"],  # type: ignore[index]
            context=[self.task_calculate_evm_metrics()],
            output_pydantic=DashboardAndReport,
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Performance and Control Crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            task_callback=record_task_completed,
            verbose=True,
        )

from typing import Literal

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, after_kickoff, agent, before_kickoff, crew, task
from pydantic import BaseModel, Field

from project_management.metrics import CrewRunMetrics, record_task_completed


class ChangelogEntry(BaseModel):
    version: str
    date: str
    change_description: str


class Dependency(BaseModel):
    predecessor_id: str = Field(..., description="ID of the predecessor activity")
    type: Literal["FS", "SS", "FF", "SF"] = Field(..., description="Dependency type")
    lag_days: float = Field(0, description="Lag (positive) or lead (negative) in days")


class ScheduleActivity(BaseModel):
    id: str = Field(..., description="WBS code or backlog item ID")
    name: str
    duration_days: float
    effort_hours: float
    predecessors: list[Dependency] = []
    early_start: float
    early_finish: float
    late_start: float
    late_finish: float
    total_float: float
    on_critical_path: bool


class ScheduleModel(BaseModel):
    title: str
    project_name: str
    version: str
    date: str
    changelog: list[ChangelogEntry]
    time_unit: str = Field("days", description="Unit for durations, starts, finishes, and float")
    activities: list[ScheduleActivity]
    critical_path: list[str] = Field(..., description="Ordered activity IDs on the critical path")
    project_duration_days: float


class WbsAndSchedule(BaseModel):
    wbs: str = Field(
        ..., description="WBS markdown document; empty for a purely adaptive approach"
    )
    backlog: str = Field(
        ..., description="Backlog markdown document; empty for a purely predictive approach"
    )
    schedule_model: ScheduleModel


class RequirementsAndDoD(BaseModel):
    requirements_specification: str = Field(
        ..., description="Requirements Specification markdown document, including traceability matrix"
    )
    definition_of_done: str = Field(..., description="Definition of Done markdown document")


@CrewBase
class PlanningAndScopeCrew:
    """Planning and Scope Crew

    Triggered during baseline planning or whenever scope modifications are introduced.
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
    def scope_decomposition_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["scope_decomposition_agent"],  # type: ignore[index]
        )

    @agent
    def quality_engineering_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["quality_engineering_agent"],  # type: ignore[index]
        )

    @task
    def task_build_wbs_and_backlog(self) -> Task:
        return Task(
            config=self.tasks_config["task_build_wbs_and_backlog"],  # type: ignore[index]
            output_pydantic=WbsAndSchedule,
        )

    @task
    def task_define_requirements_and_dod(self) -> Task:
        return Task(
            config=self.tasks_config["task_define_requirements_and_dod"],  # type: ignore[index]
            context=[self.task_build_wbs_and_backlog()],
            output_pydantic=RequirementsAndDoD,
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Planning and Scope Crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            task_callback=record_task_completed,
            verbose=True,
        )

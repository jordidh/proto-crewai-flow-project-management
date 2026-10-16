from typing import Literal

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, after_kickoff, agent, before_kickoff, crew, task
from pydantic import BaseModel, Field

from project_management.metrics import CrewRunMetrics, record_task_completed


class RiskRegister(BaseModel):
    risk_register: str = Field(..., description="Risk Register markdown document")


class ChangeEvaluation(BaseModel):
    change_log: str = Field(..., description="Change Log markdown document")
    change_request_rfc: str = Field(
        ..., description="Change Request (RFC) markdown document; empty if no threshold is breached"
    )
    critical_path_delay_days: float = Field(
        ..., description="Largest critical path delay of the proposed changes, in days"
    )
    cost_delta_percent: float = Field(
        ..., description="Largest cost delta of the proposed changes, as % of work package budget or BAC"
    )
    decision: Literal["no_change", "fast_track_replan", "formal_rfc"]


@CrewBase
class RiskAndChangeManagementCrew:
    """Risk and Change Management Crew

    Triggered when issues arise, new risks emerge, or change requests enter the system.
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
    def risk_assessor_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["risk_assessor_agent"],  # type: ignore[index]
        )

    @agent
    def change_control_arbiter(self) -> Agent:
        return Agent(
            config=self.agents_config["change_control_arbiter"],  # type: ignore[index]
        )

    @task
    def task_update_risk_register(self) -> Task:
        return Task(
            config=self.tasks_config["task_update_risk_register"],  # type: ignore[index]
            output_pydantic=RiskRegister,
        )

    @task
    def task_evaluate_and_log_changes(self) -> Task:
        return Task(
            config=self.tasks_config["task_evaluate_and_log_changes"],  # type: ignore[index]
            context=[self.task_update_risk_register()],
            output_pydantic=ChangeEvaluation,
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Risk and Change Management Crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            task_callback=record_task_completed,
            verbose=True,
        )

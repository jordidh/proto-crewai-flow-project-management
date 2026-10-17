from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, after_kickoff, agent, before_kickoff, crew, task
from pydantic import BaseModel, Field

from project_management.metrics import CrewRunMetrics, record_task_completed
from project_management.task_selection import select_tasks

# Artifacts produced by each task, used to run only the tasks a change affects
TASK_ARTIFACTS = {
    "task_create_business_case_and_charter": {"business_case", "project_charter"},
    "task_map_stakeholders_and_team_charter": {"stakeholder_register", "team_charter"},
}


class BusinessCaseAndCharter(BaseModel):
    business_case: str = Field(..., description="Business Case markdown document")
    project_charter: str = Field(..., description="Project Charter markdown document")


class StakeholdersAndTeamCharter(BaseModel):
    stakeholder_register: str = Field(
        ..., description="Stakeholder Register markdown document, including RACI matrix"
    )
    team_charter: str = Field(..., description="Team Charter markdown document")


@CrewBase
class InitiationAndGovernanceCrew:
    """Initiation and Governance Crew

    Triggered at project inception or when strategic objectives are renegotiated.
    """

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, affected_artifacts: set[str] | None = None) -> None:
        self.run_metrics = CrewRunMetrics(type(self).__name__)
        self.affected_artifacts = affected_artifacts

    @before_kickoff
    def start_run_metrics(self, inputs):
        return self.run_metrics.start(inputs)

    @after_kickoff
    def finish_run_metrics(self, output):
        return self.run_metrics.finish(output)

    @agent
    def strategic_value_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["strategic_value_agent"],  # type: ignore[index]
        )

    @agent
    def stakeholder_alignment_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["stakeholder_alignment_agent"],  # type: ignore[index]
        )

    @task
    def task_create_business_case_and_charter(self) -> Task:
        return Task(
            config=self.tasks_config["task_create_business_case_and_charter"],  # type: ignore[index]
            output_pydantic=BusinessCaseAndCharter,
        )

    @task
    def task_map_stakeholders_and_team_charter(self) -> Task:
        return Task(
            config=self.tasks_config["task_map_stakeholders_and_team_charter"],  # type: ignore[index]
            context=[self.task_create_business_case_and_charter()],
            output_pydantic=StakeholdersAndTeamCharter,
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Initiation and Governance Crew"""
        return Crew(
            agents=self.agents,
            tasks=select_tasks(self.tasks, TASK_ARTIFACTS, self.affected_artifacts),
            process=Process.sequential,
            task_callback=record_task_completed,
            verbose=True,
        )

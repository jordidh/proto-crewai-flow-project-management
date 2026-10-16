# proto-crewai-flow-project-management

Welcome to the proto-crewai-flow-project-management project, powered by [crewAI](https://crewai.com). This template is designed to help you set up a multi-agent AI system with ease, leveraging the powerful and flexible framework provided by crewAI. Our goal is to enable your agents to collaborate effectively on complex tasks, maximizing their collective intelligence and capabilities.

## Setup the project

Requeriments:
- Python 3.10+
- Virtual Environments (https://www.w3schools.com/PYTHON/python_virtualenv.asp)
- VS Code
- CrewAI (https://crewai.com/, https://docs.crewai.com/v1.15.2/en/installation)
- LLM SDKs
- Dotenv

```bash
python3 --version
# Python 3.12.3

# Go to the project folder
# Create a virtual environment in a hidden folder .venv to isolate dependencies
python3 -m venv .venv
# This will set up a virtual environment, and create a folder named ".venv" with subfolders and files, like this:
#.venv
# Include  
# Lib  
# Scripts  
# .gitignore  
# pyvenv.cfg

# Activate the virtual environment
source .venv/bin/activate
# The command line will look like this when the virtual environment is active:
(.venv) ... $
```

Install uv python package manager <https://docs.astral.sh/uv/getting-started/installation/#installation-methods>:

```bash
# Install astral
curl -LsSf https://astral.sh/uv/install.sh | sh
uv --version

# To add $HOME/snap/code/248/.local/share/../bin to your PATH
#    gedit ~/.profile
# Either restart your shell or run:
#
#    source $HOME/snap/code/248/.local/share/../bin/env (sh, bash, zsh)
#    source $HOME/snap/code/248/.local/share/../bin/env.fish (fish)
```

Install CrewAI CLI:

```bash
uv tool install crewai

# Check crewai is installed successfully
uv tool list

# Update the shell path
uv tool update-shell

# Upgrade crewai
uv tool install crewai --upgrade
```

## Create the project

```bash
crewai create flow proto-crewai-flow-organization-analysis
```

## Install dependencies

```bash
crewai install
uv add "crewai[google-genai]"
uv add "crewai[litellm]"

uv add crewai-tools
```

## Running

To kickstart your flow and begin execution, run this from the root folder of your project:

```bash
crewai run
```

This command initializes the project-management Flow as defined in your configuration.

The flow reads the brief from `input/project_brief.md` (and optional actuals from `input/progress_data.md`), runs four crews in sequence and writes their artifacts under `output/`:

| Crew | Artifacts |
|------|-----------|
| Initiation and Governance | `output/initiation/` — business case, project charter, stakeholder register, team charter |
| Planning and Scope | `output/planning/` — WBS, backlog, schedule model, requirements specification, definition of done |
| Risk and Change Management | `output/control/` — risk register, change log, change request (RFC) when a tolerance is breached |
| Performance and Control | `output/performance/` — EVM metrics, S-curve CSV, project dashboard, status report |

Each run appends its KPIs (flow duration, per-crew latency, per-task time and output size, tasks completed, token usage) to `output/logs/run_metrics.jsonl`. Existing artifacts in `output/` are fed back to the crews on the next run so they update rather than start over.

### First run

To try it, write a brief into `input/project_brief.md` and run `crewai run`, or use the trigger:
uv run run_with_trigger `'{"project_name": "X", "project_brief": "...", "trigger_reason": "Project inception"}'`

After the first full run, crewai traces enable will record each step of the run if you want to see how the agents reached their output.

## Project Structure

**Add your `OPENAI_API_KEY` into the `.env` file**

- Each crew lives in `src/project_management/crews/<crew_name>/`, with its agents and tasks in `config/agents.yaml` and `config/tasks.yaml` and its logic in `<crew_name>.py`
- `src/project_management/main.py` orchestrates the flow and saves the artifacts
- `src/project_management/metrics.py` times crews and tasks and collects the run KPIs

## How to create a CrewAI project

Steps done to create this project.

Iteration 1 - Crew creation. Steps:
1. Identify the general architecture: how may crews it will be needed, what will do each crew and a name
2. Specify each crew:
    2.1. Specify the agents: name, role and a description
    2.2. Specify the tasks: name, description, generated artifacts and agent that will execute the task
3. Specify the flow orchestration patter to be used
4. Test running `crewai run` and inspect and analyze the logs and the artifacts generated

Iteration 2 - KPI and logs to measure performance and reliability. Steps:
1. Identify the KPI and values to measure
2. Add the KPIs and log the results


## Changelog

### v0.1.0 — 2026-10-16

**Added**
- Project-management flow that turns a project brief into a full set of PM artifacts using four crews: Initiation and Governance, Planning and Scope, Risk and Change Management, and Performance and Control.
- Input from `input/project_brief.md` or a trigger payload (`uv run run_with_trigger '<json>'`), with optional scope change requests, emerging conditions and progress data.
- Incremental runs: artifacts already in `output/` are passed back to the crews so they are updated instead of regenerated.
- Run KPIs (flow duration, crew latency, per-task time and word count, tasks completed, token usage) printed at the end of each run and appended to `output/logs/run_metrics.jsonl`.

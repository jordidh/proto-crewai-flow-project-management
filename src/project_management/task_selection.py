from crewai import Task


def select_tasks(
    tasks: list[Task], task_artifacts: dict[str, set[str]], affected: set[str] | None
) -> list[Task]:
    """Keep the tasks that produce at least one affected artifact, or all tasks when affected is None.

    A kept task whose context task was dropped gets an empty context, so its YAML must also
    receive the dropped task's artifacts as inputs.
    """
    if affected is None:
        return tasks
    return [task for task in tasks if task_artifacts[task.name] & affected]

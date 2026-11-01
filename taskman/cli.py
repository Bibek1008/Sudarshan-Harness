import argparse
import sys
from taskman.models import Task
from taskman.storage import Storage, StorageError


class CLI:
    def __init__(self, storage_path: str = "tasks.json"):
        self.storage = Storage(storage_path)

    def run(self, args: list[str]):
        parser = argparse.ArgumentParser(prog="taskman", description="Manage tasks stored in tasks.json.")
        commands = parser.add_subparsers(dest="command", required=True)
        add = commands.add_parser("add", help="Add a task")
        add.add_argument("title")
        add.add_argument("description", nargs="*", help="Optional description; quote text containing spaces")
        commands.add_parser("list", help="List tasks")
        for command in ("show", "complete", "delete"):
            subparser = commands.add_parser(command, help=f"{command.capitalize()} a task")
            subparser.add_argument("id", help="Exact task ID")
        try:
            options = parser.parse_args(args)
        except SystemExit as exc:
            return int(exc.code)
        try:
            if options.command == "add":
                self.add_task(options.title, " ".join(options.description))
            elif options.command == "list":
                self.list_tasks()
            else:
                getattr(self, options.command + "_task")(options.id)
            return 0
        except (ValueError, StorageError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    def add_task(self, title, desc):
        task = Task.create(title, desc)
        tasks = self.storage.load()
        tasks.append(task)
        self.storage.save(tasks)
        print(f"Task added: {task.id}")

    def list_tasks(self):
        tasks = self.storage.load()
        if not tasks:
            print("No tasks found.")
        for task in tasks:
            status = "[x]" if task.completed else "[ ]"
            print(f"{task.id} {status} {task.title}")

    def complete_task(self, task_id):
        tasks = self.storage.load()
        task = self._find(tasks, task_id)
        task.completed = True
        self.storage.save(tasks)
        print(f"Task {task_id} completed.")

    def delete_task(self, task_id):
        tasks = self.storage.load()
        task = self._find(tasks, task_id)
        tasks.remove(task)
        self.storage.save(tasks)
        print(f"Task {task_id} deleted.")

    def show_task(self, task_id):
        task = self._find(self.storage.load(), task_id)
        print(f"ID: {task.id}")
        print(f"Title: {task.title}")
        print(f"Description: {task.description}")
        print(f"Created: {task.created_at}")
        print(f"Status: {'Completed' if task.completed else 'Pending'}")

    @staticmethod
    def _find(tasks, task_id):
        for task in tasks:
            if task.id == task_id:
                return task
        raise ValueError(f"Task {task_id} not found.")

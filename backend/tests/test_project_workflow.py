import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nova import projects, store


class ProjectWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / "generated_projects"
        self.workspace.mkdir()
        self.records = {}
        self.settings_patch = patch.object(projects.settings, "projects_root", self.workspace)
        self.store_get_patch = patch.object(store, "get_project", side_effect=lambda project_id=None: self.records.get(project_id))
        self.store_save_patch = patch.object(
            store,
            "save_project",
            side_effect=lambda project_id, name, path, stack: self.records.__setitem__(
                project_id, {"id": project_id, "name": name, "path": str(path), "stack": stack}
            ),
        )
        self.settings_patch.start()
        self.store_get_patch.start()
        self.store_save_patch.start()
        self.addCleanup(self.settings_patch.stop)
        self.addCleanup(self.store_get_patch.stop)
        self.addCleanup(self.store_save_patch.stop)

    def create_project(self):
        project = projects.create_project("Calculator", "Four-function calculator", "react-vite")
        self.records[project["id"]] = project
        return project

    def test_react_project_contains_required_files_inside_workspace(self):
        project = self.create_project()

        self.assertTrue(Path(project["path"]).is_relative_to(self.workspace))
        self.assertTrue({"package.json", "src/App.tsx", "src/main.tsx", "vite.config.ts"}.issubset(projects.list_files(project["id"])))

    def test_dependency_build_and_server_actions_require_approval(self):
        project = self.create_project()

        for action in ("npm install", "npm run build"):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "approval"):
                projects.run_command(project["id"], action)
        with self.assertRaisesRegex(ValueError, "approval"):
            projects.start_server(project["id"])

    def test_project_file_writes_reject_paths_outside_workspace(self):
        project = self.create_project()

        with self.assertRaisesRegex(ValueError, "escapes"):
            projects.write_file(project["id"], "../outside.txt", "not allowed")

    def test_build_returns_real_exit_code_and_output(self):
        project = self.create_project()
        completed = projects.subprocess.CompletedProcess([], 7, "compiler output", "syntax error")

        with patch.object(projects.subprocess, "run", return_value=completed) as run:
            result = projects.run_command(project["id"], "npm run build", approved=True)

        self.assertEqual(result, {"exit_code": 7, "stdout": "compiler output", "stderr": "syntax error"})
        self.assertTrue(Path(run.call_args.kwargs["cwd"]).samefile(project["path"]))
        self.assertFalse(run.call_args.kwargs["shell"])


if __name__ == "__main__":
    unittest.main()

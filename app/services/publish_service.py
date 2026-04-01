from pathlib import Path
import subprocess
import sys

from app.core.config import settings


class PublishService:
    def trigger_publish(self, rendered_path: str) -> None:
        script = Path("scripts/publish_site.py")
        if not script.exists():
            return
        command = [
            sys.executable,
            str(script),
            "--rendered",
            rendered_path,
            "--remote",
            settings.git_remote,
            "--branch",
            settings.git_branch,
        ]
        if settings.git_auto_push:
            command.append("--push")
        subprocess.run(command, check=True)

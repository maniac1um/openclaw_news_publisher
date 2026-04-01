from pathlib import Path
import subprocess
import sys


class PublishService:
    def trigger_publish(self, rendered_path: str) -> None:
        script = Path("scripts/publish_site.py")
        if not script.exists():
            return
        subprocess.run([sys.executable, str(script), "--rendered", rendered_path], check=True)

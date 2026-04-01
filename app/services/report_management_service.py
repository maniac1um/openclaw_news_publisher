from pathlib import Path


class ReportManagementService:
    """Reusable report file management for public portal APIs."""

    def __init__(self, raw_root: Path, rendered_root: Path) -> None:
        self.raw_root = raw_root
        self.rendered_root = rendered_root

    def delete_reports(self, ingest_ids: list[str]) -> dict:
        deleted: list[str] = []
        not_found: list[str] = []
        for ingest_id in ingest_ids:
            raw_file = self.raw_root / f"{ingest_id}.json"
            rendered_file = self.rendered_root / f"{ingest_id}.json"
            raw_deleted = False
            rendered_deleted = False
            if raw_file.exists():
                raw_file.unlink()
                raw_deleted = True
            if rendered_file.exists():
                rendered_file.unlink()
                rendered_deleted = True
            if raw_deleted or rendered_deleted:
                deleted.append(ingest_id)
            else:
                not_found.append(ingest_id)
        return {
            "requested": len(ingest_ids),
            "deleted": deleted,
            "not_found": not_found,
        }

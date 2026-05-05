from pathlib import Path, PureWindowsPath

from assetflow.config import Settings


def resolve_export_output_path(settings: Settings, output_path: str) -> Path:
    stripped_output_path = output_path.strip()
    windows_output = PureWindowsPath(stripped_output_path)
    if not stripped_output_path or windows_output.is_absolute() or windows_output.drive:
        raise ValueError("Output path must be a file name or relative path under the export directory.")
    if ".." in windows_output.parts:
        raise ValueError("Output path must not contain '..'.")

    relative_output = Path(stripped_output_path)
    if relative_output.is_absolute() or relative_output.drive:
        raise ValueError("Output path must be a file name or relative path under the export directory.")
    if ".." in relative_output.parts:
        raise ValueError("Output path must not contain '..'.")

    export_dir = settings.export_dir.resolve()
    resolved_output = (export_dir / relative_output).resolve()
    try:
        resolved_output.relative_to(export_dir)
    except ValueError as exc:
        raise ValueError("Output path must stay under the export directory.") from exc
    return resolved_output

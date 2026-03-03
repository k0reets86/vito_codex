import os
from pathlib import Path


PROJECT_ROOT = Path(
    os.getenv("PROJECT_ROOT", str(Path(__file__).resolve().parents[1]))
).resolve()


def root_path(*parts: str) -> str:
    return str(PROJECT_ROOT.joinpath(*parts))

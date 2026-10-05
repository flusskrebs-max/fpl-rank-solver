from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
PROJECTIONS_DIR = DATA_DIR / "projections"
DATASETS_DIR = PROJECT_ROOT / "datasets"
UPSTREAM_DIR = PROJECT_ROOT / "vendor" / "open-fpl-solver"

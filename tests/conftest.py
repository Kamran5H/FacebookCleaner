"""Point the app at a throwaway data folder *before* it is imported, so the
suite can never read or overwrite a real scanned_data.json / purge history."""

import os
import sys
import tempfile
from pathlib import Path

_DATA_DIR = tempfile.mkdtemp(prefix="fbc-tests-")
os.environ["FBC_DATA_DIR"] = _DATA_DIR
os.environ.setdefault("LOCALAPPDATA", _DATA_DIR)

BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

"""Snapshot the monolith's OpenAPI document: the e2e suite's shape oracle.

The monolith (api/) is the behaviour the services must keep. Its response models, as
OpenAPI schemas, are what the e2e suite checks every response body against
(e2e/shapes.py). api/ is deleted in build step 5, so the snapshot is committed:

    api/.venv/bin/python e2e/oracle/export_monolith_openapi.py

Run it from the repository root on a branch that still has api/. Nothing connects to a
database: FastAPI builds the document from the routes alone.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))

from app.main import app  # noqa: E402

out = Path(__file__).resolve().with_name("monolith-openapi.json")
out.write_text(json.dumps(app.openapi(), indent=1, sort_keys=True) + "\n")
print(f"Wrote {out.relative_to(ROOT)} ({len(app.openapi()['paths'])} paths)")

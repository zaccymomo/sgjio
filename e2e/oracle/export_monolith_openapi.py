"""Snapshot the monolith's OpenAPI document: the e2e suite's shape oracle.

RUN THIS ON `main`, NOT ON THIS BRANCH. The monolith (api/) only exists on `main`; this
branch deleted it, so here the import below fails by design.

The monolith is the behaviour the services must keep. Its response models, as OpenAPI
schemas, are what the e2e suite checks every response body against (e2e/shapes.py). The
snapshot, e2e/oracle/monolith-openapi.json, is committed and frozen; regenerate it only if
`main`'s API changes and this branch is meant to follow:

    git worktree add ../sgjio-main main               # a checkout of main beside this one
    cd ../sgjio-main                                  # with api/.venv set up as README says
    api/.venv/bin/python e2e/oracle/export_monolith_openapi.py
    cp e2e/oracle/monolith-openapi.json <this checkout>/e2e/oracle/

(If main does not have this script, copy it there first.) Nothing connects to a database:
FastAPI builds the document from the routes alone.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "api" / "app" / "main.py").is_file():
    sys.exit("api/ is not here: run this on main (see the docstring), not on arch/microservices.")
sys.path.insert(0, str(ROOT / "api"))

from app.main import app  # noqa: E402

out = Path(__file__).resolve().with_name("monolith-openapi.json")
out.write_text(json.dumps(app.openapi(), indent=1, sort_keys=True) + "\n")
print(f"Wrote {out.relative_to(ROOT)} ({len(app.openapi()['paths'])} paths)")

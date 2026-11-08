"""Snapshot the monolith's OpenAPI document: the e2e suite's shape oracle.

HISTORICAL. The monolith (api/) was removed in #21; its last version is commit 1afb4b3,
so this only runs on a checkout of that commit (or earlier).

The monolith is the behaviour the services must keep. Its response models, as OpenAPI
schemas, are what the e2e suite checks every response body against (e2e/shapes.py). The
snapshot, e2e/oracle/monolith-openapi.json, is committed. Since the monolith is gone, a
deliberate change to the public API is made in the snapshot by hand, in the same PR: copy the
changed schemas from the owning service's /openapi.json (sorted keys, indent 1). To rebuild it
from the monolith itself:

    git worktree add ../sgjio-monolith 1afb4b3        # the monolith's last version
    cd ../sgjio-monolith                              # with api/.venv set up as its README says
    api/.venv/bin/python <this checkout>/e2e/oracle/export_monolith_openapi.py
    cp e2e/oracle/monolith-openapi.json <this checkout>/e2e/oracle/

 Nothing connects to a database:
FastAPI builds the document from the routes alone.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "api" / "app" / "main.py").is_file():
    sys.exit("api/ is not here: run this on the monolith (commit 1afb4b3), see the docstring.")
sys.path.insert(0, str(ROOT / "api"))

from app.main import app  # noqa: E402

out = Path(__file__).resolve().with_name("monolith-openapi.json")
out.write_text(json.dumps(app.openapi(), indent=1, sort_keys=True) + "\n")
print(f"Wrote {out.relative_to(ROOT)} ({len(app.openapi()['paths'])} paths)")

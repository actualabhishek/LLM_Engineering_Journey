"""
CLI validator for pipeline hand-offs. The Dispatcher pipes every subagent's
JSON output through this before trusting it or passing it to the next agent
-- a hand-off that fails validation is a PipelineError, not something to
patch up or guess at.

Usage:
    python validate.py <ModelName> <json-file>
    python validate.py <ModelName> -        # read JSON from stdin

Exit code 0 + "OK" on stdout if valid, exit code 1 + the validation error
message on stderr if not.

NOTE: in the real project this lives at dispatcher/validate.py and imports
from a sibling models/ package (`from models import schemas`); the import
below is adjusted since this copy sits alongside schemas.py directly.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pydantic import BaseModel, ValidationError

import schemas

MODELS: dict[str, type[BaseModel]] = {
    "IncidentFound": schemas.IncidentFound,
    "StoreLookupRequest": schemas.StoreLookupRequest,
    "StoreContactInfo": schemas.StoreContactInfo,
    "EmailSendRequest": schemas.EmailSendRequest,
    "EmailSentConfirmation": schemas.EmailSentConfirmation,
    "IncidentFinalizeRequest": schemas.IncidentFinalizeRequest,
    "IncidentFinalizedForLog": schemas.IncidentFinalizedForLog,
    "AirtableLogRecord": schemas.AirtableLogRecord,
    "PipelineError": schemas.PipelineError,
}


def validate(model_name: str, data: dict) -> tuple[bool, str]:
    model_cls = MODELS.get(model_name)
    if model_cls is None:
        known = ", ".join(sorted(MODELS))
        return False, f"Unknown model '{model_name}'. Known models: {known}"
    try:
        instance = model_cls.model_validate(data)
    except ValidationError as e:
        return False, str(e)
    return True, instance.model_dump_json()


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2

    model_name, source = sys.argv[1], sys.argv[2]
    raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: input is not valid JSON: {e}", file=sys.stderr)
        return 1

    ok, result = validate(model_name, data)
    if ok:
        print("OK")
        print(result)
        return 0
    else:
        print(f"ERROR: {result}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

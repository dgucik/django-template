#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${repository_root}/backend"
export PYTHONPYCACHEPREFIX="${repository_root}/backend/.mutmut-pycache"

if ! uv run --locked python <<'PY'
import ast
from pathlib import Path

production_files = (
    path for path in Path("apps").rglob("*.py") if "tests" not in path.parts
)
has_functions = any(
    any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(ast.parse(path.read_text()))
    )
    for path in production_files
)
raise SystemExit(0 if has_functions else 1)
PY
then
    printf '%s\n' "Mutation testing skipped: backend/apps contains no production functions."
    exit 0
fi

uv run --locked mutmut run

mutation_results="$(uv run --locked mutmut results)"
if [[ -n "${mutation_results}" ]]; then
    printf '%s\n' "Mutation testing found non-killed mutants:" "${mutation_results}"
    exit 1
fi

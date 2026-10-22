#!/usr/bin/env bash
# Regenerate pydantic models from the Smithy contract.
#
# Smithy (smithy/models/*.smithy) is the single source of truth: gradle builds
# OpenAPI, datamodel-codegen emits snake_case pydantic v2 models with camelCase
# aliases on GeneratedBaseModel — the backend honors the camelCase wire contract
# the web client targets.
#
# backend/schemas/generated/models.py is GENERATED AND GITIGNORED, like cortex:
# nothing generated is reviewed. Run this after checkout and after any
# smithy/ change; the backend imports it. Requires a JDK on PATH.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENAPI="$REPO_ROOT/build/smithy/openapi/openapi/Groundwork.openapi.json"
GENERATED_DIR="$REPO_ROOT/backend/schemas/generated"

if ! command -v java >/dev/null 2>&1; then
  echo "error: java not found. Install a JDK and put it on PATH (or export JAVA_HOME)." >&2
  exit 1
fi

echo "==> gradle smithyBuild"
(cd "$REPO_ROOT" && smithy/gradlew smithyBuild --project-dir smithy --rerun-tasks -q)

rm -f "$GENERATED_DIR/models.py"
mkdir -p "$GENERATED_DIR"
touch "$GENERATED_DIR/__init__.py"

# Runs via uvx (not a project dev dep): datamodel-codegen 0.86 pins isort<9,
# while the project lints with isort 9 — the isolated env avoids the conflict.
echo "==> codegen: $OPENAPI -> $GENERATED_DIR/models.py"
(cd "$REPO_ROOT" && uvx --from datamodel-code-generator==0.86.0 datamodel-codegen \
  --input "$OPENAPI" \
  --input-file-type openapi \
  --output "$GENERATED_DIR/models.py" \
  --output-model-type pydantic_v2.BaseModel \
  --base-class backend.schemas.generated_base.GeneratedBaseModel \
  --snake-case-field \
  --use-default \
  --use-annotated \
  --use-standard-collections \
  --use-union-operator \
  --use-double-quotes \
  --strict-nullable \
  --target-python-version 3.14 \
  --disable-timestamp)

echo "==> done"

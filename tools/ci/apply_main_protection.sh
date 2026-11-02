#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
# Requires a GitHub credential with Administration: write for this repository.
# The task connector returned HTTP 403; this operation must not report success on denial.
gh api --method PUT repos/byYorick/hydro2.0/branches/main/protection \
  --input .github/main-protection.json

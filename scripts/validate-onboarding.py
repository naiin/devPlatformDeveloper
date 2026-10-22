#!/usr/bin/env python3
"""Validate the only files the portal is allowed to propose for onboarding."""
import re
import subprocess
import sys
from pathlib import Path
import yaml

base = sys.argv[1]
assert re.fullmatch(r"[0-9a-f]{40}", base), "Invalid base SHA"
files = subprocess.check_output(["git", "diff", "--name-only", f"{base}...HEAD"], text=True).splitlines()
assert files, "Empty onboarding request"
for file in files:
    match = re.fullmatch(r"gitops/onboarded/([a-z][a-z0-9-]{2,30})/app.yaml", file)
    assert match, f"Unexpected onboarding change: {file}"
    name = match[1]
    data = yaml.safe_load(Path(file).read_text())
    assert data == {"name": name, "repoURL": f"https://github.com/naiin/{name}.git",
                    "chartPath": "gitops/charts/platform", "valuesFile": "../../environments/staging/platform/values.yaml"}, "Unexpected discovery configuration"
print(f"Validated {len(files)} onboarding entries; human review is still required.")

"""External tools required by SciSkill workflows."""

import shutil
import subprocess

REQUIRED_TOOLS = ("uv", "uvx")


def check_required_tools():
    versions = {}
    failures = []
    for name in REQUIRED_TOOLS:
        executable = shutil.which(name)
        if executable is None:
            failures.append(f"{name}: not found on PATH")
            continue
        try:
            result = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            output = result.stdout.strip()
            if result.returncode != 0 or not output:
                failures.append(f"{name}: version check failed")
            else:
                versions[name] = output.splitlines()[0]
        except (OSError, subprocess.TimeoutExpired):
            failures.append(f"{name}: could not run version check")
    if failures:
        raise ValueError("Required tools unavailable: " + "; ".join(failures))
    return versions

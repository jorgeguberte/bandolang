"""protocol.py — Python-Rust Conformance Protocol Bridge for SOMA-IR Slice 1.

Encodes High-Level SOMA-IR programs as JSON, executes the Rust bando-conformance toolchain,
and deserializes canonical ConformanceObservationV0 outputs.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


REPO_ROOT = Path(__file__).parent.parent.parent
RUST_BIN = REPO_ROOT / "target" / "debug" / "bando-conformance.exe"


def ensure_rust_binary():
    if not RUST_BIN.exists():
        subprocess.run(["cargo", "build", "--bin", "bando-conformance"], cwd=REPO_ROOT, check=True)


def invoke_rust_conformance(program_json: dict[str, Any]) -> dict[str, Any]:
    """Execute the Rust bando-conformance binary with the given program dictionary."""
    ensure_rust_binary()
    input_str = json.dumps(program_json)
    proc = subprocess.run(
        [str(RUST_BIN)],
        input=input_str,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Rust bando-conformance crashed with returncode {proc.returncode}:\nStdout: {proc.stdout}\nStderr: {proc.stderr}")
    return json.loads(proc.stdout)

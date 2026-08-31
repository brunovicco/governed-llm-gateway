"""Test path setup for credential-free workspace tests."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for source in (
    ROOT / "packages/gateway-contracts/src",
    ROOT / "packages/gateway-core/src",
    ROOT / "packages/gateway-client/src",
    ROOT / "apps/gateway-api/src",
):
    sys.path.insert(0, str(source))

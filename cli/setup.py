from __future__ import annotations

import sys
from pathlib import Path

from setuptools import setup


ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from build_validation import validate_packaged_sdk_wheel


validate_packaged_sdk_wheel(ROOT)

setup()

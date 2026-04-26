"""Test config — make `client.*` imports work without installing the package."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

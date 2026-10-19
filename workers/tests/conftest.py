"""pytest setup: make this folder importable so tests can ``import fakes`` without installing anything."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

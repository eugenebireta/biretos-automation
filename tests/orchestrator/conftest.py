import os
import sys

_orch = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator"))
if _orch not in sys.path:
    sys.path.insert(0, _orch)

import os
import sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_orch = os.path.join(_root, "orchestrator")

for _p in (_root, _orch):
    if _p not in sys.path:
        sys.path.insert(0, _p)

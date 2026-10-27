"""pytest config: make the Lambda source importable as `app`."""
import os
import sys

_HERE = os.path.dirname(__file__)
_SRC = os.path.abspath(os.path.join(_HERE, "..", "visitor_counter"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

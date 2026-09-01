__version__ = "0.1.36"

from urai import *
from .core import *

# Hosted remote/claude/copilot dependencies are baseline, but backend modules remain lazy.
# Local litert/llama/mlx/ollama dependencies are optional extras.
_backends = ('litert', 'llama', 'mlx', 'ollama', 'remote', 'claude', 'copilot')

def __getattr__(name):
    "Import a backend submodule on first attribute access (`rishi.llama` without a hard dependency)."
    if name in _backends:
        from importlib import import_module
        return import_module(f'.{name}', __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def __dir__(): return sorted(list(globals()) + list(_backends))

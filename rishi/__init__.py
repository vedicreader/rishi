__version__ = "0.1.23"

from .core import *
from .core import Chat, AsyncChat

# Backends are optional extras (`pip install 'rishi[litert]'`, `[llama]`, `[mlx]`), so importing one
# eagerly here would make `import rishi` fail on a machine that only has the others. `Chat(model)`
# imports the backend it actually needs, lazily, via `core.get_runtime`. `rishi.litert` and friends
# still work as ordinary submodule imports; this only stops them being *required*.
_backends = ('litert', 'llama', 'mlx', 'ollama', 'remote')

def __getattr__(name):
    "Import a backend submodule on first attribute access (`rishi.llama` without a hard dependency)."
    if name in _backends:
        from importlib import import_module
        return import_module(f'.{name}', __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def __dir__(): return sorted(list(globals()) + list(_backends))

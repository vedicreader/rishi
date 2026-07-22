__version__ = "0.0.3"
from .core import *

def __getattr__(name):
    # lazy backend submodules: rishi.litert (litert_lm) and rishi.llama (llama-cpp-python, optional extra)
    if name in ('litert', 'llama'):
        import importlib
        return importlib.import_module(f'.{name}', __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

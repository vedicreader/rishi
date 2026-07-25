__version__ = "0.0.3"
from .core import *

def __getattr__(name):
    # lazy submodules: rishi.litert (litert_lm), rishi.llama (llama-cpp-python, optional extra),
    # and rishi.auto (picks one from the model name)
    if name in ('litert', 'llama', 'auto'):
        import importlib
        return importlib.import_module(f'.{name}', __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

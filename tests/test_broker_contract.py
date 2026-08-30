#!/usr/bin/env python
"""Every broker's backend still satisfies what `ChatBroker` calls on it.

`urai` tests the broker protocol itself against a stub. What nothing tests is the seam on this
side: `ChatBroker` builds the shared engine with `chat_cls.create_engine(model_id=...)` and then
opens each client with `chat_cls(engine=..., messages=..., tools=())`. A backend can drift out of
that shape without any notebook noticing, because loading a real model is the only other way to
find out. These checks load nothing.

    python tests/test_broker_contract.py         # or: pytest tests/test_broker_contract.py
"""
import inspect, sys, types
from pathlib import Path


def _stub_mlx():
    "mlx only installs on arm64 macOS, so stand it in to reach `rishi.mlx` at all."
    if 'mlx_lm' in sys.modules: return
    def mod(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items(): setattr(m, k, v)
        sys.modules[name] = m
        return m
    mod('mlx'); sys.modules['mlx'].core = mod('mlx.core', random=types.SimpleNamespace(seed=lambda s: None))
    mod('mlx_lm', load=lambda *a, **k: (None, None, {}), stream_generate=lambda *a, **k: iter(()))
    mod('mlx_lm.sample_utils', make_sampler=lambda **k: object())
    mod('mlx_lm.models.cache', make_prompt_cache=lambda m, mx=None: ['live'],
        trim_prompt_cache=lambda c, n: n, can_trim_prompt_cache=lambda c: True,
        save_prompt_cache=lambda p, c, md=None: Path(p).write_text('{}'),
        load_prompt_cache=lambda p, return_metadata=False: ({}, {}) if return_metadata else {})
    sys.modules['mlx_lm'].models = mod('mlx_lm.models')
    sys.modules['mlx_lm'].models.cache = sys.modules['mlx_lm.models.cache']


_stub_mlx()
from rishi.litert import LitertBroker, LitertChat      # noqa: E402
from rishi.llama import LlamaBroker, LlamaChat         # noqa: E402
from rishi.mlx import MlxBroker, MlxChat               # noqa: E402

BROKERS = [(LitertBroker, LitertChat), (LlamaBroker, LlamaChat), (MlxBroker, MlxChat)]


def test_each_broker_serves_its_own_chat_class():
    for broker, chat in BROKERS:
        assert broker('/tmp/rishi-contract.sock').chat_cls is chat, broker.__name__


def test_create_engine_takes_the_arguments_the_broker_builds_it_with():
    "`_mk_engine` calls `create_engine(model_id=..., **engine_kw)` and nothing else."
    for broker, chat in BROKERS:
        sig = inspect.signature(chat.create_engine)
        assert 'model_id' in sig.parameters, f'{chat.__name__}.create_engine lost model_id'
        assert any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values()), \
            f'{chat.__name__}.create_engine must accept the broker\'s engine_kw'


def test_a_client_chat_can_be_opened_on_a_shared_engine():
    "`_handle` opens every client as `chat_cls(engine=..., messages=..., tools=())`."
    for broker, chat in BROKERS:
        sig = inspect.signature(chat.__init__)
        p = sig.parameters
        assert 'engine' in p, f'{chat.__name__} cannot be handed a shared engine'
        assert p['engine'].kind is p['engine'].KEYWORD_ONLY, f'{chat.__name__}.engine must be keyword-only'
        assert any(q.kind is q.VAR_KEYWORD for q in p.values()), \
            f'{chat.__name__} must pass messages and tools through to ChatOpts'
        assert callable(getattr(chat, 'close', None)), f'{chat.__name__} has no close for the broker to call'


def test_the_brokers_model_id_reaches_create_engine():
    for broker, chat in BROKERS:
        seen = {}
        orig = chat.create_engine
        chat.create_engine = classmethod(lambda cls, **kw: seen.update(kw) or 'engine')
        try:
            b = broker('/tmp/rishi-contract.sock', model_id='some/model', n_ctx=4096)
            assert b._mk_engine() == 'engine'
            assert seen.get('model_id') == 'some/model', f'{broker.__name__} dropped model_id: {seen}'
            assert seen.get('n_ctx') == 4096, f'{broker.__name__} dropped engine_kw: {seen}'
        finally: chat.create_engine = orig


def test_an_engine_the_broker_was_handed_is_never_closed_by_it():
    "Only an engine the broker built is the broker's to release."
    class _Eng:
        closed = False
        def close(self): self.closed = True
    for broker, chat in BROKERS:
        given = _Eng()
        b = broker('/tmp/rishi-contract.sock', engine=given)
        b._shut_engine()
        assert given.closed is False, f'{broker.__name__} closed an engine it did not build'
        b2 = broker('/tmp/rishi-contract.sock')
        b2.engine = own = _Eng()
        b2._shut_engine()
        assert own.closed is True, f'{broker.__name__} leaked the engine it built'


def test_every_backend_engine_can_actually_be_released():
    "`_shut_engine` releases through `close`, so an engine that only has `__exit__` would leak."
    from litert_lm import Engine
    assert callable(getattr(Engine, 'close', None)), 'litert Engine needs close, not just __exit__'
    from llama_cpp import Llama
    assert callable(getattr(Llama, 'close', None)), 'llama_cpp Llama needs close'


if __name__ == '__main__':
    fns = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for f in fns: f(); print('ok', f.__name__)
    print(f'{len(fns)} passed')

#!/usr/bin/env python
"""The MLX prefix-cache wiring, exercised without Apple Silicon.

`nbs/03_mlx.ipynb` is `skip_exec`, and mlx only installs on arm64 macOS, so the wiring between
`MlxChat` and `rishi.core.PrefixCache` has no notebook that can cover it. This stands in fake mlx
modules, drives the real `MlxChat` methods, and asserts what the cache has to guarantee: a longer
prefix is adopted, a restored prefix is trimmed to what actually matches rather than trusted, and
a write only happens once the prefix has grown enough to pay for itself.

    python tests/test_mlx_prefix_cache.py        # or: pytest tests/test_mlx_prefix_cache.py
"""
import json, sys, tempfile, types
from pathlib import Path


def _fake_mlx():
    "Register just enough of mlx-lm for `rishi.mlx` to import and for a cache to be a plain object."
    saved = {}
    def mod(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items(): setattr(m, k, v)
        saved[name] = sys.modules.get(name); sys.modules[name] = m
        return m
    mod('mlx')
    sys.modules['mlx'].core = mod('mlx.core', random=types.SimpleNamespace(seed=lambda s: None))
    mod('mlx_lm', load=lambda *a, **k: (None, None, {}), stream_generate=lambda *a, **k: iter(()))
    mod('mlx_lm.sample_utils', make_sampler=lambda **k: object())
    def save_prompt_cache(path, cache, metadata=None):
        Path(path).write_text(json.dumps({'cache': cache, 'md': metadata or {}}))
    def load_prompt_cache(path, return_metadata=False):
        d = json.loads(Path(path).read_text())
        return (d['cache'], d['md']) if return_metadata else d['cache']
    mod('mlx_lm.models.cache',
        make_prompt_cache=lambda model, mx=None: ['live'],
        trim_prompt_cache=lambda cache, n: n, can_trim_prompt_cache=lambda cache: True,
        save_prompt_cache=save_prompt_cache, load_prompt_cache=load_prompt_cache)
    sys.modules['mlx_lm'].models = mod('mlx_lm.models')
    sys.modules['mlx_lm'].models.cache = sys.modules['mlx_lm.models.cache']
    return saved


_fake_mlx()
from rishi.mlx import MlxChat, MlxEngine   # noqa: E402  (the fakes have to land first)


class _Tok:
    def encode(self, text): return [1, 2, 3]
    def apply_chat_template(self, msgs, **kw): return _Tok.ids


def mk_chat(dir, ids, **kw):
    "An `MlxChat` over a fake engine whose rendered prompt is exactly `ids`."
    _Tok.ids = ids
    eng = MlxEngine(object(), _Tok(), model_id='fake/model', cfg={'max_position_embeddings': 4096})
    return MlxChat(engine=eng, prefix_cache=dir, cache_store_every=4, **kw)


def test_a_longer_shared_prefix_is_adopted_and_then_trimmed_to_what_matches():
    d = tempfile.mkdtemp()
    a = mk_chat(d, list(range(512)))
    a._cache_ids = list(range(512))                 # a turn that filled the cache
    assert a._store_shared(), 'a grown prefix should be published'

    b = mk_chat(d, list(range(512)))                # a second conversation, cold
    assert b._cache_ids == []
    ids, feed, cached = b._feed_ids()
    assert cached == 511, f'expected the shared prefix to be adopted, got {cached}'
    assert feed == ids[511:], 'only the tail may be left to prefill'


def test_a_restored_prefix_longer_than_the_prompt_is_clamped_not_trusted():
    "The file covers 512 tokens; this prompt shares 400. The cache offset must follow the prompt."
    d = tempfile.mkdtemp()
    a = mk_chat(d, list(range(512))); a._cache_ids = list(range(512)); a._store_shared()

    shared = list(range(400)) + [999] * 5
    b = mk_chat(d, shared)
    ids, feed, cached = b._feed_ids()
    assert cached <= 400, f'restored more than the prompt actually shares: {cached}'
    assert ids[:cached] == b._cache_ids[:cached], 'the kept prefix must match the prompt exactly'


def test_a_prefix_that_has_not_grown_enough_is_not_written():
    d = tempfile.mkdtemp()
    c = mk_chat(d, list(range(512)))
    c._cache_ids = list(range(3))                  # under cache_store_every
    assert c._store_shared() is False
    assert c.shared_cache.entries == []


def test_a_shared_cache_is_never_built_for_a_chat_that_has_no_kv_cache():
    d = tempfile.mkdtemp()
    c = mk_chat(d, list(range(512)), prompt_cache=False)
    assert c.shared_cache is None
    assert c._store_shared() is False


def test_another_model_never_restores_this_ones_keys():
    d = tempfile.mkdtemp()
    a = mk_chat(d, list(range(512))); a._cache_ids = list(range(512)); a._store_shared()
    b = mk_chat(d, list(range(512)), kv_bits=4)     # a different cache setting is a different fingerprint
    assert b.shared_cache.entries == [], 'a cache saved under other settings must be invisible'
    assert b._feed_ids()[2] == 0


if __name__ == '__main__':
    fns = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for f in fns: f(); print('ok', f.__name__)
    print(f'{len(fns)} passed')

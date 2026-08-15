# Unify `Chat` across backends over one shared `core` — Implementation Plan (v2, prune-based)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the duplicated litert/llama `Chat` implementations into one shared `rishi.core.Chat` base + two thin backend subclasses, with backend selection built into `Chat`, and delete `rishi.auto`.

**Architecture:** `rishi.core` = backend-agnostic layer + a `Chat` base whose `__new__` dispatches to `LitertChat` (`rishi.litert`) or `LlamaChat` (`rishi.llama`) by `runtime=`/model shape. Turn execution (`_send`/`_stream`) and encoding (`mk_msg`) are per-backend hooks; the surround (callbacks machinery, `__call__`, `classify`/`structured`/`check`, `AsyncChat`) is shared.

**Starting point (already done by the operator):** `nbs/02_litert.ipynb` is a **full copy of `00_core.ipynb`** with `#| default_exp litert` already set; the old alias litert is gone. So each backend notebook is *pruned to its role*, not built from scratch: `00_core` drops the litert-specific cells and gains the shared base; `02_litert` drops the shared cells (imports them from core) and keeps the litert-specific cells as a `LitertChat` subclass. `01_llama` already exists and only needs subclass conversion.

**Dependency graph:** `litert` and `llama` both depend only on `core`, never on each other → **Task 1 (core) first, then Tasks 2 (litert) and 3 (llama) run in parallel**, then Task 4 (cleanup).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-30-unify-chat-backends-design.md`.
- nbdev: notebooks are source; tests are cells (`#| eval: false` skipped). Never hand-edit `rishi/*.py`.
- fastai style: `store_attr`, `patch`, `delegates`, `first`, `L`, `ifnone`; one-line docstrings.
- `llama-cpp-python==0.3.30` pinned. Selector kwarg is **`runtime`**, never `backend` (litert `backend=Backend.GPU()` passes through).
- `from rishi import *` keeps exposing `Chat`, `AsyncChat`, `resp_text`, `display_stream`, `thought`, `truncated`, `UsageStats`, `hitl_policy`, `extract_fence`, and `mk_msg`/`mk_content`/`mk_msgs` (shims). Bare `Chat()` = litert default model.
- **The worker must NOT run git.** Commit checkpoints are for the human operator.

### Export & test (use every task)

```bash
./.venv/bin/python -c "from nbdev.doclinks import nbdev_export; nbdev_export.__wrapped__()"
./.venv/bin/python -c "from nbdev.test import nbdev_test; nbdev_test.__wrapped__(path='nbs/00_core.ipynb')"
```
Edit cells programmatically (ipynb Read overflows): load JSON, `cell['source']=text.splitlines(keepends=True)`, clear code `outputs`/`execution_count`, `json.dump(indent=1, ensure_ascii=False)`. Locate cells by a source substring or section heading.

## The shared contract (what `core` MUST keep exporting)

Ground truth = llama's current `from rishi.core import (...)` + shared utilities/constants:
`UsageStats, ChatCallback, run_cbs, resp_text, thought, quote_, Resp, mk_tr_details, StreamFormatter, display_stream, truncated, TruncationCallback, hitl_policy, extract_code, extract_fence, matches_, mk_result_fence, run_coro, run_py, task_complete, output_matches, PyFenceCallback, grades, repo_root, mv_skill_md, qa_sp_, tool_reminder_`
**plus new:** `Chat, AsyncChat, mk_msg, mk_content, mk_msgs` (shims), `runtimes, dflt_runtime, split_runtime, infer_runtime, resolve_runtime, get_runtime, _mk_obj`.

## The hook interface (every backend subclass provides)

class attr `_runtime` · `__init__(self, model=None, *, runtime=None, model_path=None, …backend kw…)` (build engine, set `self.ctx_limit`, then `self._setup(...)`) · `mk_content/mk_msg/mk_msgs` (module funcs bound as `staticmethod`) · `_send(msg, max_output_tokens=None)->Resp` · `_stream(msg, max_output_tokens=None, cbs=None)` (generator) · `token_count` (property) · `count_tokens(text)->int` · `_oneshot(prompt, sp)->str` · `_structured_call(prompt, schema, sp)->dict` · `close()`. Each backend defines its own concrete callbacks + `_dflt_cbs`.

---

## Task 1 — `core`: prune litert-specifics, add the shared base (PREREQUISITE)

**Files:** Modify `nbs/00_core.ipynb` → `rishi/core.py`. Tests: cells in `00_core`.

**Interfaces produced:** the shared contract above (the hook interface is consumed by Tasks 2–3).

- [ ] **Step 1: Strip litert from core's import cell; add stdlib helpers**

Remove litert imports (`Engine, Backend, SamplerConfig, Content, Text, Message, Role, Contents, ImageBytes, AudioBytes, ImageFile, AudioFile, normalize_message, Benchmark, ToolEventHandler, set_min_log_severity, guess_type`) and `import numpy`/audio bits if litert-only. Add:
```python
import asyncio
from importlib import import_module
from dataclasses import is_dataclass
from typing import get_type_hints
```
Keep `from fastcore.all import Path, store_attr, patch, L, GetAttr, ifnone, first, listify, AttrDict` (+ `detect_mime` only if still used by a shared cell; it isn't → drop).

- [ ] **Step 2: DELETE the litert-specific cells from `00_core`**

Delete these cells (they live in `02_litert` after Task 2):
- `mk_content, mk_msg, mk_msgs` (## Messages export) — replaced by shims in Step 5.
- `ToolReminderCallback` (## Built-in callbacks) — litert version mutates `turn_msg.contents.contents`.
- `HistoryCallback, UsageCallback` (keep `truncated`+`TruncationCallback` — move them to their own export cell) — litert versions.
- `_tc_name, _tool_msg, ChatToolHandler` (## Tool calling) — litert tool-event handler.
- `_litertlm, _cached_model, get_model, _merge_chunks, Chat` (## Loading models & Chat) — litert.
- `bench` (from ## Utilities export) — litert.
- litert default ids (`gemma4_e2b, gemma4_e2b, gemma4_12b`) — litert.
- litert-only test cells: `_Chat`, `_C`, `_S`, the `#| eval:false` litert model/usage/streaming/images cells, and the `Person`/`add`/`delete_files` example cells. Keep pure-Python test cells for kept symbols (`_Dummy/_A/_B` for callbacks, `_CbHost/_X/_Y`, the StreamFormatter test, extract/run_py tests, grades test, skill test).

Keep in core (shared): `UsageStats`; `ChatCallback, run_cbs`; `resp_text, thought, quote_, Resp, _tc_summary, mk_tr_details, StreamFormatter, display_stream`; `truncated, TruncationCallback`; `hitl_policy, _ask_console`; `extract_code, extract_fence, matches_, mk_result_fence, run_coro, run_py, task_complete, output_matches, PyFenceCallback`; `grades`; `repo_root, mv_skill_md`; `qa_sp_, tool_reminder_`.

- [ ] **Step 3: Write the failing test cell (resolution, dispatch, base surface)**

Add near the end (before the `#| hide` export):
```python
from fastcore.test import test_eq, test_fail
test_eq(split_runtime('llama/Qwen/Qwen3-4B-GGUF'), ('llama', 'Qwen/Qwen3-4B-GGUF'))
test_eq(split_runtime('litert-community/gemma-4-E2B-it-litert-lm'), (None, 'litert-community/gemma-4-E2B-it-litert-lm'))
test_eq(infer_runtime('Qwen/Qwen3-0.6B-GGUF'), 'llama'); test_eq(infer_runtime('/m/x.litertlm'), 'litert')
test_eq(resolve_runtime('llama/my'), ('llama','my')); test_eq(resolve_runtime(), ('litert', None))
test_fail(lambda: resolve_runtime('gemma-4-E2B'), contains="Can't tell which backend")
test_fail(lambda: resolve_runtime('x', runtime='mlx'), contains='Unknown runtime')
from dataclasses import dataclass
@dataclass
class _A: year:int; month:int
@dataclass
class _P: name:str; age:_A
test_eq(_mk_obj(_P, {'name':'Alice','age':{'year':1995,'month':6}}).age, _A(1995,6))
# base surface via a fake subclass (no engine)
class _FakeChat(Chat):
    _runtime='litert'
    def __init__(self, **kw): self.ctx_limit=100; self._setup(**kw)
    def mk_msgs(self, msgs): return list(msgs or [])
    def _oneshot(self, prompt, sp): return 'positive because good'
    def _structured_call(self, prompt, schema, sp): return {'name':'Alice','age':{'year':1995,'month':6}}
    def _send(self, msg, mot=None): return Resp({'role':'assistant','content':'ok'})
    def close(self): pass
c=_FakeChat(sp='hi')
test_eq(c.classify('great', ['positive','negative']), 'positive')
test_eq(c.structured('x', _P).age, _A(1995,6))
test_eq(run_coro(AsyncChat(c)('go')), Resp({'role':'assistant','content':'ok'}))
```

- [ ] **Step 4: Run test → verify it fails**

`./.venv/bin/python -c "from nbdev.test import nbdev_test; nbdev_test.__wrapped__(path='nbs/00_core.ipynb')"` → FAIL (`split_runtime` undefined).

- [ ] **Step 5: Add the export cells — resolution+registry+`_mk_obj`, base `Chat`, `AsyncChat`, shims**

Resolution/registry/`_mk_obj` cell (verbatim from spec §Dispatch): `runtimes, dflt_runtime, _pats, split_runtime, infer_runtime, resolve_runtime, _runtime_mod, get_runtime, _is_path, _mk_obj`.

Base `Chat` cell:
```python
#| export
class Chat:
    "Backend-agnostic chat: `Chat(model)` dispatches to the litert/llama subclass by `runtime`/model shape."
    def __new__(cls, model=None, *, runtime=None, model_path=None, **kw):
        if cls is not Chat: return super().__new__(cls)
        nm, _ = resolve_runtime(model, runtime, model_path)
        return super().__new__(get_runtime(nm))
    def _setup(self, model=None, sp='', messages=None, tools=None, approve=None,
               tool_max_len=None, max_steps=10, cbs=None, default_cbs=True):
        "Shared init tail: strip runtime prefix, store shared fields, build history, register callbacks."
        _, model = split_runtime(model)
        self.tools = L(tools); self.hist = self.mk_msgs(messages)
        store_attr('sp,approve,tool_max_len,max_steps', self)
        self.use, self.cbs, self.turn_msg, self.turn_res = UsageStats(), L(), None, None
        if default_cbs: self.add_cbs(self._dflt_cbs)
        self.add_cbs(cbs); return model
    @property
    def runtime(self): return self._runtime
    @property
    def pct_full(self): return self.token_count / self.ctx_limit
    def add_cb(self, cb):
        if isinstance(cb, type): cb = cb()
        cb.chat = self; self.cbs.append(cb); return cb
    def add_cbs(self, cbs): return L(cbs).map(self.add_cb)
    def remove_cb(self, cb):
        keep = (lambda c: not isinstance(c, cb)) if isinstance(cb, type) else (lambda c: c is not cb)
        self.cbs = self.cbs.filter(keep); return self
    def remove_cbs(self, cbs): L(cbs).map(self.remove_cb); return self
    def print_hist(self):   # move existing body verbatim from old core.Chat
        ...
    def __call__(self, msg=None, stream=False, max_output_tokens=None, cbs=None):
        "Run one chat turn; a `Resp` (or a markdown-chunk generator when `stream=True`)."
        self.use = UsageStats()
        if stream: return self._stream(msg, max_output_tokens, cbs)
        added = self.add_cbs(cbs)
        try: return self._send(msg, max_output_tokens)
        finally: self.remove_cbs(added)
    def __del__(self):
        try: self.close()
        except Exception: pass
```
Shared `classify`/`structured`/`check` over hooks (replace old litert-engine versions):
```python
#| export
@patch
def classify(self:Chat, text, labels, sp='Reply with only the single best label and nothing else.'):
    out = self._oneshot(f"{text}\n\nChoose exactly one label from: {', '.join(labels)}.", sp).lower()
    return first(labels, lambda l: l.lower() in out) or out.strip()
@patch
def structured(self:Chat, prompt, schema, sp='Reply with only a JSON object matching the schema.'):
    return _mk_obj(schema, self._structured_call(prompt, schema, sp))
@patch
def check(self:Chat, question, expected, grade_fn=matches_, llm_judge=False, judge=None, tag='answer', sp=qa_sp_):
    a = extract_fence(self._oneshot(question, sp), tag)
    ok = (judge or self).grades(question, expected, a) if (llm_judge or judge) else grade_fn(a, expected)
    return AttrDict(question=question, expected=expected, answer=a, ok=ok)
```
Update `grades` (`@patch`) to call `self._oneshot(judge_prompt, sp)` instead of the engine directly.
`AsyncChat` + encoder shims cell (verbatim from spec §Dispatch / §AsyncChat), using `_runtime_mod(dflt_runtime)`.
Update `__all__` to the shared contract list above (add the new names; keep `mk_msg/mk_content/mk_msgs`; drop litert-only names).

- [ ] **Step 6: Export + test → verify pass**

Run export + `nbdev_test` on `00_core`. Expected: PASS. (`get_runtime`/`_runtime_mod` aren't exercised yet — backends arrive in Tasks 2–3.)

- [ ] **Step 7: Checkpoint (human commits)**

`git add nbs/00_core.ipynb rishi/core.py && git commit -m "core: shared Chat base + dispatch + AsyncChat + shims; drop litert impl"`

---

## Task 2 — `litert`: prune the core-copy to the litert backend  ⟂ (parallel with Task 3)

**Depends on:** Task 1 (needs `core.Chat` + hook interface). **Files:** Modify `nbs/02_litert.ipynb` → `rishi/litert.py`.

**Interfaces:** Consumes `core.Chat`, `core._mk_obj`, the shared contract. Produces `litert.LitertChat`, `litert.mk_msg/mk_content/mk_msgs/get_model/bench` + litert defaults; makes `runtimes['litert']` live.

- [ ] **Step 1: Replace the import cell — import shared names from core**

`02_litert` currently re-imports litert libs *and* redefines the shared layer (it's a copy). Change the first `#| export` import cell to keep the litert library imports (`Engine, Backend, SamplerConfig, Content, Text, Message, Role, Contents, ImageBytes, AudioBytes, ImageFile, AudioFile, normalize_message, Benchmark, ToolEventHandler, set_min_log_severity, guess_type`, `numpy` if used) and add:
```python
from rishi import core
from rishi.core import (Chat, UsageStats, ChatCallback, run_cbs, resp_text, thought, quote_, Resp,
                        mk_tr_details, StreamFormatter, display_stream, truncated, TruncationCallback,
                        hitl_policy, extract_fence, matches_, qa_sp_, tool_reminder_, run_coro, _mk_obj)
```

- [ ] **Step 2: DELETE the shared cells from `02_litert`**

Delete every cell whose symbols now live in core (the "Keep in core" list from Task 1 Step 2): `UsageStats`; `ChatCallback, run_cbs`; the `resp_text…StreamFormatter…display_stream` cell; `truncated, TruncationCallback`; `hitl_policy, _ask_console`; the `extract_code…run_py…PyFenceCallback` cell; `grades`; `repo_root, mv_skill_md`; `qa_sp_, tool_reminder_`; the runtime-resolution/base-`Chat`/`AsyncChat`/shims/`_mk_obj` cells (Task 1 added those to core). Also delete their shared test cells. Keep litert-specific cells (Step 3).

- [ ] **Step 3: Keep + adapt the litert cells; make `LitertChat(core.Chat)`**

Keep (litert-specific): litert default ids; `mk_content/mk_msg/mk_msgs`; `_litertlm/_cached_model/get_model`; `_merge_chunks`; litert `ToolReminderCallback`, `HistoryCallback`, `UsageCallback`, `ChatToolHandler`, `_tc_name`, `_tool_msg`; `bench`; the litert model-cell demos (`#| eval:false`). Define the default-cbs list and the subclass:
```python
#| export
_dflt_cbs = [HistoryCallback, UsageCallback, ToolReminderCallback]   # litert's own callback classes

class LitertChat(core.Chat):
    "Sync chat over a local litert_lm engine."
    _runtime = 'litert'
    _dflt_cbs = _dflt_cbs
    mk_content, mk_msg, mk_msgs = staticmethod(mk_content), staticmethod(mk_msg), staticmethod(mk_msgs)
    # create_engine: keep the existing classmethod verbatim
    def __init__(self, model=None, *, runtime=None, model_path=None, engine=None, backend=Backend.CPU(),
                 multimodal=True, cache_dir=None, enable_speculative_decoding=None, eng_kw=None,
                 sp='', messages=None, tools=None, ctx_limit=None, approve=None, tool_max_len=None,
                 max_steps=10, think=False, filter_think=True, temp=None, top_k=None, top_p=None,
                 seed=None, sampler_config=None, max_output_tokens=None, conv_kw=None, cbs=None, default_cbs=True):
        model = core.split_runtime(model)[1]
        model_id = None if model is None or core._is_path(model) else model
        model_path = model_path or (model if model and core._is_path(model) else None)
        self._stack = ExitStack()
        if not engine: engine = self.create_engine(model_id or gemma4_e2b, model_path, backend,
            multimodal=multimodal, cache_dir=cache_dir, enable_speculative_decoding=enable_speculative_decoding, **(eng_kw or {}))
        self.engine = self._stack.enter_context(engine)
        preface = ([{'role':'system','content':sp}] if sp else []) + self.mk_msgs(messages)
        if sampler_config is None and any(x is not None for x in (temp,top_k,top_p,seed)):
            sampler_config = SamplerConfig(temperature=temp, top_k=top_k, top_p=top_p, seed=seed)
        cvk = dict(sampler_config=sampler_config, max_output_tokens=max_output_tokens, **(conv_kw or {}))
        if think: cvk['extra_context'] = {**cvk.get('extra_context',{}), 'enable_thinking': True}
        if filter_think: cvk['filter_channel_content_from_kv_cache'] = True
        self.conv = self._stack.enter_context(engine.create_conversation(messages=preface or None,
            tools=list(L(tools)) or None, tool_event_handler=ChatToolHandler(self), **cvk))
        self.ctx_limit = ifnone(ctx_limit, engine.n_ctx()) if hasattr(engine,'n_ctx') else ctx_limit
        self._setup(model=model, sp=sp, messages=None, tools=tools, approve=approve,
                    tool_max_len=tool_max_len, max_steps=max_steps, cbs=cbs, default_cbs=default_cbs)
        self.hist = mk_msgs(messages)   # keep litert Message history (preface already seeded the conv)
    # token_count (property), count_tokens, cancel, render, _send, _stream : move verbatim from old core.Chat
    def _oneshot(self, prompt, sp):
        with self.engine.create_conversation(messages=[{'role':'system','content':sp}] if sp else None) as conv:
            return resp_text(conv.send_message(prompt))
    def _structured_call(self, prompt, schema, sp):
        pre = [{'role':'system','content':sp}] if sp else None
        with self.engine.create_conversation(messages=pre, tools=[schema], automatic_tool_calling=False) as conv:
            r = conv.send_message(prompt)
        if not (tcs := r.get('tool_calls')): raise ValueError(f"model did not call the tool; reply: {resp_text(r)[:200]!r}")
        return tcs[0].get('function', {}).get('arguments', {})
    def close(self):
        if getattr(self, '_stack', None) is not None: self._stack.close(); self._stack = None
```
(Note `ctx_limit` handling: litert exposes it via engine; keep whatever the old `core.Chat` used for `self.ctx_limit`/`self.conv.token_count`.) Delete the copied `classify/structured/check/grades` cells — inherited from `core.Chat`. Update `__all__` to `LitertChat, mk_content, mk_msg, mk_msgs, get_model, bench, ToolReminderCallback, HistoryCallback, UsageCallback, ChatToolHandler` + litert defaults.

- [ ] **Step 4: Retarget litert tests + add dispatch test**

Change litert test cells that used `Chat(...)` → `LitertChat(...)` (or `core.Chat('…litertlm')`). Add:
```python
from fastcore.test import test_eq
import rishi.core, rishi.litert
test_eq(rishi.core.get_runtime('litert'), rishi.litert.LitertChat)
from unittest.mock import patch as mock_patch
with mock_patch.object(rishi.litert.LitertChat, '__init__', return_value=None):
    assert isinstance(rishi.core.Chat(), rishi.litert.LitertChat)
    assert rishi.core.Chat('litert-community/gemma-4-E2B-it-litert-lm').runtime == 'litert'
```

- [ ] **Step 5: Export + test**

Export, then `nbdev_test` on `nbs/02_litert.ipynb`. Expected PASS (model cells `#| eval:false`).

- [ ] **Step 6: Checkpoint (human commits)**

`git add nbs/02_litert.ipynb rishi/litert.py && git commit -m "litert: LitertChat(core.Chat) over shared hooks"`

---

## Task 3 — `llama`: `Chat` → `LlamaChat(core.Chat)`  ⟂ (parallel with Task 2)

**Depends on:** Task 1. **Files:** Modify `nbs/01_llama.ipynb` → `rishi/llama.py`.
Identical to v1 Task 3 — reproduced here so this task is self-contained.

- [ ] **Step 1: Rename class + bind hook attrs**
```python
class LlamaChat(core.Chat):
    "Sync chat over a local llama.cpp model."
    _runtime = 'llama'
    _dflt_cbs = [UsageCallback, ToolReminderCallback]   # llama's own callback classes
    mk_content, mk_msg, mk_msgs = staticmethod(mk_content), staticmethod(mk_msg), staticmethod(mk_msgs)
    # create_engine: keep existing classmethod
```

- [ ] **Step 2: Rework `__init__` to the unified signature + `_setup`** (keep engine-building body; replace bookkeeping tail):
```python
    def __init__(self, model=None, *, runtime=None, model_path=None, engine=None,
                 quant='Q4_K_M', n_ctx=8192, n_gpu_layers=0, mmproj=None, eng_kw=None,
                 sp='', messages=None, tools=None, ctx_limit=None, approve=None, tool_max_len=None,
                 max_steps=10, think=None, temp=None, top_k=None, top_p=None, seed=None,
                 max_output_tokens=None, comp_kw=None, cbs=None, default_cbs=True):
        model = core.split_runtime(model)[1]
        model_id = None if model is None or core._is_path(model) else model
        model_path = model_path or (model if model and core._is_path(model) else None)
        self._own_engine = engine is None
        if engine is None:
            engine = self.create_engine(model_id or qwen3_17b, model_path, quant, n_ctx=n_ctx,
                                        n_gpu_layers=n_gpu_layers, mmproj=mmproj, **(eng_kw or {}))
        self.engine = engine
        self.toolspecs = [mk_toolspec(t) for t in L(tools)]
        self.ns = mk_ns([t for t in L(tools) if callable(t)])
        self._samp = {k:v for k,v in dict(temperature=temp, top_k=top_k, top_p=top_p, seed=seed).items() if v is not None}
        store_attr('think,max_output_tokens', self)
        self.ctx_limit, self.comp_kw, self._ctx_tokens = ifnone(ctx_limit, engine.n_ctx()), comp_kw or {}, 0
        self._setup(model=model, sp=sp, messages=messages, tools=tools, approve=approve,
                    tool_max_len=tool_max_len, max_steps=max_steps, cbs=cbs, default_cbs=default_cbs)
```

- [ ] **Step 3: Delete inherited duplicates; add `_oneshot`/`_structured_call`**

Remove from `01_llama`: `@patch def classify`, `@patch def check`, the `add_cb/... = core.Chat....` line, `class AsyncChat` (use `core.AsyncChat`), `__call__` (inherited). Replace `@patch def structured` with:
```python
    def _oneshot(self, prompt, sp):
        msgs = ([{'role':'system','content':sp}] if sp else []) + [{'role':'user','content':prompt}]
        return resp_text(norm_resp(self.engine.create_chat_completion(msgs, **self._samp)))
    def _structured_call(self, prompt, schema, sp):
        rf = {'type':'json_object','schema': get_schema(schema)['input_schema']}
        msgs = ([{'role':'system','content':sp}] if sp else []) + [{'role':'user','content':prompt}]
        return json.loads(resp_text(norm_resp(self.engine.create_chat_completion(msgs, response_format=rf, **self._samp))))
```
Keep `_msgs/_sys_msgs/_step/_run_tools/_stream_step/_send/_stream/token_count/count_tokens/close`. Update `__all__`: `Chat`→`LlamaChat`, drop `AsyncChat`.

- [ ] **Step 4: Retarget tests + dispatch + fix stray async cell**

Change `Chat(model_id=…)` → `LlamaChat(…)` in test cells; keep audio/`structured`/handler tests. Add the `get_runtime('llama')`/dispatch mock test (mirror Task 2 Step 4 with `LlamaChat`, `'Qwen/Qwen3-0.6B-GGUF'`, `'/models/x.gguf'`). Fix the stray `assert 'pong' …` cell (move it into the `#| eval:false` cell defining its `r`, or mark that cell `#| eval:false`).

- [ ] **Step 5: Export + test** `nbs/01_llama.ipynb` → PASS.

- [ ] **Step 6: Checkpoint (human commits)** `git add nbs/01_llama.ipynb rishi/llama.py && git commit -m "llama: LlamaChat(core.Chat) over shared hooks"`

---

## Task 4 — Delete `auto`; wire `__init__`; docs/settings; full `nbdev-prepare`

**Depends on:** Tasks 1–3. **Files:** delete `nbs/03_auto.ipynb`, `rishi/auto.py`; modify `rishi/__init__.py`, `nbs/index.ipynb`, `README.md`, `settings.ini`, regenerate `rishi/_modidx.py`.

- [ ] **Step 1: Delete `nbs/03_auto.ipynb` and `rishi/auto.py`.**

- [ ] **Step 2: Update `rishi/__init__.py`**
```python
__version__ = "0.0.3"
from .core import *

def __getattr__(name):
    if name in ('litert', 'llama'):
        import importlib
        return importlib.import_module(f'.{name}', __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

- [ ] **Step 3: Update `index.ipynb` + `README.md`** to the unified story (`from rishi import Chat; Chat('…gguf' | '…litertlm')`, `runtime=`, `chat.runtime`); drop alias/auto examples (keep `#| eval:false`).

- [ ] **Step 4: End-to-end model-free check**
```bash
./.venv/bin/python -c "
from rishi import Chat, AsyncChat, resp_text, mk_msg
from unittest.mock import patch as mock_patch
import rishi.llama, rishi.litert
with mock_patch.object(rishi.llama.LlamaChat,'__init__',return_value=None): assert isinstance(Chat('Qwen/Qwen3-0.6B-GGUF'), rishi.llama.LlamaChat)
with mock_patch.object(rishi.litert.LitertChat,'__init__',return_value=None): assert isinstance(Chat(), rishi.litert.LitertChat)
print('OK')"
```

- [ ] **Step 5: Full suite** — `nbdev-prepare` (or API stages: export, then `nbdev_test` on index/00_core/01_llama/02_litert). Confirm `_modidx` has no diff after re-export. `grep -rn "rishi.auto\|03_auto\|class Chat:" nbs rishi README.md` → only litert's hardware `backend=` remains.

- [ ] **Step 6: Checkpoint (human commits)** `git add -A && git commit -m "remove auto; unify top-level Chat; docs+settings"`

---

## Parallel execution note

After Task 1 is green, dispatch Tasks 2 and 3 as **two concurrent subagents** (independent files, both depend only on the frozen `core` contract). Merge order doesn't matter; run Task 4 once both land. If executing inline, do 2 then 3 sequentially.

## Self-Review

- **Spec coverage:** dispatch/registry → T1; base+shared classify/structured/check → T1; hook interface → T1 (defined) + T2/T3 (implemented); AsyncChat/shims → T1; litert backend → T2; llama backend → T3; delete auto + top-level surface → T4; testing → every task. Covered.
- **Placeholders:** `...` markers (`print_hist`, litert `_send/_stream/token_count/count_tokens/render/cancel`, `create_engine`) are explicit *move-verbatim-from-old-core* instructions naming existing symbols — bodies exist in today's `rishi/core.py`. No unspecified logic.
- **Type consistency:** hook names (`_setup, _oneshot, _structured_call, mk_msgs, token_count, count_tokens, close, _runtime, _dflt_cbs`) and resolver names (`resolve_runtime/get_runtime/_is_path/_mk_obj/split_runtime`) are identical across T1–T3.

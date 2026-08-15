# Design: Unify `Chat` across backends over one shared `core`

Date: 2026-07-30
Status: approved (pending spec review)

## Goal

One seamless `Chat` for devs, DRY internals. Today the litert and llama.cpp backends
duplicate the entire turn API (`__init__/_send/_stream/__call__/classify/structured/check`),
`rishi.litert` is a no-op alias of `rishi.core`, `rishi.auto` bolts a factory on top, and
`backend=` is overloaded (litert hardware `Backend.GPU()` vs auto's software selector). We
collapse this to a shared `rishi.core` layer + two thin backend subclasses, with backend
selection built into `Chat` itself.

Non-goals: changing model formats, adding runtimes, or touching litert/llama inference
semantics. This is a layout + de-duplication refactor.

## Constraints

- Only `rishi.core` is released. Devs use `from rishi import *` → `Chat()`, `resp_text`,
  `display_stream`, etc. `rishi.llama`/`rishi.litert`/`rishi.auto` are unreleased (this
  branch), so they can be redesigned freely.
- Must preserve: `from rishi import *` exposing `Chat`/`AsyncChat` + the agnostic helpers;
  a bare `Chat()` still means litert with its default model.
- fastai style: succinct/functional, `store_attr`/`patch`/`delegates`/`first`/`L`, one-line
  docstrings, no redundant comments.
- nbdev project: notebooks are source; run `nbdev-prepare` (hyphen) after changes.

## Decisions (locked)

1. **Approach A** — shared `core.Chat` base + `LitertChat`/`LlamaChat` subclasses; `Chat`
   dispatches via `__new__` so `from rishi import Chat; Chat('…gguf')` returns a `LlamaChat`
   that `isinstance`-checks as `Chat` and reports `chat.runtime`.
2. **Shared layer stays named `core`.** The litert *implementation* moves out of `core` into
   `rishi.litert`. `rishi.auto` and the `rishi.litert` alias are deleted.
3. **Selector is `runtime=`** (`'litert'`/`'llama'`), never `backend`. litert's hardware
   `backend=Backend.GPU()` passes through `**kw` untouched. The `'llama/…'` name prefix still
   forces a runtime.
4. **`mk_msg`/`mk_content`/`mk_msgs` stay top-level as lazy shims.** The real encoders live in
   the backend modules (litert `Content` vs OpenAI dicts); `core` keeps thin top-level shims
   that forward to the default runtime, so `from rishi import mk_msg`/`from rishi import *`
   keep working unchanged (non-breaking). No release-visible API change.

## Module & notebook layout

| notebook | module | holds |
|---|---|---|
| `00_core.ipynb` | `rishi.core` | agnostic layer **+** `Chat` (dispatching `__new__`), `AsyncChat`, runtime resolution + registry, top-level `mk_msg`/`mk_content`/`mk_msgs` shims |
| `01_llama.ipynb` | `rishi.llama` | `LlamaChat(core.Chat)` + llama encode/engine + audio patches + read_audio + llama defaults (number unchanged) |
| `02_litert.ipynb` | `rishi.litert` | repurposed alias → real backend: `LitertChat(core.Chat)` + litert `mk_msg`/`mk_content`/`get_model`/`bench` + litert defaults |
| *(deleted)* | ~~`rishi.auto`~~ (`03_auto.ipynb`) | subsumed by `core.Chat.__new__` |

`rishi/__init__.py`: `from .core import *`; lazy `__getattr__` for `litert`/`llama` submodules.
No import cycle: `core` imports no backend at load time (only lazily inside `__new__`);
backends import from `core`.

## Dispatch (in `core`)

Pure string logic + a string-only registry (no eager imports), renamed from today's
`*_backend`:

```python
runtimes = {'litert': ('rishi.litert','LitertChat'), 'llama': ('rishi.llama','LlamaChat')}
dflt_runtime = 'litert'
_pats = {'litert': ('.litertlm','litertlm','litert-community','litert-lm'), 'llama': ('.gguf','gguf')}

def split_runtime(model):   "('runtime/model') -> (runtime, model); prefix must name a known runtime."
def infer_runtime(model):   "guess from id/path shape (.litertlm vs .gguf), else None."
def resolve_runtime(model=None, runtime=None, model_path=None):
    "explicit runtime, then prefix, then shape, then dflt_runtime; raise (actionable) if ambiguous."
def get_runtime(nm):        "import runtimes[nm] module and return its Chat subclass; hint pip extra on ImportError."
def _is_path(model):        "does model name a local .gguf/.litertlm file (or existing path)?"
```

```python
class Chat:
    def __new__(cls, model=None, *, runtime=None, model_path=None, **kw):
        if cls is not Chat: return super().__new__(cls)          # concrete subclass -> no dispatch
        nm, _ = resolve_runtime(model, runtime, model_path)
        return super().__new__(get_runtime(nm))                  # Python then calls subclass.__init__
```

Top-level encoder shims (in `core`, in `__all__`) forward to the default runtime so
`from rishi import mk_msg` stays working:

```python
def _runtime_mod(nm): return import_module(runtimes[nm][0])
def mk_content(o):                 return _runtime_mod(dflt_runtime).mk_content(o)
def mk_msg(content, role='user'):  return _runtime_mod(dflt_runtime).mk_msg(content, role)
def mk_msgs(msgs):                 return _runtime_mod(dflt_runtime).mk_msgs(msgs)
```

`__new__`/`__init__` arg-threading wart: Python calls the subclass `__init__` with the
*original* args, so the shared init tail re-runs `split_runtime(model)` (idempotent — strips a
`'llama/…'` prefix) and routes `model` → `model_id` vs `model_path` via `_is_path`. Subclass
`__init__` accepts and ignores a `runtime=None` param.

Behavior: bare `Chat()` → `LitertChat` default model (unchanged). `Chat('Qwen/…-GGUF')` →
`LlamaChat`. `Chat('/m.gguf')` → `LlamaChat` with `model_path`. `Chat(x, runtime='litert')`
forces. `Chat('…litertlm', backend=Backend.GPU())` now works (hardware `backend` passes
through).

## Hook boundary

Shared surrounds the turn; only turn execution + encoding are hooks, because litert's engine
runs the tool loop internally while llama runs a Python-side loop.

**`core.Chat` (concrete, shared):** `__new__` · `add_cb/add_cbs/remove_cb/remove_cbs` ·
`print_hist` · `pct_full` · `__call__` (stream dispatch + per-turn cbs) · `classify` ·
`structured` · `check` · `grades` · `run_py` · `_mk_obj` · `runtime` property · `__del__`→`close`.
Shared init tail `_setup(model, sp, messages, tools, approve, tool_max_len, max_steps, cbs,
default_cbs)`: strips prefix, `store_attr`s shared fields, builds `hist` via `self.mk_msgs`,
registers callbacks.

**Subclass hooks (litert + llama each implement):**
- `__init__` — build engine, then `self._setup(...)`
- `mk_content` / `mk_msg` / `mk_msgs` — encode (module-level funcs in each backend, bound onto
  the subclass as `staticmethod`s so `self.mk_msgs(...)` and `rishi.llama.mk_msgs(...)` both work)
- `_send(msg, max_output_tokens)` — full turn incl. tool loop, returns `Resp`
- `_stream(msg, max_output_tokens, cbs)` — streamed turn (feeds shared `StreamFormatter`)
- `token_count` (property) · `count_tokens(text)`
- `_oneshot(prompt, sp) -> str` — stateless one-shot completion (for classify/check/grades)
- `_structured_call(prompt, schema, sp) -> dict` — backend structured mechanism
- `close()`

**R3 payoff — written once in `core`:**

```python
def structured(self, prompt, schema, sp='…'):
    return _mk_obj(schema, self._structured_call(prompt, schema, sp))
def classify(self, text, labels, sp='…'):
    out = self._oneshot(f"{text}\n\nChoose exactly one label from: {', '.join(labels)}.", sp).lower()
    return first(labels, lambda l: l.lower() in out) or out.strip()
def check(self, question, expected, grade_fn=matches_, llm_judge=False, judge=None, tag='answer', sp=qa_sp_):
    a = extract_fence(self._oneshot(question, sp), tag)
    ok = (judge or self).grades(question, expected, a) if (llm_judge or judge) else grade_fn(a, expected)
    return AttrDict(question=question, expected=expected, answer=a, ok=ok)
```

- llama `_structured_call`: grammar-constrained `response_format={'type':'json_object','schema':…}`.
- litert `_structured_call`: forced tool call (`create_conversation(tools=[schema],
  automatic_tool_calling=False)`), returns `tool_calls[0].function.arguments`.
- Both gain `_mk_obj`'s nested-dataclass rebuild; the previous `structured` divergence is gone.

## AsyncChat / streaming / errors

- **One `core.AsyncChat(GetAttr)`** wrapping any `Chat`
  (`chat = model if hasattr(model,'_send') else Chat(model, runtime=…, **kw)`), blocking calls
  in a worker thread. Replaces the three current AsyncChats.
- **Streaming**: `StreamFormatter`/`display_stream` stay shared in `core`; each `_stream` feeds
  it from its own chunk source (litert `send_message_async`; llama `StreamSplit`).
- **Errors**: `resolve_runtime` keeps the actionable messages; `get_runtime` keeps the
  `pip install 'rishi[llama]'` hint. Relocated from `auto`, unchanged.

## Testing (model-free where it counts)

- **core**: `__new__` dispatch via `mock_patch` on subclass `__init__` (as `auto` already
  tests); `resolve_runtime`/`infer_runtime`/`split_runtime` (moved from auto); `classify`/
  `structured`/`check`/`_mk_obj` over a tiny fake exposing `_oneshot`/`_structured_call`;
  `AsyncChat` over a `_FakeChat`; callback add/remove.
- **litert**: `LitertChat` hooks via fakes where possible; `#| eval:false` model cells for the
  real path.
- **llama**: retarget existing tests to `LlamaChat`; keep the audio + `structured` +
  handler-routing tests already written.

## nbdev migration mechanics (sequence carefully, gate on `nbdev-prepare`)

1. `00_core`: remove litert `Chat`/`create_engine`/`mk_msg`/`mk_content`/`get_model`/`bench`;
   add `Chat` base + dispatch + registry + `AsyncChat` + top-level encoder shims; update
   `__all__` (add `Chat`,`AsyncChat`; keep `mk_msg`,`mk_content`,`mk_msgs` as shims).
2. `01_llama` (number unchanged): `LlamaChat(core.Chat)` implementing the hooks; import shared
   names from `core`; keep audio/`structured`/handler tests.
3. `02_litert` (repurpose the alias): `LitertChat(core.Chat)` + litert encode/engine/defaults/
   bench; `default_exp litert`.
4. Delete `03_auto` (and its `rishi/auto.py`).
5. `rishi/__init__.py`: `from .core import *`; keep lazy submodules `litert`,`llama`.
6. Update `index.ipynb`, `settings.ini` (`nbs`/lib refs), `_modidx`, README cross-links.
7. `nbdev-prepare` clean at each step.

## Risks

- `__new__` dispatch is mildly magic; mitigated by the `cls is not Chat` guard + idempotent
  prefix strip, and covered by dispatch tests.
- Large diff across notebooks + `_modidx`/`index`. Sequenced above; each step ends green. No
  notebook renumber (`01_llama` stays; `02_litert` repurposed; only `03_auto` deleted).
- Top-level `mk_msg`/`mk_content`/`mk_msgs` shims keep `from rishi import …` non-breaking; cost
  is a lazy import of the default runtime on first use.
- Per standing user rule, **no git operations** are performed by the assistant; the human
  commits.

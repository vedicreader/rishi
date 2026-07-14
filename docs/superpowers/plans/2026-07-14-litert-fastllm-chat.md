# litert fastllm-style Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `litert_lm`'s local Gemma engine a fastllm-style `Chat`: callable turn interface, Python-visible history, an ordered `ChatCallback` system, sync streaming display, and `token_count`-based usage tracking so callers know when to compress.

**Architecture:** One nbdev module (`nbs/00_core.ipynb` → `rishi/core.py`). Thin message helpers over litert's `Message`/`Contents`; a `UsageStats` dataclass fed by `conv.token_count` diffs; a sync `ChatCallback(GetAttr)` framework with a `run_cbs` dispatcher; a `StreamFormatter` adapted to litert's chunk shape; a `ChatToolHandler(ToolEventHandler)` that bridges litert's in-engine tool loop to callbacks + history; and a `Chat` class orchestrating turns. Tool calling, message construction, and streaming are litert primitives we reuse, not reimplement.

**Tech Stack:** Python 3.13, nbdev, fastcore (`GetAttr`, `store_attr`, `patch`, `L`), `litert_lm` (Engine/Conversation/Message/Contents/ToolEventHandler), `huggingface_hub`. Code execution during verification via `safepyrun` / `clikernel`.

## Global Constraints

- nbdev workflow: all code lives in `nbs/00_core.ipynb` cells; `#| export` marks exported code; run `uv run nbdev-prepare` (hyphen, never underscore) after changes; check `nbs/index.ipynb` for stale references before finishing.
- fastcore idioms required: `store_attr`, `patch`, `GetAttr`, `L`. Short one-line docstrings; no redundant comments.
- Sync only — no asyncio (litert is synchronous).
- Do NOT edit `MANIFEST.in` for build config; this repo uses nbdev/setuptools via `pyproject.toml`.
- Heavy engine/inference test cells MUST be marked `#| eval: false` so `nbdev-prepare` stays fast; verify them manually (steps provided) with `gemma4_e2b`.
- Package installs via `uv add`; run tools via `uv run`.

## File Structure

- Modify: `nbs/00_core.ipynb` — the only source file. New `#| export` cells added in dependency order (helpers → UsageStats → callback framework → StreamFormatter → ToolReminderCallback → ChatToolHandler → Chat), each followed by test cell(s).
- Generated: `rishi/core.py` — produced by `nbdev-prepare`; never edited by hand.
- Reference only (installed deps, do not modify): `litert_lm/{conversation,interfaces,_messages,engine,tools}.py`, `fastllm/chat.py`, `safepyrun/core.py`.

## Deviations from spec (intentional, more faithful to fastllm)

- Usage accumulation and history appends happen **inline in `Chat`** / `ChatToolHandler`, not as `UsageCB`/`HistoryCB` callbacks (mirrors fastllm's inline `_track` and `hist.append`).
- Output tokens computed via `engine.tokenize(resp_text)`; input = `token_count` delta − output. The prefill-boundary read is not required.
- Only `ToolReminderCallback` is ported as a concrete built-in (the rest of fastllm's built-ins are provider/wire-specific). The full callback *architecture* is ported.

---

### Task 1: Imports + message helpers (`mk_content`, `mk_msg`, `mk_msgs`)

**Files:**
- Modify: `nbs/00_core.ipynb` (imports cell `da4d26dd`; new export + test cells)

**Interfaces:**
- Produces:
  - `mk_content(o) -> Content` — `str`→`Text`, `bytes`→`ImageBytes`, `Path`→`ImageFile`/`AudioFile` by mime, `Content`→unchanged.
  - `mk_msg(content, role='user') -> Message` — accepts `str`/`bytes`/`list`/`Message`/dict; lists build multimodal `Contents`.
  - `mk_msgs(msgs) -> list[dict]` — normalize a list to litert message dicts via `normalize_message`.

- [ ] **Step 1: Extend the imports cell**

Replace the body of the existing imports cell (`#| export`, id `da4d26dd`) with:

```python
#| export
import json, re
from html import escape
from mimetypes import guess_type
from litert_lm import (Engine, Backend, Conversation, Session, Message, Contents,
                       Content, Role, ToolCall, ToolEventHandler, set_min_log_severity)
from litert_lm._messages import (Text, ImageBytes, ImageFile, AudioBytes, AudioFile,
                                 ToolResponse, normalize_message)
from huggingface_hub import hf_hub_download
from fastcore.all import Path, store_attr, patch, L, GetAttr, ifnone
```

- [ ] **Step 2: Add failing test cell** (place after the helpers cell you create next; run now to see it fail)

```python
#| hide
m = mk_msg("hello")
assert m.to_json() == {"role": "user", "content": [{"type": "text", "text": "hello"}]}
assert mk_msg("hi", role="model").to_json()["role"] == "model"
ms = mk_msgs(["a", mk_msg("b", role="model")])
assert [x["role"] for x in ms] == ["user", "model"]
assert isinstance(mk_content("x"), Text)
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run nbdev-prepare`
Expected: FAIL — `NameError: name 'mk_msg' is not defined`.

- [ ] **Step 4: Add the export cell (before the test cell)**

```python
#| export
def mk_content(o):
    "Convert `o` to a litert `Content`."
    if isinstance(o, Content): return o
    if isinstance(o, str): return Text(o)
    if isinstance(o, bytes): return ImageBytes(o)
    if isinstance(o, Path):
        mime = guess_type(str(o))[0] or ''
        return AudioFile(str(o)) if mime.startswith('audio/') else ImageFile(str(o))
    raise TypeError(f"Unsupported content type: {type(o)}")

def mk_msg(content, role='user'):
    "Create a litert `Message` from str/bytes/list/dict/Message."
    if content is None: return None
    if isinstance(content, Message): return content
    if isinstance(content, dict): return Message(Role(content['role']), Contents.of(content['content']))
    parts = [mk_content(o) for o in content] if isinstance(content, list) else [mk_content(content)]
    return Message(Role(role), Contents(parts))

def mk_msgs(msgs):
    "Normalize a list of messages to litert message dicts."
    if not msgs: return []
    if not isinstance(msgs, list): msgs = [msgs]
    return [normalize_message(mk_msg(m) if not isinstance(m, (Message, dict)) else m) for m in msgs]
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run nbdev-prepare`
Expected: PASS — no assertion errors; `rishi/core.py` regenerated.

- [ ] **Step 6: Commit**

```bash
git add nbs/00_core.ipynb rishi/core.py
git commit -m "feat: mk_content/mk_msg/mk_msgs over litert message types"
```

---

### Task 2: `UsageStats`

**Files:**
- Modify: `nbs/00_core.ipynb` (new export + test cells)

**Interfaces:**
- Consumes: none.
- Produces: `UsageStats(prompt_tokens=0, completion_tokens=0, total_tokens=0, n=0)` with `__add__`, `__radd__`, `__repr__`, `fmt() -> str`.

- [ ] **Step 1: Add failing test cell**

```python
#| hide
a = UsageStats(prompt_tokens=10, completion_tokens=5, total_tokens=15, n=1)
b = UsageStats(prompt_tokens=3, completion_tokens=2, total_tokens=20, n=1)
c = a + b
assert (c.prompt_tokens, c.completion_tokens, c.n) == (13, 7, 2)
assert "in=13" in repr(c) and "out=7" in repr(c)
assert (a + None).prompt_tokens == 10
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run nbdev-prepare`
Expected: FAIL — `NameError: name 'UsageStats' is not defined`.

- [ ] **Step 3: Add the export cell (before the test cell)**

```python
#| export
class UsageStats:
    "Token usage for a chat turn, fed by `conv.token_count` diffs."
    def __init__(self, prompt_tokens=0, completion_tokens=0, total_tokens=0, n=0): store_attr()

    def __add__(self, other):
        if other is None: return self
        return UsageStats(*[getattr(self, k) + getattr(other, k)
            for k in ('prompt_tokens', 'completion_tokens', 'total_tokens', 'n')])
    def __radd__(self, other): return self if other in (None, 0) else self.__add__(other)

    def __repr__(self):
        return ' | '.join([f"total={self.total_tokens:,}", f"in={self.prompt_tokens:,}",
                           f"out={self.completion_tokens:,}", f"turns={self.n}"])

    def fmt(self):
        "Markdown `<details>` token block."
        if not self.total_tokens: return ''
        return f"\n\n<details><summary>{self.total_tokens:,} tokens</summary>\n\n`{self!r}`\n\n</details>\n"
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run nbdev-prepare`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nbs/00_core.ipynb rishi/core.py
git commit -m "feat: UsageStats token accounting"
```

---

### Task 3: Callback framework (`ChatCallback`, `run_cbs`)

**Files:**
- Modify: `nbs/00_core.ipynb` (new export + test cells)

**Interfaces:**
- Consumes: none.
- Produces:
  - `ChatCallback(GetAttr)` with class attrs `order=0, _default='chat', chat=None, run=True` and `__repr__`.
  - `run_cbs(chat, event)` — generator; iterates `chat.cbs.sorted('order')`, calls `cb.<event>()` when defined+enabled, and `yield from` any generator it returns.

- [ ] **Step 1: Add failing test cell**

```python
#| hide
class _Dummy: pass
class _A(ChatCallback):
    order = 20
    def before_send(self): self.chat.log.append('A')
class _B(ChatCallback):
    order = 10
    def before_send(self):
        self.chat.log.append('B')
        yield {'text': 'from-B'}
d = _Dummy(); d.log = []
a, b = _A(), _B(); a.chat = d; b.chat = d
d.cbs = L(a, b)
out = list(run_cbs(d, 'before_send'))
assert d.log == ['B', 'A']          # sorted by order
assert out == [{'text': 'from-B'}]  # generator yields forwarded
assert repr(a) == '_A'
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run nbdev-prepare`
Expected: FAIL — `NameError: name 'ChatCallback' is not defined`.

- [ ] **Step 3: Add the export cell (before the test cell)**

```python
#| export
class ChatCallback(GetAttr):
    "Base chat callback; reads chat state via `GetAttr` (`self.turn_msg` → `chat.turn_msg`)."
    order, _default, chat, run = 0, 'chat', None, True
    def __repr__(self): return type(self).__name__

def run_cbs(chat, event):
    "Dispatch `event` to enabled callbacks in `order`; forward any yielded stream items."
    for cb in chat.cbs.sorted('order'):
        if cb.run and hasattr(cb, event):
            r = getattr(cb, event)()
            if r is not None: yield from r
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run nbdev-prepare`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nbs/00_core.ipynb rishi/core.py
git commit -m "feat: ChatCallback framework + run_cbs dispatcher"
```

---

### Task 4: `StreamFormatter` + tool-display helpers

**Files:**
- Modify: `nbs/00_core.ipynb` (new export + test cells)

**Interfaces:**
- Consumes: none.
- Produces:
  - `_resp_text(resp) -> str` — join text parts of a litert response/chunk dict.
  - `_tc_summary(name, args, result=None) -> str` — `<code>` one-liner.
  - `mk_tr_details(name, args, result, mx=2000) -> str` — `<details>` JSON block.
  - `StreamFormatter(mx=2000)` with `format_item(o) -> str` and `format_stream(rs)` generator.
  - `display_stream(rs, **kwargs) -> StreamFormatter` — IPython markdown display.

- [ ] **Step 1: Add failing test cell**

```python
#| hide
fmt = StreamFormatter()
assert _resp_text({"role": "assistant", "content": [{"type": "text", "text": "hi"}]}) == "hi"
assert fmt.format_item({"content": [{"type": "text", "text": "hel"}]}) == "hel"
assert fmt.format_item({"content": [{"type": "text", "text": "lo"}]}) == "lo"
assert fmt.outp == "hello"
tc = {"content": [{"type": "tool_call", "name": "add", "arguments": {"a": 1}}]}
assert "add" in fmt.format_item(tc)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run nbdev-prepare`
Expected: FAIL — `NameError: name 'StreamFormatter' is not defined`.

- [ ] **Step 3: Add the export cell (before the test cell)**

```python
#| export
def _resp_text(resp):
    "Join text parts of a litert response/chunk dict."
    c = resp.get('content', []) if isinstance(resp, dict) else ''
    if isinstance(c, str): return c
    return ''.join(p.get('text', '') for p in c if isinstance(p, dict) and p.get('type') == 'text')

def _tc_summary(name, args, result=None):
    "One-line `<code>` summary of a tool call."
    params = ', '.join(f"{k}={v!r}" for k, v in (args or {}).items())
    res = f" → {result}" if result is not None else ''
    return '<code>' + escape(f"{name}({params}){res}") + '</code>'

def mk_tr_details(name, args, result, mx=2000):
    "`<details>` JSON block for a completed tool call."
    body = json.dumps({'call': {'function': name, 'arguments': args}, 'result': str(result)[:mx]}, indent=2)
    return f"\n\n<details><summary>{_tc_summary(name, args, result)}</summary>\n\n```json\n{body}\n```\n\n</details>\n\n"

class StreamFormatter:
    "Format a litert response stream to markdown."
    def __init__(self, mx=2000): self.outp = ''; store_attr()
    def format_item(self, o):
        "Format one litert chunk dict."
        res = _resp_text(o)
        for p in (o.get('content', []) if isinstance(o, dict) else []):
            if isinstance(p, dict) and p.get('type') == 'tool_call':
                res += f"\n- ⏳ {_tc_summary(p.get('name', ''), p.get('arguments', {}))}\n"
        self.outp += res
        return res
    def format_stream(self, rs):
        "Yield markdown strings for each chunk."
        for o in rs: yield self.format_item(o)

def display_stream(rs, **kwargs):
    "Markdown-display a litert stream via IPython."
    from IPython.display import display, Markdown
    fmt, md = StreamFormatter(**kwargs), ''
    h = display(Markdown(' '), display_id=True)
    for o in fmt.format_stream(rs):
        md += o
        if md: h.update(Markdown(md))
    return fmt
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run nbdev-prepare`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nbs/00_core.ipynb rishi/core.py
git commit -m "feat: StreamFormatter + tool-call display helpers"
```

---

### Task 5: `ToolReminderCallback`

**Files:**
- Modify: `nbs/00_core.ipynb` (new export + test cells)

**Interfaces:**
- Consumes: `ChatCallback`, `Text` (litert).
- Produces: `_tool_reminder` (str), `ToolReminderCallback(ChatCallback)` (`order=30`, `before_send` appends reminder to `chat.turn_msg` contents when `chat.tools`).

- [ ] **Step 1: Add failing test cell**

```python
#| hide
class _C:
    def __init__(self): self.tools = [1]; self.turn_msg = mk_msg("hi")
c = _C(); cb = ToolReminderCallback(); cb.chat = c
list(run_cbs_stub := iter([cb.before_send()])) if False else cb.before_send()
assert any('summarise' in (p.text or '') for p in c.turn_msg.contents.contents)
# no tools → no injection
c2 = _C(); c2.tools = []; cb2 = ToolReminderCallback(); cb2.chat = c2
cb2.before_send()
assert len(c2.turn_msg.contents.contents) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run nbdev-prepare`
Expected: FAIL — `NameError: name 'ToolReminderCallback' is not defined`.

- [ ] **Step 3: Add the export cell (before the test cell)**

```python
#| export
_tool_reminder = ("\n<system-reminder>After every tool call result, briefly summarise in prose "
                  "what you found before continuing or calling another tool.</system-reminder>")

class ToolReminderCallback(ChatCallback):
    "Inject a tool-summary reminder into the outgoing message when tools are registered."
    order = 30
    def __init__(self, tool_reminder=_tool_reminder): store_attr()
    def before_send(self):
        if self.chat.tools and self.chat.turn_msg is not None:
            self.chat.turn_msg.contents.contents.append(Text(self.tool_reminder))
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run nbdev-prepare`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nbs/00_core.ipynb rishi/core.py
git commit -m "feat: ToolReminderCallback"
```

---

### Task 6: `ChatToolHandler`

**Files:**
- Modify: `nbs/00_core.ipynb` (new export + test cells)

**Interfaces:**
- Consumes: `ToolEventHandler` (litert), `run_cbs`.
- Produces: `ChatToolHandler(ToolEventHandler)` — `__init__(self, chat)`; `approve_tool_call(tc) -> bool` (sets `chat.turn_tc`, appends assistant tool-call msg to `chat.hist`, fires `before_tool_calls`, returns `True`); `process_tool_response(resp) -> resp` (sets `chat.turn_tool_result`, appends tool msg to `chat.hist`, fires `after_tool_calls`, returns `resp` unchanged).

- [ ] **Step 1: Add failing test cell**

```python
#| hide
class _Chat:
    def __init__(self): self.hist = []; self.cbs = L(); self.events = []
ch = _Chat()
h = ChatToolHandler(ch)
tc = {"function": {"name": "add", "arguments": {"a": 1, "b": 2}}}
assert h.approve_tool_call(tc) is True
assert ch.turn_tc == tc
assert ch.hist[-1]["role"] in ("assistant", "model")
out = h.process_tool_response({"result": 3})
assert out == {"result": 3}                 # returned unchanged
assert ch.hist[-1]["role"] == "tool"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run nbdev-prepare`
Expected: FAIL — `NameError: name 'ChatToolHandler' is not defined`.

- [ ] **Step 3: Add the export cell (before the test cell)**

```python
#| export
class ChatToolHandler(ToolEventHandler):
    "Bridge litert's in-engine tool loop to Chat callbacks and history."
    def __init__(self, chat): self.chat = chat
    def approve_tool_call(self, tool_call):
        self.chat.turn_tc = tool_call
        fn = tool_call.get('function', {})
        self.chat.hist.append({'role': 'model', 'tool_calls': [tool_call]})
        for _ in run_cbs(self.chat, 'before_tool_calls'): pass
        return True
    def process_tool_response(self, tool_response):
        self.chat.turn_tool_result = tool_response
        self.chat.hist.append({'role': 'tool', 'content': [{'type': 'tool_response',
            'name': self.chat.turn_tc.get('function', {}).get('name', ''), 'response': tool_response}]})
        for _ in run_cbs(self.chat, 'after_tool_calls'): pass
        return tool_response
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run nbdev-prepare`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nbs/00_core.ipynb rishi/core.py
git commit -m "feat: ChatToolHandler bridging litert tool loop to callbacks"
```

---

### Task 7: `Chat` — init, non-stream turn, usage, `print_hist`

**Files:**
- Modify: `nbs/00_core.ipynb` (gemma-constants cell `f717f851d413e77`; rewrite the existing `Chat`/`get_model` cell `40fb869354982708`; new `#| eval: false` manual-test cell)

**Interfaces:**
- Consumes: `mk_msg`, `mk_msgs`, `UsageStats`, `run_cbs`, `ChatToolHandler`, `ToolReminderCallback`, `_resp_text`, `Engine`, `Backend`, `hf_hub_download`.
- Produces:
  - `get_model(model_id, model_path) -> str` (unchanged).
  - `_dflt_cbs = [ToolReminderCallback]`.
  - `Chat(model_id=gemma4_e2b, model_path=None, backend=Backend.CPU, multimodal=True, sp='', messages=None, tools=None, ctx_limit=4096, cbs=None, default_cbs=True, **kwargs)`.
  - `Chat.add_cb(cb)`, `Chat.add_cbs(cbs)`, `Chat.__call__(msg=None, stream=False, max_output_tokens=None)`, `Chat.token_count` (property), `Chat.pct_full` (property), `Chat.print_hist()`, `Chat._track(tc0)`.

- [ ] **Step 1: Export the gemma constants cell**

Prepend `#| export` to cell `f717f851d413e77` so the defaults are importable:

```python
#| export
gemma4_e4b = 'litert-community/gemma-4-E4B-it-litert-lm'
gemma4_e2b = 'litert-community/gemma-4-E2B-it-litert-lm'
gemma4_12b = 'litert-community/gemma-4-12B-it-litert-lm'
```

- [ ] **Step 2: Rewrite the `Chat`/`get_model` cell** (`40fb869354982708`)

```python
#| export
def get_model(model_id, model_path=None):
    "Return a local model path, downloading from HF on first use."
    if model_path and Path(model_path).exists(): return model_path
    return hf_hub_download(model_id, repo_type='model')

_dflt_cbs = [ToolReminderCallback]

class Chat:
    "fastllm-style sync chat over a local litert_lm Gemma engine."
    def __init__(self, model_id=gemma4_e2b, model_path=None, backend=Backend.CPU, multimodal=True,
                 sp='', messages=None, tools=None, ctx_limit=4096, cbs=None, default_cbs=True, **kwargs):
        assert model_id or model_path, "model_id or model_path must be provided"
        self.engine = Engine(get_model(model_id, model_path), backend=backend, multimodal=multimodal)
        self.tools = L(tools)
        self.hist = mk_msgs(messages)
        preface = ([{'role': 'system', 'content': sp}] if sp else []) + self.hist
        self.conv = self.engine.create_conversation(messages=preface or None, tools=list(self.tools) or None,
            tool_event_handler=ChatToolHandler(self), automatic_tool_calling=True)
        store_attr('ctx_limit,sp')
        self.use, self.cbs, self.turn_msg, self.turn_res = UsageStats(), L(), None, None
        if default_cbs: self.add_cbs(_dflt_cbs)
        self.add_cbs(cbs)

    def add_cb(self, cb):
        if isinstance(cb, type): cb = cb()
        cb.chat = self; self.cbs.append(cb); return self
    def add_cbs(self, cbs):
        L(cbs).map(self.add_cb); return self

    @property
    def token_count(self): return self.conv.token_count
    @property
    def pct_full(self): return self.conv.token_count / self.ctx_limit

    def _track(self, tc0):
        tc1 = self.conv.token_count
        out = len(self.engine.tokenize(_resp_text(self.turn_res)))
        self.use += UsageStats(prompt_tokens=max((tc1 - tc0) - out, 0), completion_tokens=out, total_tokens=tc1 - tc0, n=1)

    def __call__(self, msg=None, stream=False, max_output_tokens=None):
        "Run one chat turn; returns the litert response dict (or a stream generator)."
        self.use, self.turn_msg = UsageStats(), mk_msg(msg)
        if self.turn_msg is not None: self.hist.append(normalize_message(self.turn_msg))
        for _ in run_cbs(self, 'after_msgs'): pass
        for _ in run_cbs(self, 'before_send'): pass
        if stream: return self._stream(max_output_tokens)
        tc0 = self.conv.token_count
        self.turn_res = self.conv.send_message(self.turn_msg, max_output_tokens=max_output_tokens)
        self._track(tc0); self.hist.append(self.turn_res)
        for _ in run_cbs(self, 'after_response'): pass
        return self.turn_res

    def print_hist(self):
        "Print each message on its own line."
        for m in self.hist: print(f"{m.get('role','?')}: {_resp_text(m) or m}")
```

- [ ] **Step 3: Run pure gate**

Run: `uv run nbdev-prepare`
Expected: PASS (no engine cell executes yet; earlier pure tests still pass).

- [ ] **Step 4: Add a manual engine-test cell** (marked non-eval so `nbdev-prepare` skips it)

```python
#| eval: false
set_min_log_severity(2)
chat = Chat()
r = chat("Reply with exactly: pong")
assert 'pong' in _resp_text(r).lower()
assert chat.hist[-1] is r and chat.hist[0]['role'] == 'user'
assert chat.use.total_tokens > 0 and chat.token_count > 0
print(chat.use); chat.print_hist()
```

- [ ] **Step 5: Verify the engine turn manually**

Export first, then run the check through safepyrun (downloads `gemma4_e2b` on first run; CPU inference may take a while):

Run:
```bash
uv run nbdev-prepare
uv run python -c "from rishi.core import *; set_min_log_severity(2); c=Chat(); r=c('Reply with exactly: pong'); print(_resp_text(r)); print(c.use); assert c.use.total_tokens>0 and c.token_count>0"
```
Expected: prints a reply containing `pong`, then a `UsageStats` line like `total=… | in=… | out=… | turns=1`; no assertion error.

- [ ] **Step 6: Commit**

```bash
git add nbs/00_core.ipynb rishi/core.py
git commit -m "feat: Chat init + non-stream turn + usage + print_hist"
```

---

### Task 8: `Chat` streaming turn (`_stream`)

**Files:**
- Modify: `nbs/00_core.ipynb` (add `_stream` + `_merge_chunks`; new `#| eval: false` manual-test cell)

**Interfaces:**
- Consumes: `StreamFormatter`, `_resp_text`, `run_cbs`, `Chat._track`.
- Produces:
  - `_merge_chunks(chunks) -> dict` — reconstruct an assistant response dict from streamed chunks.
  - `Chat._stream(max_output_tokens)` — generator yielding markdown strings; on completion sets `turn_res`, tracks usage, appends to `hist`, fires `after_response`.

- [ ] **Step 1: Add a failing pure test cell for `_merge_chunks`**

```python
#| hide
merged = _merge_chunks([{"content": [{"type": "text", "text": "po"}]},
                        {"content": [{"type": "text", "text": "ng"}]}])
assert merged == {"role": "assistant", "content": [{"type": "text", "text": "pong"}]}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run nbdev-prepare`
Expected: FAIL — `NameError: name '_merge_chunks' is not defined`.

- [ ] **Step 3: Add the export cell (before the test cell)**

```python
#| export
def _merge_chunks(chunks):
    "Reconstruct an assistant response dict from streamed litert chunks."
    return {'role': 'assistant', 'content': [{'type': 'text', 'text': ''.join(_resp_text(c) for c in chunks)}]}

@patch
def _stream(self: Chat, max_output_tokens=None):
    "Yield markdown for a streaming turn, then track usage + history."
    tc0, fmt, chunks = self.conv.token_count, StreamFormatter(), []
    for o in self.conv.send_message_async(self.turn_msg, max_output_tokens=max_output_tokens):
        chunks.append(o); yield fmt.format_item(o)
    self.turn_res = _merge_chunks(chunks)
    self._track(tc0); self.hist.append(self.turn_res)
    for _ in run_cbs(self, 'after_response'): pass
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run nbdev-prepare`
Expected: PASS.

- [ ] **Step 5: Add a manual streaming-test cell** (`#| eval: false`)

```python
#| eval: false
chat = Chat()
md = ''.join(chat("Count: one two three", stream=True))
assert md and chat.turn_res is not None
assert chat.hist[-1] == chat.turn_res and chat.use.completion_tokens > 0
print(md)
```

- [ ] **Step 6: Verify streaming manually**

Run:
```bash
uv run nbdev-prepare
uv run python -c "from rishi.core import *; set_min_log_severity(2); c=Chat(); md=''.join(c('Count: one two three', stream=True)); print(md); assert c.turn_res and c.use.completion_tokens>0"
```
Expected: streamed text prints; no assertion error.

- [ ] **Step 7: Commit**

```bash
git add nbs/00_core.ipynb rishi/core.py
git commit -m "feat: Chat streaming turn via StreamFormatter"
```

---

### Task 9: Tool round end-to-end + docs refresh

**Files:**
- Modify: `nbs/00_core.ipynb` (new `#| eval: false` tool-round cell; update markdown/`index.ipynb` if it references the old stub)

**Interfaces:**
- Consumes: full `Chat`, `ChatToolHandler`, `ChatCallback`.
- Produces: no new public API — verifies `before_tool_calls`/`after_tool_calls` fire and tool messages land in `hist`.

- [ ] **Step 1: Add a manual tool-round cell** (`#| eval: false`)

```python
#| eval: false
def add(a: int, b: int) -> int:
    "Add two integers.\n\nArgs:\n    a: first\n    b: second"
    return a + b

fired = []
class _SpyCB(ChatCallback):
    def before_tool_calls(self): fired.append('before')
    def after_tool_calls(self):  fired.append('after')

chat = Chat(tools=[add], sp="Use the add tool for arithmetic.")
chat.add_cb(_SpyCB)
r = chat("What is 21 + 21? Use the tool.")
assert 'before' in fired and 'after' in fired
assert any(m.get('role') == 'tool' for m in chat.hist)
print(_resp_text(r)); chat.print_hist()
```

- [ ] **Step 2: Verify the tool round manually**

Run:
```bash
uv run nbdev-prepare
uv run python - <<'PY'
from rishi.core import *
set_min_log_severity(2)
def add(a:int,b:int)->int:
    "Add two integers.\n\nArgs:\n    a: first\n    b: second"
    return a+b
fired=[]
class Spy(ChatCallback):
    def before_tool_calls(self): fired.append('before')
    def after_tool_calls(self):  fired.append('after')
c=Chat(tools=[add], sp="Use the add tool for arithmetic.")
c.add_cb(Spy)
r=c("What is 21 + 21? Use the tool.")
print(_resp_text(r)); print('fired=',fired)
assert 'before' in fired and 'after' in fired
assert any(m.get('role')=='tool' for m in c.hist)
PY
```
Expected: reply references 42; `fired= ['before', 'after']`; no assertion error.

- [ ] **Step 3: Refresh docs and check for stale references**

Update the top markdown cell of `00_core.ipynb` if it still describes only "model initialisation and tools". Open `nbs/index.ipynb` and confirm no references to the old `Chat` stub signature remain; update any usage snippet to the new `Chat().__call__` API.

Run: `uv run nbdev-prepare`
Expected: PASS; docs build clean.

- [ ] **Step 4: Commit**

```bash
git add nbs/00_core.ipynb rishi/core.py nbs/index.ipynb
git commit -m "test: end-to-end tool round; refresh docs"
```

---

## Self-Review

**Spec coverage:**
- Message helpers → Task 1. `UsageStats` → Task 2. Callback framework (full `ChatCallback` architecture) → Task 3. StreamFormatter → Task 4. `ToolReminderCallback` built-in → Task 5. `ChatToolHandler` (leverage `ToolEventHandler`) → Task 6. `Chat` init/turn/usage/history/`print_hist` → Task 7. Streaming → Task 8. Tool round + docs → Task 9.
- Usage source = `token_count` diff (Tasks 7/8). Compression trigger = `Chat.token_count`/`pct_full` vs `ctx_limit` (Task 7).
- Spec's `UsageCB`/`HistoryCB` intentionally folded inline (see Deviations); `StopReasonCallback` dropped in favor of leaving stop handling to callers — noted as a deviation and surfaced at handoff.

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every run step gives an exact command + expected output.

**Type consistency:** `mk_msg`/`mk_msgs`/`mk_content`, `UsageStats(prompt_tokens,completion_tokens,total_tokens,n)`, `run_cbs(chat,event)`, `ChatCallback` attrs, `StreamFormatter.format_item/format_stream`, `_resp_text`, `ChatToolHandler(chat)`, `Chat.__call__(msg,stream,max_output_tokens)`, `_stream`, `_merge_chunks` are named identically across producing and consuming tasks.

## Open items surfaced during planning
- `StopReasonCallback` is not ported (litert's stop info is limited to stream exceptions). If you want truncation warnings, we can add a small callback that inspects the final chunk — say the word.
- The prefill-boundary token split is omitted in favor of `tokenize()`-based split; add it later only if per-turn input accuracy matters.

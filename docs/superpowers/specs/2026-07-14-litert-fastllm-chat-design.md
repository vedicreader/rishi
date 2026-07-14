# Design: fastllm-style `Chat` over litert_lm

Date: 2026-07-14
Module: `rishi/core.py` (developed in `nbs/00_core.ipynb`, nbdev)
Reference source: `fastllm/chat.py` (installed dep) and `litert_lm/*` (installed dep).

## Goal

Give the local `litert_lm` engine the ergonomics of fastllm's `chat.py`: a callable
`Chat` turn interface, Python-visible history, an ordered callback system, notebook
streaming display, and input/output token accounting so the caller knows when to compress
the conversation. Succinct, functional code that reuses litert primitives and mirrors
fastllm idioms (`GetAttr` callbacks, `store_attr`, sync `StreamFormatter`) rather than
reimplementing them.

## Key decision: synchronous API

fastllm's `AsyncChat` is fully async because LiteLLM is network-bound. litert is local and
**entirely synchronous**: `conv.send_message` is a blocking C call and
`conv.send_message_async` is a *synchronous generator* (queue + C callback, no asyncio).
Therefore our `Chat` is **sync** — sync `__call__`, sync callbacks, sync `StreamFormatter`
(fastllm's `StreamFormatter`, not `AsyncStreamFormatter`). No event-loop plumbing.

## What litert_lm already provides (do NOT reimplement)

- **Message construction**: `Message.system/user/model/tool`, `Contents.of(...)`,
  `Content.Text/ImageBytes/ImageFile/AudioBytes/AudioFile/ToolResponse`, and
  `normalize_message` (accepts `str` / dict / `Contents` / `Message`).
- **Tool calling**: automatic tool-call loop inside `Conversation.send_message` /
  `send_message_async`; `tool_from_function` (Python fn → OpenAPI schema from signature +
  docstring); `ToolEventHandler` (`approve_tool_call`, `process_tool_response` hooks).
- **Streaming**: `send_message_async` yields response dicts
  `{"role":"assistant","content":[{"type":"text","text":...}]}` chunk-by-chunk.
- **Cancellation**: `conv.cancel_process()`.
- **Token count**: `conv.token_count` (cumulative KV-cache = prefill + decode);
  `engine.tokenize` / `engine.detokenize`.

Note: litert responses carry **no usage block**, and history lives only in the C++ KV
cache — nothing Python-visible to inspect or render. Those are the gaps we fill.

## Components (each independently testable)

### 1. Message helpers (thin — reuse litert; mirror fastllm names)
- `mk_content(o)`: `str`→`Text`, `bytes`→`ImageBytes`, `Path`/image file→`ImageFile`
  (mime via `guess_type`), audio analogously. Returns a litert `Content`.
  (litert analog of fastllm `_mk_content`.)
- `mk_msg(content, role='user')`: build a litert `Message`; accepts str / bytes / list
  (multimodal) / dict / existing `Message`. Delegates to litert `normalize_message` where
  possible. fastllm's cache-control/ttl args are dropped (Anthropic-specific).
- `mk_msgs(msgs)`: normalize a list into canonical litert message dicts for history/preface.
  fastllm's `fmt2hist`/tool-details parsing is NOT ported (wire-protocol specific).

Pure functions, no engine dependency.

### 2. `UsageStats` (mirror fastllm shape, litert source)
- Fields: `prompt_tokens`, `completion_tokens`, `total_tokens`, `n` (turns). `store_attr`.
  `__add__`/`__radd__` accumulate; `__repr__` summarises (`total=… | in=… | out=…`);
  `fmt()` returns a `<details>` token block like fastllm.
- Populated from `conv.token_count` diffs — no re-tokenizing on the hot path.
  - **Plain (no-tool) streaming turn**: read `token_count` before → after first chunk
    (prefill boundary = **prompt_tokens**) → at end (delta = **completion_tokens**).
  - **Non-streaming / tool turns**: before/after delta around the whole `send_message`.
    `total_tokens` = final `token_count` = authoritative live context size. For
    non-streaming plain turns, split `completion_tokens = len(engine.tokenize(resp_text))`,
    `prompt_tokens = delta - completion_tokens` as best-effort fallback.
- `Chat.use` accumulates across turns. Compression trigger: compare `chat.use.total_tokens`
  (== `conv.token_count`) against a configurable `ctx_limit`.

### 3. Callbacks (`ChatCallback` port, sync)
- Base `ChatCallback(GetAttr)` with `_default='chat'` (so callbacks read chat state:
  `self.turn_msg`, `self.turn_res`, `self.stream`, etc.), plus `order:int`, `run:bool`,
  `chat=None`; `__repr__` = class name. Exactly fastllm's idiom, minus async.
- `Chat._run_cbs(event)` iterates `self.cbs.sorted('order')`, calling `cb.<event>()` on
  enabled callbacks that define it; a callback may be a plain method or a generator that
  yields stream items (yielded items are forwarded into the stream, like fastllm).
- Events (fastllm names adapted to litert): `after_msgs`, `before_send` (≙ before_acomplete),
  `after_response` (≙ after_acomplete), `before_tool_calls`, `after_tool_calls`.
- `add_cb`/`add_cbs` mirror fastllm (instantiate class, set `cb.chat=self`, append).
- Built-ins ported/adapted (fastllm's Deepseek*/FenceTool callbacks dropped — provider/
  wire-specific):
  - `UsageCB` — updates `chat.use` from `token_count` diff.
  - `HistoryCB` — appends turn messages to `chat.hist`.
  - `ToolReminderCallback` — port directly (injects the tool-summary system-reminder).
  - `StopReasonCallback` — adapted: litert surfaces limited stop info ("Max number of
    tokens reached" / cancellation); warn on truncation.
- `default_cbs=True` installs the built-ins (fastllm `defaults.chat_callbacks` analog).

### 4. Tool handling — via `ToolEventHandler` (leverage litert; `automatic_tool_calling=True`)
- `ChatToolHandler(ToolEventHandler)` bridges litert's in-engine loop to Chat callbacks:
  - `approve_tool_call(tc)` → fire `before_tool_calls`, record tool-call into `hist`,
    return `True` (or consult an approve callback).
  - `process_tool_response(resp)` → fire `after_tool_calls`, record tool message into
    `hist`, return `resp`.
- We do NOT reimplement litert's tool loop. Accepted consequence: usage is the cumulative
  `token_count` delta spanning all tool rounds, not per-round — sufficient for the
  compression trigger.

### 5. History
- `self.hist`: list of canonical litert message dicts. `__init__`'s `messages` seeds both
  `hist` and the conversation preface. Each turn appends the user msg, assistant response,
  and any tool messages (captured in `ChatToolHandler`). `print_hist()` renders role + text
  (+ tool-call summaries), fastllm-style.

### 6. Streaming display (sync `StreamFormatter`, adapted)
- `StreamFormatter(mx=2000, showthink=False)`: consumes litert stream dicts, extracts text
  from the `content` list (litert shape), renders markdown; tool calls rendered via
  `mk_tr_details`/`_tc_summary` helpers ported from fastllm. `display_stream` wrapper uses
  IPython `display`/`update_display` (sync analog of fastllm's `adisplay_stream`).

### 7. `Chat` (orchestration — extends the existing stub)
- `__init__(model_id, model_path, backend, multimodal, sp, messages, tools, ctx_limit,
  cbs, default_cbs, **kwargs)`: build `engine` (existing `get_model` helper), then
  `self.conv = engine.create_conversation(messages=…, tools=…,
  tool_event_handler=ChatToolHandler(self), automatic_tool_calling=True,
  sampler_config=…)`. Init `hist`, `use=UsageStats()`, `cbs=L()`; `add_cbs(defaults)` when
  `default_cbs`, then `add_cbs(cbs)`.
- `__call__(msg=None, stream=False, **kw)`:
  fire `after_msgs` → `before_send` → record `token_count` → `send_message`
  (or `send_message_async` rendered through `StreamFormatter`) → compute usage from
  `token_count` → `after_response`. Tool rounds handled inside litert, surfaced via
  `ChatToolHandler` (which fires `before_tool_calls`/`after_tool_calls`). Returns the
  response with a `.text`/`contents` accessor; stream path renders live and yields chunks.
- Keep `get_model` helper as-is.

## Testing (nbdev cells, small model `gemma4_e2b`)
- `mk_msg`/`mk_msgs`: pure, assert produced litert message dicts (no engine).
- Basic turn returns text; `hist` grows by user+assistant.
- `use.total_tokens` increases and equals `conv.token_count`; `prompt_tokens`/
  `completion_tokens` populated on a plain turn.
- A tool round fires `before_tool_calls`/`after_tool_calls` and records tool messages.
- Streaming turn yields/renders text via `StreamFormatter`.
- Run `nbdev-prepare` (hyphen) after changes; check `index.ipynb` for stale references.

## Non-goals (YAGNI)
- Async `Chat`, structured outputs / constraint decoding, effort/thinking levels, cost
  estimation, Anthropic prompt caching, fence tools, Deepseek/remote-API callbacks,
  per-tool-round usage splitting.

## Open verification items (resolve during build, not blocking)
- Confirm `conv.token_count` updates at the prefill→decode boundary so the streaming
  input/output split is meaningful; if not, fall back to the tokenize-based split.

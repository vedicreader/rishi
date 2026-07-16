---
name: rishi
description: Run Gemma models on-device through rishi's Chat API over litert_lm - local chat with tool calling and human approval, streaming, thinking, a python sandbox, structured output, classification, and graded answers. Use when writing or debugging offline LLM chat, local tool-use agents, or anything mentioning rishi, litert_lm, or gemma .litertlm models.
---

# rishi

rishi wraps Google's on-device litert_lm engine in a callable `Chat`. Models run locally (CPU or GPU), so there are no API keys and no network once weights are cached. Import everything from `rishi.core`.

## The one thing to remember

`chat(msg)` returns litert's response wrapped in `Resp`, not a string. Pull text with `resp_text(r)`; in a notebook `r` renders itself as markdown (thinking, text, and tool calls). When streaming, you iterate markdown chunks instead.

```python
from rishi.core import Chat, resp_text
chat = Chat()                       # downloads gemma-4-E2B once, then loads from cache
r = chat("Say hello.")
print(resp_text(r))
```

`Chat()` builds an engine and a conversation. Each call runs one turn, appends to `chat.hist`, and updates `chat.use`. Calling again continues the same conversation (litert holds the KV cache).

## API surface

- `Chat(engine=None, model_id=gemma4_e2b, model_path=None, backend=Backend.CPU(), multimodal=True, cache_dir=None, sp='', messages=None, tools=None, ctx_limit=None, approve=None, tool_max_len=None, think=False, filter_think=True, temp=None, top_k=None, top_p=None, seed=None, sampler_config=None, max_output_tokens=None, cbs=None, default_cbs=True)`.
- `chat(msg=None, stream=False, max_output_tokens=None, cbs=None)` runs a turn. `stream=True` returns a generator of markdown chunks. `cbs=` registers callbacks for that turn only.
- State: `chat.hist` (Python-visible history, print with `chat.print_hist()`), `chat.use` (a `UsageStats`: `total`, `in`, `out`, `turns`), `chat.token_count` (live context size), `chat.pct_full` (that over `ctx_limit`).
- Chat methods: `run_py(code)`, `classify(text, labels)`, `structured(prompt, schema)`, `check(question, expected, ...)`, `grades(question, expected, actual)`, `count_tokens(text)`, `render(msg)`, `cancel()`, `add_cb`/`add_cbs`/`remove_cb`/`remove_cbs`, `close()`.
- `Chat.create_engine(...)` is a classmethod that builds the `Engine` (resolves the model, makes `cache_dir`, wires multimodal backends). Patch it or pass `engine=` to override.
- Module helpers: `resp_text`, `thought`, `display_stream`, `mk_msg`/`mk_content`/`mk_msgs`, `hitl_policy`, `output_matches`, `task_complete`, `bench`, `get_model`. Model ids: `gemma4_e2b`, `gemma4_e4b`, `gemma4_12b`.
- Callbacks: `HistoryCallback`, `UsageCallback`, `ToolReminderCallback`, `TruncationCallback`, `PyFenceCallback`, and the `ChatCallback` base.

## Streaming and thinking

```python
for chunk in chat("Count to five.", stream=True): print(chunk, end='', flush=True)
display_stream(chat("Count to five.", stream=True))   # renders live in a notebook
```

`Chat(think=True)` turns on the thinking channel. `resp_text(r)` is the answer, `thought(r)` is the reasoning, and `r` renders the thinking as a quoted block in a notebook. `filter_think=True` (the default) keeps thinking out of the KV cache.

## Tools and approval

Register plain functions. litert builds the schema from the signature and docstring and calls them mid-turn.

```python
def add(a: int, b: int) -> int:
    "Add two integers."
    return a + b
chat = Chat(tools=[add])
```

Gate execution with `approve`, an `approve(tool_call) -> bool` consulted before every call. `hitl_policy` builds one from a per-tool rule:

```python
from rishi.core import hitl_policy
chat = Chat(tools=[add, danger], approve=hitl_policy({'add': 'approved', 'danger': 'dont_run'}))
```

Modes are `approved` (run), `dont_run` (block), `check` (ask on the console). A blocked call is recorded as "Denied by human operator" and reported to the model. For custom logic, pass your own function. `ChatToolHandler` routes calls through `approve` and writes calls and results into `hist`.

## Running python from replies

`PyFenceCallback` makes the chat a code interpreter: it runs the last ```python fence through a sandbox (`safepyrun`, so `socket`/`importlib` are blocked), feeds the output back as a ```result block, and loops until the model answers in prose or `done(chat)` is true, capped by `max_rounds`.

```python
from rishi.core import PyFenceCallback, output_matches
chat = Chat(cbs=[PyFenceCallback], sp="Use a ```python fence to compute the answer, then reply in prose.")
chat("What is 2**100?")
chat("Sort [3,1,2] and print it.", cbs=[PyFenceCallback(done=output_matches('[1, 2, 3]'))])
```

`done` is any `chat -> bool`. `output_matches(expected)` stops once `chat.turn_code_out` contains the expected value; `task_complete` asks the model. Execution goes through the same `approve` gate as a tool. `chat.run_py(code)` runs a snippet directly in the chat's persistent namespace.

## Structured output, classification, and grading

These run one-shot in a throwaway conversation on the same engine, so they leave the live chat untouched.

```python
from dataclasses import dataclass
@dataclass
class Person: name: str; age: int
chat.structured("John Smith is 30.", Person)          # -> Person(name='John Smith', age=30)
chat.classify("I loved it!", ['positive','negative']) # -> 'positive'

chat.check("Capital of France?", "Paris").ok           # deterministic match -> True
judge = Chat(model_id=gemma4_12b, multimodal=False, cache_dir='.cache/litertlm')
chat.check("Name a primary colour.", "red, blue, or yellow", judge=judge).ok  # graded by a bigger model
```

`check` extracts the answer from a ```answer fence and grades it. Default grade is `grade_fn(answer, expected)` (`_matches`, a contains check). Pass `llm_judge=True` or a `judge=` chat to grade with a model, or your own `grade_fn`. It returns `AttrDict(question, expected, answer, ok)`.

## Callbacks

Subclass `ChatCallback`, hook `before_send`, `after_response`, `before_tool_calls`, or `after_tool_calls`, and read turn state off the chat (`self.turn_res` is `chat.turn_res`). `order` sets when it runs; keep `HistoryCallback` (records the turn) and `UsageCallback` at the front. Register with `chat.add_cb(MyCb)` or `Chat(cbs=[...])`, run one for a single turn with `chat(msg, cbs=[...])`, and drop one with `chat.remove_cb(MyCb)` (by instance or class). The three defaults are on unless you pass `default_cbs=False`.

## Sharing a model

Loading costs seconds and gigabytes. Build one engine and reuse it:

```python
eng = Chat.create_engine(cache_dir='.cache/litertlm')
a, b = Chat(engine=eng), Chat(engine=eng)
```

A Chat that built its own engine frees it on `close()`; a Chat handed an engine leaves it alone, so siblings keep working.

## Gotchas

- Model files: a repo can ship both a native `.litertlm` and a `-web` build. The web build has no CPU/GPU decode graph and fails with `TF_LITE_PREFILL_DECODE not found`. `get_model` already prefers the native one.
- GPU needs a writable `cache_dir`. Without it you get `Could not open ... mldrift_weight_cache.bin: No such file or directory`. `create_engine` makes the directory for you when you pass `cache_dir`.
- The log line `WebGPU sampler not available, falling back to statically linked C API` is harmless. Quiet the noise with `set_min_log_severity(3)`.
- Tool and structured-output arguments arrive as floats (`21.0`) from the model's JSON. Cast inside the tool if you need strict ints.
- `run_text_scoring` is not available on this runtime, so `classify` and `check` grade by generation, not log-likelihood scoring.

## Working on rishi itself

It's an nbdev project. Edit `nbs/00_core.ipynb`, not `rishi/core.py` (generated). Tests are non-exported `#| hide` cells; model-dependent cells are `#| eval: false` to keep the test run offline. Run `nbdev-prepare` (with a hyphen) after changes.

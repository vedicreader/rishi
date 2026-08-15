

# rishi

rishi wraps four engines - three on-device, one hosted - in one callable
`Chat`. Models run locally, so there are no API keys and no network once
weights are cached. The backend-agnostic API lives in `rishi.core`; the
engines are `rishi.litert` (Gemma `.litertlm` via litert_lm),
`rishi.llama` (any GGUF via llama-cpp-python), `rishi.mlx` (Apple
silicon via mlx-lm/mlx-vlm) and `rishi.remote` (hosted APIs via
fastllm). `Chat(model)` picks one from the model name.

A plain `pip install rishi` (and therefore `uv add rishi`) installs
LiteRT and fastllm everywhere, plus MLX and MLX-VLM on Apple Silicon, so
local and hosted chat work immediately. `rishi[llama]` is the only
runtime extra; it adds llama.cpp for GGUF models. Backend modules still
load lazily; asking for llama.cpp without its extra raises an
ImportError naming it.

## The one thing to remember

`chat(msg)` returns litert’s response wrapped in `Resp`, not a string.
Pull text with `resp_text(r)`; in a notebook `r` renders itself as
markdown (thinking, text, and tool calls). When streaming, you iterate
markdown chunks instead.

``` python
from rishi.core import Chat, resp_text
chat = Chat()                       # downloads gemma-4-E2B once, then loads from cache
r = chat("Say hello.")
print(resp_text(r))
```

`Chat()` builds an engine and a conversation. Each call runs one turn,
appends to `chat.hist`, and updates `chat.use`. Calling again continues
the same conversation (litert holds the KV cache).

## API surface

- `Chat(model=None, *, runtime=None, model_path=None, engine=None, backend=Backend.CPU(), multimodal=True, cache_dir=None, sp='', messages=None, tools=None, ctx_limit=None, approve=None, tool_max_len=None, think=False, filter_think=True, temp=None, top_k=None, top_p=None, seed=None, sampler_config=None, max_output_tokens=None, cbs=None, default_cbs=True)`
  — `model` first (a repo id or local path); `Chat` dispatches by
  `runtime`/model shape and returns a
  `LitertChat`/`LlamaChat`/`MlxChat`/`RemoteChat`. Litert-specific
  kwargs shown; llama adds `quant`, `n_ctx`, `n_gpu_layers`, `mmproj`,
  `comp_kw`; mlx and remote have their own (see their sections).
- `chat(msg=None, stream=False, max_output_tokens=None, cbs=None)` runs
  a turn. `stream=True` returns a generator of markdown chunks. `cbs=`
  registers callbacks for that turn only.
- State: `chat.hist` (Python-visible history, print with
  `chat.print_hist()`), `chat.use` (a `UsageStats`: `total`, `in`,
  `out`, `turns`), `chat.token_count` (live context size),
  `chat.pct_full` (that over `ctx_limit`).
- Chat methods: `run_py(code)`, `classify(text, labels)`,
  `structured(prompt, schema)`, `check(question, expected, ...)`,
  `grades(question, expected, actual)`, `count_tokens(text)`,
  `render(msg)`, `cancel()`,
  `add_cb`/`add_cbs`/`remove_cb`/`remove_cbs`, `close()`.
- `create_engine(...)` is a classmethod on each backend class
  (`LitertChat.create_engine`, `LlamaChat.create_engine`,
  `MlxChat.create_engine`) that builds the engine (resolves the model,
  makes `cache_dir`, wires multimodal backends). `rishi.core.Chat` has
  none - patch the backend’s, or pass `engine=` to override.
  `RemoteChat` has no engine to build.
- Module helpers: `resp_text`, `thought`, `display_stream`,
  `hitl_policy`, `output_matches`, `task_complete`, `bench`. Model ids:
  `gemma4_e2b`, `gemma4_e4b`, `gemma4_12b`. The message builders
  (`mk_msg`/`mk_content`/`mk_msgs`) and model resolver are
  backend-specific, so reach them per backend as `chat.mk_msg(...)` /
  `LitertChat.mk_msg` rather than as a bare `from rishi import *` name
  (both backends define their own, so they aren’t re-exported at the top
  level).
- Callbacks: `ChatCallback` (base), `PyFenceCallback`, and
  `TruncationCallback` are public in `rishi.core`, along with the shared
  `UsageCallback`/`ToolReminderCallback` that llama and mlx use as
  defaults. litert’s history/usage callbacks are internal. All defaults
  are on unless you pass `default_cbs=False`.
- Tool-call budget: `max_steps` (default 10) caps tool *calls* per turn
  on every backend. Past the cap, calls are denied with `budget_msg_`,
  and rishi sends `final_prompt` asking the model to answer with what it
  has, so a runaway loop ends in prose. `max_steps=None` removes the
  cap.
- `parallel_tools=True` (llama and mlx; litert raises
  `NotImplementedError`) runs independent calls from one turn
  concurrently. Approval stays sequential, so HITL order and budget
  accounting don’t change, and history is identical either way.
- Context recovery: if the window fills mid-turn, rishi truncates the
  oldest tool results, rebuilds backend state, and asks for a summary;
  `ContextWindowExceededError` is raised only if that retry also fails.
- `SlidingWindowCallback(threshold=0.9, keep_first=2, keep_last=8, summarize=False)`
  is the *proactive* version and works on every backend. Before each
  turn it checks `pct_full`, and if the context is nearly full it drops
  whole message groups from the **middle** of `hist` - keeping the
  earliest turns and the live thread - then calls
  `chat._recreate_conv()` so the backend rebuilds from the shortened
  history. It needs `ctx_limit` set, and no-ops without one.
  `evict_middle`/`msg_groups` are exported if you want the policy
  without the callback; a tool call and its results are one group and
  are never split. Opt in with `Chat(cbs=[SlidingWindowCallback()])` -
  eviction is lossy, so it isn’t a default. `summarize=True` spends one
  model call to replace the dropped middle with a summary.
- This matters most on **litert**, whose KV cache has no automatic
  recycling upstream
  ([gallery#856](https://github.com/google-ai-edge/gallery/issues/856)):
  a full cache OOMs on GPU/NPU and makes the CPU path repeat itself
  forever, rather than raising cleanly. litert now also evicts and
  retries once reactively, and its system prompt lives outside `hist` so
  a rebuild always re-applies it.
- `chat.use` is a `UsageStats` with `prompt_tokens`,
  `completion_tokens`, `total_tokens`, `n`, `cached_tokens` (prompt
  tokens served from the backend’s KV/prefix cache), plus `cost`/`model`
  for merging with hosted-API usage.
- Streaming has two modes: `chat(msg, stream=True)` yields **markdown
  strings** (print them, or hand to `display_stream`);
  `chat(msg, stream='raw')` yields the underlying **chunk dicts**
  (`{'content': [{'type': 'text', ...}]}`,
  `{'channels': {'thought': ...}}`,
  `{'content': [{'type': 'tool_call', ...}]}`) for programmatic
  consumers that want structure rather than rendered text. Both run the
  same tool loop.
- `ToolCall(name, arguments, id=None, server=False)` builds a canonical
  tool call - a `dict` subclass, so indexing still works, with
  `.name`/`.arguments`/`.server` accessors. A call with `server=True` is
  one the *provider* runs; the tool loop records it and never executes
  it locally. `mk_tool_res_msg(tc, result)` /
  `mk_tool_res_msgs(tcs, results)` build the `role='tool'` reply
  messages, if you’re driving a loop by hand.

## Streaming and thinking

``` python
for chunk in chat("Count to five.", stream=True): print(chunk, end='', flush=True)
display_stream(chat("Count to five.", stream=True))   # renders live in a notebook
```

`Chat(think=True)` turns on the thinking channel. `resp_text(r)` is the
answer, `thought(r)` is the reasoning, and `r` renders the thinking as a
quoted block in a notebook. `filter_think=True` (the default) keeps
thinking out of the KV cache.

## Tools and approval

Register plain functions. litert builds the schema from the signature
and docstring and calls them mid-turn.

``` python
def add(a: int, b: int) -> int:
    "Add two integers."
    return a + b
chat = Chat(tools=[add])
```

Gate execution with `approve`, an `approve(tool_call) -> bool` consulted
before every call. `hitl_policy` builds one from a per-tool rule:

``` python
from rishi.core import hitl_policy
chat = Chat(tools=[add, danger], approve=hitl_policy({'add': 'approved', 'danger': 'dont_run'}))
```

Modes are `approved` (run), `dont_run` (block), `check` (ask on the
console). In a Leela web IDE kernel, `hitl_policy(modes, browser=True)`
sends checked calls to Leela’s browser approval card instead of calling
`input()`; use `browser='http://host:port'` or set `LEELA_URL` when
needed. `browser_approval(url=None, timeout=300)` is also available as a
standalone callback. A blocked call is recorded as “Denied by human
operator” and reported to the model. For custom logic, pass your own
function. `ChatToolHandler` routes calls through `approve` and writes
calls and results into `hist`.

## Running python from replies

`PyFenceCallback` makes the chat a code interpreter: it runs the last
`` python fence through a sandbox (`safepyrun`, so `socket`/`importlib` are blocked), feeds the output back as a ``result
block, and loops until the model answers in prose or `done(chat)` is
true, capped by `max_rounds`.

``` python
from rishi.core import PyFenceCallback, output_matches
chat = Chat(cbs=[PyFenceCallback], sp="Use a ```python fence to compute the answer, then reply in prose.")
chat("What is 2**100?")
chat("Sort [3,1,2] and print it.", cbs=[PyFenceCallback(done=output_matches('[1, 2, 3]'))])
```

`done` is any `chat -> bool`. `output_matches(expected)` stops once
`chat.turn_code_out` contains the expected value; `task_complete` asks
the model. Execution goes through the same `approve` gate as a tool.
`chat.run_py(code)` runs a snippet directly in the chat’s persistent
namespace.

## Structured output, classification, and grading

These run one-shot in a throwaway conversation on the same engine, so
they leave the live chat untouched.

``` python
from dataclasses import dataclass
@dataclass
class Person: name: str; age: int
chat.structured("John Smith is 30.", Person)          # -> Person(name='John Smith', age=30)
chat.classify("I loved it!", ['positive','negative']) # -> 'positive'

chat.check("Capital of France?", "Paris").ok           # deterministic match -> True
judge = Chat(gemma4_12b, multimodal=False, cache_dir='.cache/litertlm')
chat.check("Name a primary colour.", "red, blue, or yellow", judge=judge).ok  # graded by a bigger model
```

`check` extracts the answer from a
\`\``answer fence and grades it. Default grade is`grade_fn(answer,
expected)`(`matches\_`, a contains check). Pass`llm_judge=True`or a`judge=`chat to grade with a model, or your own`grade_fn`. It returns`AttrDict(question,
expected, answer, ok)\`.

## Callbacks

Subclass `ChatCallback`, hook `before_send`, `after_response`,
`before_tool_calls`, or `after_tool_calls`, and read turn state off the
chat (`self.turn_res` is `chat.turn_res`). `order` sets when it runs;
the backend’s built-in history and usage callbacks sit at the front (low
`order`). Register with `chat.add_cb(MyCb)` or `Chat(cbs=[...])`, run
one for a single turn with `chat(msg, cbs=[...])`, and drop one with
`chat.remove_cb(MyCb)` (by instance or class). The defaults are on
unless you pass `default_cbs=False`.

## Sharing a model

Loading costs seconds and gigabytes. Build one engine and reuse it:

``` python
from rishi.litert import LitertChat
eng = LitertChat.create_engine(cache_dir='.cache/litertlm')      # `create_engine` is per backend
a, b = Chat(engine=eng), Chat(engine=eng)
```

A Chat that built its own engine frees it on `close()`; a Chat handed an
engine leaves it alone, so siblings keep working.

## Gotchas

- Model files: a repo can ship both a native `.litertlm` and a `-web`
  build. The web build has no CPU/GPU decode graph and fails with
  `TF_LITE_PREFILL_DECODE not found`. rishi’s model resolver already
  prefers the native one.
- GPU needs a writable `cache_dir`. Without it you get
  `Could not open ... mldrift_weight_cache.bin: No such file or directory`.
  `create_engine` makes the directory for you when you pass `cache_dir`.
- The log line
  `WebGPU sampler not available, falling back to statically linked C API`
  is harmless. Quiet the noise with `set_min_log_severity(3)`.
- Tool and structured-output arguments arrive as floats (`21.0`) from
  the model’s JSON. Cast inside the tool if you need strict ints.
- `run_text_scoring` is not available on this runtime, so `classify` and
  `check` grade by generation, not log-likelihood scoring.

## One interface for all four backends

`Chat` picks the backend from the model name, fastllm-style, and returns
that backend’s own `Chat` subclass
(`LitertChat`/`LlamaChat`/`MlxChat`/`RemoteChat`) - a real subclass, not
a wrapper, so `isinstance(chat, Chat)` holds, `chat.runtime` says which,
and callbacks, tools, `hist`, `use` and streaming are exactly as
documented per backend. `**kw` passes straight through, so
backend-specific arguments (`backend=Backend.GPU()`, `mmproj=`,
`n_gpu_layers=`, `kv_bits=`) still work.

``` python
from rishi import Chat, AsyncChat

Chat('litert-community/gemma-4-E2B-it-litert-lm')   # -> litert
Chat('Qwen/Qwen3-4B-GGUF')                          # -> llama.cpp
Chat('mlx-community/Qwen3-4B-4bit')                 # -> mlx
Chat('mlx-community/Qwen3-VL-4B-Instruct-4bit')     # -> mlx, and on to MlxVlmChat (vision)
Chat('claude-sonnet-4-5')                           # -> remote (hosted, via fastllm)
Chat('openrouter/moonshotai/kimi-k2')               # vendor-prefixed hosted names work too
Chat('/models/mine.gguf')                           # local file -> model_path=
Chat('my-org/private', runtime='llama')             # explicit wins
Chat('llama/my-org/private')                        # or prefix the name
Chat()                                              # nothing to go on -> litert, as before
achat = AsyncChat('Qwen/Qwen3-4B-GGUF')             # async on any backend
```

Resolution order: explicit `runtime=`, then a `runtime/` prefix (only if
it names a known runtime, so `litert-community/...` is left alone), then
the shape of the id/path (`.litertlm`/`litert-community`/`litert-lm` vs
`.gguf`/`GGUF` vs `mlx-community`/`-mlx` vs hosted names like
`claude-*`/`gpt-*`/`gemini-*`), then the default (`litert`). Local
shapes are checked before hosted name patterns. A bare name it can’t
place raises with instructions rather than guessing - there is no alias
table, so pass a full hub repo id or path. `resolve_runtime`,
`split_runtime`, `infer_runtime` and `get_runtime` are exported if you
want the decision without building anything.

The selector is `runtime=`, not `backend=` - `backend=` stays free for
litert’s hardware backend (`Backend.GPU()`), which passes straight
through.

## llama.cpp backend (rishi.llama)

`pip install 'rishi[llama]'` (adds llama-cpp-python). Same `Chat` API
over any GGUF repo on the HuggingFace Hub, plus an `AsyncChat`:

``` python
from rishi.llama import Chat, AsyncChat, resp_text, qwen3_4b

chat = Chat(qwen3_4b, think=False)               # or model_path='path/to/model.gguf'
r = chat("Say hello.")
print(resp_text(r))

achat = AsyncChat(chat)                          # or AsyncChat(model) to build its own
r = await achat("Again?")
async for c in await achat("Stream it.", stream=True): print(c, end='')
```

Differences from the litert backend:

- `Chat(model=None, *, runtime=None, model_path=None, engine=None, quant='Q4_K_M', n_ctx=8192, n_gpu_layers=0, mmproj=None, eng_kw=None, sp='', messages=None, tools=None, ctx_limit=None, approve=None, tool_max_len=None, max_steps=10, parallel_tools=False, final_prompt=..., think=None, temp=None, top_k=None, top_p=None, seed=None, preserve_cache=False, max_output_tokens=None, comp_kw=None, cbs=None, default_cbs=True)` -
  `model` is positional (a repo id or a local path); there is no
  `model_id=` keyword. Model ids: `qwen3_06b`, `qwen3_17b`, `qwen3_4b`,
  `gemma3_1b`, `gemma3_4b`; `quant` picks the `.gguf` file from the
  repo. `n_gpu_layers=-1` offloads everything to GPU.
- Images and audio: a multimodal GGUF needs an `mmproj` projector
  alongside the model. `Chat(gemma3_4b, mmproj=True)` resolves it from
  the same repo (cache-first, same as the model lookup; `get_mmproj`
  does it standalone), or pass an explicit path. That builds llama.cpp’s
  `MTMDChatHandler`. Then pass `bytes` or a `Path` in the message list:
  `chat(['Describe this.', Path('cat.jpg')])`,
  `chat(['Transcribe this.', Path('clip.wav')])`, or both in one turn
  (each becomes a media marker in document order).
- Audio works because rishi `@patch`es `MTMDChatHandler`, which upstream
  wires for images only: `get_image_urls` also collects `input_audio`
  parts, `_get_template_messages` maps them to the media marker,
  `_create_bitmap_from_bytes` routes audio to
  `mtmd_bitmap_init_from_audio`, and `_init_mtmd_context` stops
  rejecting audio-only projectors. Images keep the original code path.
  **Note this makes `MTMDChatHandler.get_image_urls` an instance
  method** (upstream has it as a `staticmethod`); every call site inside
  llama-cpp-python is `self.`-bound, so this is safe, but don’t call it
  on the class.
- `read_audio(o, sr=16000)` decodes audio to mono float32 at `sr`
  through soundfile/libsndfile (WAV, FLAC, OGG, and MP3 on libsndfile
  \>= 1.1); anything libsndfile can’t read raises a `ValueError` naming
  the MIME type.
- The tool loop runs in Python (litert runs it in-engine): structured
  `tool_calls` and Hermes/Qwen `<tool_call>` text tags are both parsed,
  each call goes through `approve` (`hitl_policy` works unchanged),
  results are fed back as `role='tool'` messages, up to `max_steps`
  rounds per turn. Tools are python callables (schemas via
  `fastcore.funccall`) or OpenAI tool-spec dicts.
- llama.cpp is stateless per call, so `chat.hist` IS the conversation
  state (no `HistoryCallback`); messages are OpenAI-style dicts.
  Thinking is split from `<think>` tags into `channels.thought` and
  never re-sent.
- `think=True/False` appends `/think` / `/no_think` to the system prompt
  (Qwen-style soft switch); `None` keeps the model default.
- `structured` forces the tool call with a JSON-schema grammar, so
  arguments always parse. No `render()`, `cancel()`, or `bench()`.
- **KV cache.** llama.cpp does prefix reuse itself: `Llama.generate`
  trims its cache to the longest common prefix with the incoming prompt
  and evaluates only the tail, so an ordinary appended turn re-prefills
  nothing. rishi reports what it can as `use.cached_tokens`, and knows
  the three things that break the prefix: a one-shot on the same engine
  (`classify`/`structured`/`check`/`grades`, a shared `engine=`, or a
  `judge=` on the same engine - a `Llama` has one context, so any
  completion overwrites the conversation), a rewritten history (eviction
  or context recovery), and media (the live turn carries the real image,
  later turns carry an `[image]` placeholder, so a media turn forces a
  re-prefill on the next one). `preserve_cache=True` saves and restores
  the llama state around one-shots instead of losing it - a full KV
  copy, so worth it only on big contexts.
  `save_cache(path)`/`load_cache(path)` persist the context to disk,
  same API as `rishi.mlx`.
- `AsyncChat` wraps a `Chat` (pass one, or its kwargs); calls run in a
  worker thread. `await achat(msg)`;
  `async for c in await achat(msg, stream=True)`.

## MLX backend (rishi.mlx)

`pip install 'rishi[mlx]'` (Apple silicon only; `'rishi[mlx-vlm]'` adds
vision/audio). Same `Chat` API over any
[mlx-community](https://huggingface.co/mlx-community) repo:

``` python
from rishi.mlx import MlxChat, qwen3_4b
chat = MlxChat(qwen3_4b, sp='You are concise.', think=False)
print(resp_text(chat("Say hello.")))
print(chat.use)          # cached_tokens > 0 from the second turn on
```

What is different from the other two backends:

- **KV reuse.** LiteRT retains state in its `Conversation`, llama.cpp
  re-renders history but reuses its longest matching KV prefix, and MLX
  explicitly owns and trims its prompt cache. Each turn rishi renders
  the conversation to token ids, compares them against what the cache
  holds (`common_prefix_len`), trims any diverged tail off the cache,
  and prefills only the new tokens. The reuse is reported as
  `use.cached_tokens`. Turn it off with `prompt_cache=False`.
  `save_cache(path)`/`load_cache(path)` persist a warmed cache, so a
  long system prompt can be prefilled once and reused in later sessions.
- Comparing tokens (rather than trusting the cache) is what makes an
  edited history safe: a chat template need not re-render an assistant
  turn as the tokens the model generated, and context recovery rewrites
  history outright. A mismatch just costs a re-prefill.
- `Chat(model=None, *, runtime=None, model_path=None, vlm=None, engine=None, adapter_path=None, draft_model=None, eng_kw=None, sp='', messages=None, tools=None, ctx_limit=None, approve=None, tool_max_len=None, max_steps=10, parallel_tools=False, final_prompt=..., think=None, temp=None, top_k=None, top_p=None, min_p=None, seed=None, max_output_tokens=1024, prompt_cache=True, max_kv_size=None, kv_bits=None, kv_group_size=64, quantized_kv_start=0, tmpl_kw=None, gen_kw=None, cbs=None, default_cbs=True)` -
  `model` is positional; there is no `model_id=` keyword. Model ids:
  `qwen3_06b`, `qwen3_17b`, `qwen3_4b`, `qwen3_8b`, `qwen3_30b`,
  `gemma3_4b`, `llama32_3b`, `qwen3vl_4b` (vision), `gemma4_e4b`
  (vision + audio, ~5GB), `qwen3omni_30b` (audio in, ~22GB).
- `kv_bits=4` quantizes the KV cache (with `kv_group_size`,
  `quantized_kv_start`) for long contexts. `draft_model=qwen3_06b` turns
  on speculative decoding. `adapter_path='./adapters'` applies a LoRA
  adapter at load time.
- Tools come back as `<tool_call>{json}</tool_call>` text (mlx-lm has no
  built-in parser), which rishi parses with the same `StreamSplit` llama
  uses. Thinking is `<think>` tags; `think=True/False` is passed to the
  chat template as `enable_thinking`, which Qwen3-style templates read.
- `structured` has no grammar constraint on this backend: it asks for
  JSON and parses the reply (fenced
  \`\``json first, then the outermost braces), raising`ValueError`if neither works.`classify`,`check`and`grades\`
  work as elsewhere.
- **Vision and audio** route automatically: `Chat` reads the repo’s
  `config.json`, and a model with a vision/audio tower gets `MlxVlmChat`
  (mlx-vlm) instead. Force it with `vlm=True`/`False`. Pass media as
  `bytes` or a `Path` in the message list, exactly as on llama. Two
  caveats: mlx-vlm has no per-model tool-call parsers, so tool use there
  depends on the model emitting `<tool_call>` tags, and it manages its
  own vision-feature cache, so cross-turn token prefix reuse is off on
  that path. A text-only MLX model raises a `TypeError` pointing at
  `rishi[mlx-vlm]` rather than silently dropping the image.
- **Audio in**: `chat([Path('speech.wav'), 'Transcribe this audio.'])`
  on a model with an audio tower (`gemma4_e4b`, `qwen3omni_30b`).
  mlx-vlm decodes the file and resamples it to the model’s own
  feature-extractor rate, so don’t pass `sampling_rate` yourself. rishi
  also passes its own `think` to mlx-vlm’s chat template rather than
  letting mlx-vlm default to `enable_thinking=False`: that default
  prefills an empty `<think></think>` block, and a model handed a
  finished thought can end the turn immediately - Qwen3-Omni transcribes
  nothing at all when it happens.

## Hosted models (rishi.remote)

[fastllm](https://github.com/AnswerDotAI/fastllm) is installed by
default; set the vendor’s key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, …)
to use the same `Chat` API against Anthropic, OpenAI, Gemini, DeepSeek,
Moonshot, OpenRouter and the rest:

``` python
from rishi import Chat
chat = Chat('claude-sonnet-4-5', sp='You are concise.')
print(resp_text(chat("Say hello.")))
```

- `Chat(model, *, api_key=None, base_url=None, vendor_name=None, api_name=None, sp='', messages=None, tools=None, approve=None, tool_max_len=None, max_steps=10, parallel_tools=False, tool_choice=None, reasoning_effort=None, temp=None, max_output_tokens=4096, retries=2, comp_kw=None, cbs=None, default_cbs=True)`.
- It rides the same `ToolLoopMixin` as llama and mlx, so approval, the
  budget, `parallel_tools`, callbacks and `PyFenceCallback` behave
  identically. The wire call is async (`fastllm.acomplete`), bridged to
  the sync API with `run_coro` and `sync_iter`.
- **`tool_choice`** (`'auto'`/`'required'`/`'none'`, or a tool name) and
  **`reasoning_effort`** (`'low'`/`'medium'`/`'high'`) are passed
  straight through - hosted APIs support both natively, unlike the local
  backends.
- **Server-side tools** (a provider-run web search) come back with
  `server=True` on the `ToolCall`. The tool loop records them and never
  executes anything locally.
- History conversion is `to_msg`/`to_hist` between rishi’s canonical
  dicts and fastllm’s `Msg`/`Part`. Text, thinking, tool calls, tool
  results, images and audio all round-trip - media is carried as a data
  URL rather than collapsed to a placeholder, so a local -\> hosted hop
  keeps the picture.
- `structured` forces the tool call (`tool_choice=<name>`), so arguments
  parse reliably; it falls back to parsing a JSON reply.
- `chat.use` gets `cached_tokens` from the provider’s prompt-cache
  accounting, the same field MLX fills from prefix reuse, so a mixed
  local/hosted tally adds up in one `UsageStats`. `close()` is a no-op:
  the HTTP client belongs to fastllm.

## Working on rishi itself

It’s an nbdev project. Edit `nbs/00_core.ipynb`, `nbs/01_llama.ipynb`,
`nbs/02_litert.ipynb`, `nbs/03_mlx.ipynb` or `nbs/04_remote.ipynb`, not
the generated files in `rishi/`. Tests are non-exported `#| hide` cells;
model-dependent cells are `#| eval: false` to keep the test run offline.
`nbs/03_mlx.ipynb` is additionally marked `skip_exec: true` in its
frontmatter, because CI runs on linux where MLX doesn’t exist - run it
on a Mac. Run `nbdev-prepare` (with a hyphen) after changes.

The tool loop itself lives once, in `rishi.core.ToolLoopMixin`: a
backend that receives tool calls as data (llama, mlx) supplies
`_model_step` and `_stream_step` plus an `ns` tool namespace, and the
mixin owns approval, history, the budget, parallel dispatch and context
recovery. litert runs its loop inside the engine and bridges back
through `ChatToolHandler` instead. `rishi.remote`’s tests patch
`acomplete` with a fake, so the whole backend - conversions, tool loop,
budget, streaming - is covered in CI without a key.

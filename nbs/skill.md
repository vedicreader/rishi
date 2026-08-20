---
name: rishi
description: Run models through rishi's one Chat API. Local engines are Gemma .litertlm over litert_lm (rishi.litert), any GGUF over llama-cpp-python (rishi.llama), quantized models on Apple silicon over MLX (rishi.mlx) and anything an Ollama daemon serves (rishi.ollama). Hosted ones are vendor APIs over fastllm (rishi.remote), Claude Code (rishi.claude) and GitHub Copilot (rishi.copilot). All of them share tool calling with human approval, a tool-call budget, streaming, thinking, a python sandbox, structured output, classification and graded answers. Use when writing or debugging offline LLM chat, local tool-use agents, or anything mentioning rishi, litert_lm, gemma .litertlm models, local GGUF/llama.cpp chat, mlx-lm/mlx-vlm, ollama, Claude Code or GitHub Copilot.
---

# rishi

rishi wraps seven backends in one callable `Chat`. Four are on-device, and need no API key and no network once weights are cached. The backend-agnostic API lives in `rishi.core`. The local engines are `rishi.litert` (Gemma `.litertlm` over litert_lm), `rishi.llama` (any GGUF over llama-cpp-python), `rishi.mlx` (Apple silicon over mlx-lm and mlx-vlm) and `rishi.ollama` (whatever a local Ollama daemon serves). The hosted ones are `rishi.remote` for vendor APIs over fastllm, plus `rishi.claude` and `rishi.copilot`. `Chat(model)` picks one from the model name.

The core install is small, and every runtime is an extra: `rishi[litert]`, `rishi[llama]`, `rishi[mlx]`, `rishi[ollama]`, `rishi[remote]`, `rishi[claude]`, `rishi[copilot]`, or `rishi[all]` for everything your platform supports. Backend modules load lazily, and asking for one without its extra raises an ImportError naming it.

## The one thing to remember

`chat(msg)` returns litert's response wrapped in `Resp`, not a string. Pull text with `resp_text(r)`. In a notebook `r` renders itself as markdown, with thinking, text and tool calls. When streaming, you iterate markdown chunks instead.

```python
from rishi.core import Chat, resp_text
chat = Chat()                       # downloads gemma-4-E2B once, then loads from cache
r = chat("Say hello.")
print(resp_text(r))
```

`Chat()` builds an engine and a conversation. Each call runs one turn, appends to `chat.hist`, and updates `chat.use`. Calling again continues the same conversation (litert holds the KV cache).

## API surface

- `Chat(model=None, *, runtime=None, model_path=None, engine=None, backend=Backend.CPU(), multimodal=True, cache_dir=None, sp='', messages=None, tools=None, ctx_limit=None, approve=None, tool_max_len=None, think=False, filter_think=True, temp=None, top_k=None, top_p=None, seed=None, sampler_config=None, max_output_tokens=None, cbs=None, default_cbs=True)` . `model` comes first, as a repo id or local path. `Chat` dispatches by `runtime` and model shape, and returns a `LitertChat`, `LlamaChat`, `MlxChat`, `OllamaChat`, `RemoteChat`, `ClaudeChat` or `CopilotChat`. The litert-specific kwargs are shown here. llama adds `quant`, `n_ctx`, `n_gpu_layers`, `mmproj` and `comp_kw`, and mlx and the hosted backends have their own, in their sections.
- `chat(msg=None, stream=False, max_output_tokens=None, cbs=None)` runs a turn. `stream=True` returns a generator of markdown chunks. `cbs=` registers callbacks for that turn only.
- State: `chat.hist` (Python-visible history, print with `chat.print_hist()`), `chat.use` (a `UsageStats`: `total`, `in`, `out`, `turns`), `chat.token_count` (live context size), `chat.pct_full` (that over `ctx_limit`).
- Chat methods: `run_py(code)`, `classify(text, labels)`, `structured(prompt, schema)`, `check(question, expected, ...)`, `grades(question, expected, actual)`, `count_tokens(text)`, `render(msg)`, `cancel()`, `add_cb`/`add_cbs`/`remove_cb`/`remove_cbs`, `close()`.
- `create_engine(...)` is a classmethod on each backend class (`LitertChat.create_engine`, `LlamaChat.create_engine`, `MlxChat.create_engine`) that builds the engine (resolves the model, makes `cache_dir`, wires multimodal backends). `rishi.core.Chat` has none, so patch the backend's or pass `engine=` to override. The hosted backends have no engine to build.
- Module helpers: `resp_text`, `thought`, `display_stream`, `hitl_policy`, `output_matches`, `task_complete`, `bench`. Model ids: `gemma4_e2b`, `gemma4_e4b`, `gemma4_12b`. The message builders (`mk_msg`/`mk_content`/`mk_msgs`) and model resolver are backend-specific, so reach them per backend as `chat.mk_msg(...)` / `LitertChat.mk_msg` rather than as a bare `from rishi import *` name (both backends define their own, so they aren't re-exported at the top level).
- Callbacks: `ChatCallback` (base), `PyFenceCallback`, and `TruncationCallback` are public in `rishi.core`, along with the shared `UsageCallback`/`ToolReminderCallback` that llama and mlx use as defaults. litert's history/usage callbacks are internal. All defaults are on unless you pass `default_cbs=False`.
- Tool-call budget: `max_steps` (default 10) caps tool *calls* per turn on every backend. Past the cap, calls are denied with `budget_msg_`, and rishi sends `final_prompt` asking the model to answer with what it has, so a runaway loop ends in prose. `max_steps=None` removes the cap.
- `parallel_tools=True` runs independent calls from one turn concurrently, on llama and mlx. litert raises `NotImplementedError`. Approval stays sequential, so HITL order and budget accounting don't change, and history is identical either way.
- Context recovery: if the window fills mid-turn, rishi truncates the oldest tool results, rebuilds backend state, and asks for a summary. `ContextWindowExceededError` is raised only if that retry also fails.
- `SlidingWindowCallback(threshold=0.9, keep_first=2, keep_last=8, summarize=False)` is the *proactive* version and works on every backend. Before each turn it checks `pct_full`, and if the context is nearly full it drops whole message groups from the **middle** of `hist`, keeping the earliest turns and the live thread, then calls `chat._recreate_conv()` so the backend rebuilds from the shortened history. It needs `ctx_limit` set, and no-ops without one. `evict_middle` and `msg_groups` are exported if you want the policy without the callback. A tool call and its results are one group and are never split. Opt in with `Chat(cbs=[SlidingWindowCallback()])`, because eviction is lossy and so is not a default. `summarize=True` spends one model call to replace the dropped middle with a summary.
- This matters most on **litert**, whose KV cache has no automatic recycling upstream ([gallery#856](https://github.com/google-ai-edge/gallery/issues/856)): a full cache OOMs on GPU/NPU and makes the CPU path repeat itself forever, rather than raising cleanly. litert now also evicts and retries once reactively, and its system prompt lives outside `hist` so a rebuild always re-applies it.
- `chat.use` is a `UsageStats` with `prompt_tokens`, `completion_tokens`, `total_tokens`, `n`, `cached_tokens` (prompt tokens served from the backend's KV/prefix cache), plus `cost`/`model` for merging with hosted-API usage.
- Streaming has two modes: `chat(msg, stream=True)` yields **markdown strings** (print them, or hand to `display_stream`); `chat(msg, stream='raw')` yields the underlying **chunk dicts** (`{'content': [{'type': 'text', ...}]}`, `{'channels': {'thought': ...}}`, `{'content': [{'type': 'tool_call', ...}]}`) for programmatic consumers that want structure rather than rendered text. Both run the same tool loop.
- `ToolCall(name, arguments, id=None, server=False)` builds a canonical tool call. It is a `dict` subclass, so indexing still works, with `.name`, `.arguments` and `.server` accessors. A call with `server=True` is one the *provider* runs, and the tool loop records it and never executes it locally. `mk_tool_res_msg(tc, result)` and `mk_tool_res_msgs(tcs, results)` build the `role='tool'` reply messages, if you're driving a loop by hand.

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

Modes are `approved` (run), `dont_run` (block), `check` (ask on the console). In a Leela web IDE kernel, `hitl_policy(modes, browser=True)` sends checked calls to Leela's browser approval card instead of calling `input()`. Use `browser='http://host:port'` or set `LEELA_URL` when needed. `browser_approval(url=None, timeout=300)` is also available as a standalone callback. A blocked call is recorded as "Denied by human operator" and reported to the model. For custom logic, pass your own function. `ChatToolHandler` routes calls through `approve` and writes calls and results into `hist`.

## Running python from replies

`PyFenceCallback` makes the chat a code interpreter: it runs the last ```python fence through a sandbox (`safepyrun`, so `socket`/`importlib` are blocked), feeds the output back as a ```result block, and loops until the model answers in prose or `done(chat)` is true, capped by `max_rounds`.

```python
from rishi.core import PyFenceCallback, output_matches
chat = Chat(cbs=[PyFenceCallback], sp="Use a ```python fence to compute the answer, then reply in prose.")
chat("What is 2**100?")
chat("Sort [3,1,2] and print it.", cbs=[PyFenceCallback(done=output_matches('[1, 2, 3]'))])
```

`done` is any `chat -> bool`. `output_matches(expected)` stops once `chat.turn_code_out` contains the expected value, and `task_complete` asks the model. Execution goes through the same `approve` gate as a tool. `chat.run_py(code)` runs a snippet directly in the chat's persistent namespace.

## Structured output, classification, and grading

These run one-shot in a throwaway conversation on the same engine, so they leave the live chat untouched.

```python
from dataclasses import dataclass
@dataclass
class Person: name: str; age: int
chat.structured("John Smith is 30.", Person)          # -> Person(name='John Smith', age=30)
chat.classify("I loved it!", ['positive','negative']) # -> 'positive'

chat.check("Capital of France?", "Paris").ok           # deterministic match -> True
judge = Chat(gemma4_12b, multimodal=False, cache_dir='.cache/litertlm')
chat.check("Name a primary colour.", "red, blue, or yellow", judge=judge).ok  # graded by a bigger model
```

`check` extracts the answer from a ```answer fence and grades it. Default grade is `grade_fn(answer, expected)` (`matches_`, a contains check). Pass `llm_judge=True` or a `judge=` chat to grade with a model, or your own `grade_fn`. It returns `AttrDict(question, expected, answer, ok)`.

## Callbacks

Subclass `ChatCallback`, hook `before_send`, `after_response`, `before_tool_calls`, or `after_tool_calls`, and read turn state off the chat (`self.turn_res` is `chat.turn_res`). `order` sets when it runs, and the backend's built-in history and usage callbacks sit at the front, on a low `order`. Register with `chat.add_cb(MyCb)` or `Chat(cbs=[...])`, run one for a single turn with `chat(msg, cbs=[...])`, and drop one with `chat.remove_cb(MyCb)` (by instance or class). The defaults are on unless you pass `default_cbs=False`.

## Sharing a model

Loading costs seconds and gigabytes. Build one engine and reuse it:

```python
from rishi.litert import LitertChat
eng = LitertChat.create_engine(cache_dir='.cache/litertlm')      # `create_engine` is per backend
a, b = Chat(engine=eng), Chat(engine=eng)
```

A Chat that built its own engine frees it on `close()`. A Chat handed an engine leaves it alone, so siblings keep working.

## Gotchas

- Model files: a repo can ship both a native `.litertlm` and a `-web` build. The web build has no CPU/GPU decode graph and fails with `TF_LITE_PREFILL_DECODE not found`. rishi's model resolver already prefers the native one.
- GPU needs a writable `cache_dir`. Without it you get `Could not open ... mldrift_weight_cache.bin: No such file or directory`. `create_engine` makes the directory for you when you pass `cache_dir`.
- The log line `WebGPU sampler not available, falling back to statically linked C API` is harmless. Quiet the noise with `set_min_log_severity(3)`.
- Tool and structured-output arguments arrive as floats (`21.0`) from the model's JSON. Cast inside the tool if you need strict ints.
- `run_text_scoring` is not available on this runtime, so `classify` and `check` grade by generation, not log-likelihood scoring.
- TLS behind a re-signing corporate proxy: `certifi` does not know the proxy's root certificate and every hosted backend fails with `CERTIFICATE_VERIFY_FAILED`. Importing rishi calls `use_system_certs()`, which verifies against the OS trust store through `truststore`; `RISHI_SYSTEM_CERTS=0` turns it off. It covers what Python dials (`remote`, `copilot`), not what a separate binary does: Claude Code and the Ollama daemon carry trust stores of their own.

## One interface for every backend

`Chat` picks the backend from the model name, fastllm-style, and returns that backend's own `Chat` subclass: `LitertChat`, `LlamaChat`, `MlxChat`, `RemoteChat`, `ClaudeChat` or `CopilotChat`. It is a real subclass, not a wrapper, so `isinstance(chat, Chat)` holds and `chat.runtime` says which one you got. Callbacks, tools, `hist`, `use` and streaming are exactly as documented per backend. `**kw` passes straight through, so backend-specific arguments such as `backend=Backend.GPU()`, `mmproj=`, `n_gpu_layers=` and `kv_bits=` still work.

```python
from rishi import Chat, AsyncChat

Chat('litert-community/gemma-4-E2B-it-litert-lm')   # -> litert
Chat('Qwen/Qwen3-4B-GGUF')                          # -> llama.cpp
Chat('mlx-community/Qwen3-4B-4bit')                 # -> mlx
Chat('mlx-community/Qwen3-VL-4B-Instruct-4bit')     # -> mlx, and on to MlxVlmChat (vision)
Chat('ollama/qwen3:4b')                             # -> ollama (prefix only for a bare id)
Chat('hf.co/Qwen/Qwen3-4B-GGUF:Q4_K_M')             # -> ollama (only Ollama addresses hf.co)
Chat('claude-sonnet-4-5')                           # -> remote (hosted, via fastllm)
Chat('claude/claude-sonnet-5')                      # -> claude (Claude Code, prefix only)
Chat('copilot/gpt-4.1')                             # -> copilot (GitHub Copilot, prefix only)
Chat('openrouter/moonshotai/kimi-k2')               # vendor-prefixed hosted names work too
Chat('/models/mine.gguf')                           # local file -> model_path=
Chat('my-org/private', runtime='llama')             # explicit wins
Chat('llama/my-org/private')                        # or prefix the name
Chat()                                              # nothing to go on -> litert, as before
achat = AsyncChat('Qwen/Qwen3-4B-GGUF')             # async on any backend
```

Resolution order: an explicit `runtime=`, then a `runtime/` prefix if it names a known runtime, so `litert-community/...` is left alone, then the shape of the id or path, then the default of `litert`. The shapes are `.litertlm`, `litert-community` and `litert-lm` against `.gguf` and `GGUF` against `mlx-community` and `-mlx` against hosted names like `claude-*`, `gpt-*` and `gemini-*`. Local shapes are checked before hosted name patterns. `hf.co/...` means ollama, and is checked before `.gguf`. Three things are never inferred, and need a prefix. `claude` and `copilot` serve models under names the hosted vendors also use. A bare Ollama id like `qwen3:4b` has a `name:tag` shape, which is also how Windows spells a path. A bare name rishi cannot place raises with instructions rather than guessing. There is no alias table, so pass a full hub repo id or path. `resolve_runtime`, `split_runtime`, `infer_runtime` and `get_runtime` are exported if you want the decision without building anything.

The selector is `runtime=`, not `backend=`. `backend=` stays free for litert's hardware backend, `Backend.GPU()`, which passes straight through.

## llama.cpp backend (rishi.llama)

`pip install 'rishi[llama]'` (adds llama-cpp-python). Same `Chat` API over any GGUF repo on the HuggingFace Hub, plus an `AsyncChat`:

```python
from rishi.llama import Chat, AsyncChat, resp_text, qwen3_4b

chat = Chat(qwen3_4b, think=False)               # or model_path='path/to/model.gguf'
r = chat("Say hello.")
print(resp_text(r))

achat = AsyncChat(chat)                          # or AsyncChat(model) to build its own
r = await achat("Again?")
async for c in await achat("Stream it.", stream=True): print(c, end='')
```

Differences from the litert backend:

- `Chat(model=None, *, runtime=None, model_path=None, engine=None, quant='Q4_K_M', n_ctx=8192, n_gpu_layers=0, mmproj=None, eng_kw=None, sp='', messages=None, tools=None, ctx_limit=None, approve=None, tool_max_len=None, max_steps=10, parallel_tools=False, final_prompt=..., think=None, temp=None, top_k=None, top_p=None, seed=None, preserve_cache=False, max_output_tokens=None, comp_kw=None, cbs=None, default_cbs=True)`. `model` is positional, as a repo id or a local path, and there is no `model_id=` keyword. The model ids are `qwen3_06b`, `qwen3_17b`, `qwen3_4b`, `gemma3_1b` and `gemma3_4b`. `quant` picks the `.gguf` file from the repo. `n_gpu_layers=-1` offloads everything to GPU.
- Images and audio: a multimodal GGUF needs an `mmproj` projector alongside the model. `Chat(gemma3_4b, mmproj=True)` resolves it from the same repo, cache-first as the model lookup is, and `get_mmproj` does it standalone. Or pass an explicit path. That builds llama.cpp's `MTMDChatHandler`. Then pass `bytes` or a `Path` in the message list: `chat(['Describe this.', Path('cat.jpg')])`, `chat(['Transcribe this.', Path('clip.wav')])`, or both in one turn (each becomes a media marker in document order).
- Audio works because rishi `@patch`es `MTMDChatHandler`, which upstream wires for images only: `get_image_urls` also collects `input_audio` parts, `_get_template_messages` maps them to the media marker, `_create_bitmap_from_bytes` routes audio to `mtmd_bitmap_init_from_audio`, and `_init_mtmd_context` stops rejecting audio-only projectors. Images keep the original code path. **Note this makes `MTMDChatHandler.get_image_urls` an instance method** (upstream has it as a `staticmethod`); every call site inside llama-cpp-python is `self.`-bound, so this is safe, but don't call it on the class.
- `read_audio(o, sr=16000)` decodes audio to mono float32 at `sr` through soundfile/libsndfile (WAV, FLAC, OGG, and MP3 on libsndfile >= 1.1); anything libsndfile can't read raises a `ValueError` naming the MIME type.
- The tool loop runs in Python (litert runs it in-engine): structured `tool_calls` and Hermes/Qwen `<tool_call>` text tags are both parsed, each call goes through `approve` (`hitl_policy` works unchanged), results are fed back as `role='tool'` messages, up to `max_steps` rounds per turn. Tools are python callables (schemas via `fastcore.funccall`) or OpenAI tool-spec dicts.
- llama.cpp is stateless per call, so `chat.hist` IS the conversation state (no `HistoryCallback`); messages are OpenAI-style dicts. Thinking is split from `<think>` tags into `channels.thought` and never re-sent.
- `think=True/False` appends `/think` / `/no_think` to the system prompt (Qwen-style soft switch); `None` keeps the model default.
- `structured` forces the tool call with a JSON-schema grammar, so arguments always parse. No `render()`, `cancel()`, or `bench()`.
- **KV cache.** llama.cpp does prefix reuse itself. `Llama.generate` trims its cache to the longest common prefix with the incoming prompt and evaluates only the tail, so an ordinary appended turn re-prefills nothing. rishi reports what it can as `use.cached_tokens`, and knows the three things that break the prefix. First, a one-shot on the same engine, which means `classify`, `structured`, `check`, `grades`, a shared `engine=`, or a `judge=` on the same engine. A `Llama` has one context, so any completion overwrites the conversation. Second, a rewritten history, from eviction or context recovery. Third, media: the live turn carries the real image and later turns carry an `[image]` placeholder, so a media turn forces a re-prefill on the next one. `preserve_cache=True` saves and restores the llama state around one-shots instead of losing it. That is a full KV copy, so it is worth it only on big contexts. `save_cache(path)` and `load_cache(path)` persist the context to disk, through the same API as `rishi.mlx`.
- `AsyncChat` wraps a `Chat`, taking one or its kwargs, and calls run in a worker thread. Use `await achat(msg)`, or `async for c in await achat(msg, stream=True)`.

## MLX backend (rishi.mlx)

`pip install 'rishi[mlx]'`, on Apple silicon only, and `'rishi[mlx-vlm]'` adds vision and audio. The same `Chat` API over any [mlx-community](https://huggingface.co/mlx-community) repo:

```python
from rishi.mlx import MlxChat, qwen3_4b
chat = MlxChat(qwen3_4b, sp='You are concise.', think=False)
print(resp_text(chat("Say hello.")))
print(chat.use)          # cached_tokens > 0 from the second turn on
```

What is different from the other two backends:

- **KV reuse.** LiteRT retains state in its `Conversation`, llama.cpp re-renders history but reuses its longest matching KV prefix, and MLX explicitly owns and trims its prompt cache. Each turn rishi renders the conversation to token ids, compares them against what the cache holds (`common_prefix_len`), trims any diverged tail off the cache, and prefills only the new tokens. The reuse is reported as `use.cached_tokens`. Turn it off with `prompt_cache=False`. `save_cache(path)`/`load_cache(path)` persist a warmed cache, so a long system prompt can be prefilled once and reused in later sessions.
- Comparing tokens (rather than trusting the cache) is what makes an edited history safe: a chat template need not re-render an assistant turn as the tokens the model generated, and context recovery rewrites history outright. A mismatch just costs a re-prefill.
- `Chat(model=None, *, runtime=None, model_path=None, vlm=None, engine=None, adapter_path=None, draft_model=None, eng_kw=None, sp='', messages=None, tools=None, ctx_limit=None, approve=None, tool_max_len=None, max_steps=10, parallel_tools=False, final_prompt=..., think=None, temp=None, top_k=None, top_p=None, min_p=None, seed=None, max_output_tokens=1024, prompt_cache=True, max_kv_size=None, kv_bits=None, kv_group_size=64, quantized_kv_start=0, tmpl_kw=None, gen_kw=None, cbs=None, default_cbs=True)`. `model` is positional, and there is no `model_id=` keyword. The model ids are `qwen3_06b`, `qwen3_17b`, `qwen3_4b`, `qwen3_8b`, `qwen3_30b`, `gemma3_4b`, `llama32_3b`, `qwen3vl_4b` for vision, `gemma4_e4b` for vision and audio at about 5GB, and `qwen3omni_30b` for audio in at about 22GB.
- `kv_bits=4` quantizes the KV cache (with `kv_group_size`, `quantized_kv_start`) for long contexts. `draft_model=qwen3_06b` turns on speculative decoding. `adapter_path='./adapters'` applies a LoRA adapter at load time.
- Tools come back as `<tool_call>{json}</tool_call>` text (mlx-lm has no built-in parser), which rishi parses with the same `StreamSplit` llama uses. Thinking is `<think>` tags. `think=True` or `think=False` is passed to the chat template as `enable_thinking`, which Qwen3-style templates read.
- `structured` has no grammar constraint on this backend: it asks for JSON and parses the reply (fenced ```json first, then the outermost braces), raising `ValueError` if neither works. `classify`, `check` and `grades` work as elsewhere.
- **Vision and audio** route automatically: `Chat` reads the repo's `config.json`, and a model with a vision/audio tower gets `MlxVlmChat` (mlx-vlm) instead. Force it with `vlm=True`/`False`. Pass media as `bytes` or a `Path` in the message list, exactly as on llama. Two caveats: mlx-vlm has no per-model tool-call parsers, so tool use there depends on the model emitting `<tool_call>` tags, and it manages its own vision-feature cache, so cross-turn token prefix reuse is off on that path. A text-only MLX model raises a `TypeError` pointing at `rishi[mlx-vlm]` rather than silently dropping the image.
- **Audio in**: `chat([Path('speech.wav'), 'Transcribe this audio.'])` on a model with an audio tower (`gemma4_e4b`, `qwen3omni_30b`). mlx-vlm decodes the file and resamples it to the model's own feature-extractor rate, so don't pass `sampling_rate` yourself. rishi also passes its own `think` to mlx-vlm's chat template rather than letting mlx-vlm default to `enable_thinking=False`. That default prefills an empty `<think></think>` block, and a model handed a finished thought can end the turn immediately. Qwen3-Omni transcribes nothing at all when it happens.

## Ollama backend (rishi.ollama)

`pip install 'rishi[ollama]'`. Ollama is a server, not a library, so this backend drives the daemon as well as the conversation. `Chat('ollama/qwen3:4b')` on a machine with no Ollama installs it under `~/.cache/rishi/ollama`, starts `ollama serve`, pulls the model, and answers. It stops the daemon at interpreter exit. A daemon already listening is left alone.

```python
from rishi import Chat
from rishi.ollama import ensure_ollama, OllamaServer, install_ollama, stop_ollama, qwen3_4b

chat = Chat(f'ollama/{qwen3_4b}', think='low', n_ctx=8192, sp='You are concise.')
cl = ensure_ollama()                       # the daemon itself
print(cl.version(), cl.models(), cl.ps())
cl.pull('gemma3:4b', on_progress=print)    # streamed progress records
```

- `OllamaChat(model=None, *, host=None, client=None, quant='Q4_K_M', pull=True, install=True, serve=True, srv_kw=None, on_progress=None, n_ctx=None, n_gpu_layers=None, keep_alive=None, options=None, sp='', messages=None, tools=None, ctx_limit=None, approve=None, tool_max_len=None, max_steps=10, parallel_tools=False, final_prompt=..., think=None, temp=None, top_k=None, top_p=None, seed=None, max_output_tokens=None, comp_kw=None, cbs=None, default_cbs=True)`. Model ids are `qwen3_06b`, `qwen3_17b`, `qwen3_4b`, `gemma3_1b`, `gemma3_4b` and `llama32_3b`, or any id from Ollama's library.
- **Model ids.** `ollama_model` maps a hub GGUF repo onto `hf.co/<repo>:<quant>`, so `Chat('Qwen/Qwen3-4B-GGUF', runtime='ollama')` and the llama backend take the same id. A local `.gguf` path raises, naming `runtime='llama'`: Ollama serves only what is in its own store.
- **Thinking** is a request field, not a system-prompt switch: `think=True/False`, or `'low'`, `'medium'`, `'high'`, `'max'`. A model with no thinking refuses it, so rishi drops the field, retries once, and stops sending it for that chat.
- **Sampling.** `n_ctx` and `n_gpu_layers` keep their llama names and go out as `num_ctx` and `num_gpu`. `temp`, `top_k`, `top_p`, `seed` and `max_output_tokens` map onto the rest of `options`, and anything else goes in `options=`. `keep_alive=` sets how long the model stays resident. `chat.unload()` frees it now.
- **`structured`** uses Ollama's own `format` with the JSON schema, so arguments parse. `classify`, `check` and `grades` work as elsewhere.
- **The daemon.** `OllamaServer(host=None, bin=None, dir=OLLAMA_DIR, models=None, n_ctx=None, keep_alive=None, flash_attn=None, kv_cache_type=None, num_parallel=None, max_loaded=None, log=None)` wraps `ollama serve` and its environment variables. `install_ollama()` unpacks the release archive for this user with no root. `ensure_ollama()` returns a client, starting one if needed. `stop_ollama()` ends whatever rishi started. `OllamaClient` covers `/api/chat`, `/api/tags`, `/api/show`, `/api/ps`, `/api/pull` and `/api/delete`.
- **`model_caps(model, runtime='ollama')`** asks `/api/show`, so it reports what the daemon knows rather than guessing from file names, and comes back with `source='runtime'`.
- **Not available here:** audio in, since Ollama carries images only. `save_cache`/`load_cache` and a real `cached_tokens`, since the KV cache lives in the daemon behind no handle. An exact `count_tokens` before a turn, since there is no tokenizer endpoint. The true count arrives in `use`. There is no broker either, because the daemon already is one. Size it with `OLLAMA_NUM_PARALLEL` and `OLLAMA_MAX_LOADED_MODELS`.

## Hosted models (rishi.remote)

Install `rishi[remote]` for [fastllm](https://github.com/AnswerDotAI/fastllm), then set the vendor's key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and so on) to use the same `Chat` API against Anthropic, OpenAI, Gemini, DeepSeek, Moonshot, OpenRouter and the rest:

```python
from rishi import Chat
chat = Chat('claude-sonnet-4-5', sp='You are concise.')
print(resp_text(chat("Say hello.")))
```

- `Chat(model, *, api_key=None, base_url=None, vendor_name=None, api_name=None, sp='', messages=None, tools=None, approve=None, tool_max_len=None, max_steps=10, parallel_tools=False, tool_choice=None, reasoning_effort=None, temp=None, max_output_tokens=4096, retries=2, comp_kw=None, cbs=None, default_cbs=True)`.
- It rides the same `ToolLoopMixin` as llama and mlx, so approval, the budget, `parallel_tools`, callbacks and `PyFenceCallback` behave identically. The wire call is async (`fastllm.acomplete`), bridged to the sync API with `run_coro` and `sync_iter`.
- **`tool_choice`** (`'auto'`, `'required'`, `'none'`, or a tool name) and **`reasoning_effort`** (`'low'`, `'medium'`, `'high'`) are passed straight through. Hosted APIs support both natively, unlike the local backends.
- **Server-side tools** (a provider-run web search) come back with `server=True` on the `ToolCall`. The tool loop records them and never executes anything locally.
- History conversion is `to_msg` and `to_hist`, between rishi's canonical dicts and fastllm's `Msg` and `Part`. Text, thinking, tool calls, tool results, images and audio all round-trip. Media is carried as a data URL rather than collapsed to a placeholder, so a local to hosted hop keeps the picture.
- `structured` forces the tool call with `tool_choice=<name>`, so arguments parse reliably. It falls back to parsing a JSON reply.
- `chat.use` gets `cached_tokens` from the provider's prompt-cache accounting, the same field MLX fills from prefix reuse, so a mixed local and hosted tally adds up in one `UsageStats`. `close()` is a no-op, because the HTTP client belongs to fastllm.

## Claude Code (rishi.claude)

`rishi[claude]`, plus Claude Code on `$PATH` and one `claude /login`. This is an agent with its own harness, not a completion endpoint: one turn is one `query()` on a live session, and rishi drives the binary as a subprocess without ever reading your credentials. `ClaudeChat.local` is `False`.

```python
from rishi import Chat
from rishi.claude import ClaudeChat, sonnet5, CLAUDE_SERVER_TOOLS

chat = Chat('claude/claude-sonnet-5', sp='You are concise.')   # or ClaudeChat(sonnet5)
```

- Tools never travel as MCP. Claude Code declares a caller's tools as an in-process MCP server, and an organisation-managed configuration forbids every dynamic MCP server there is, which would leave the model with no tools at all. rishi opens none, and the schemas go out as `<tool_call>` tags in the system prompt, which `parse_tool_tags` reads back. `chat.tool_channel` is `'tags'`. Never claim `strict_mcp_config=True` either: a managed machine refuses that flag outright.
- The conversation travels as a session transcript. `anth_msgs` turns `hist` into Anthropic messages, `llmsurgery` writes them as records under `CLAUDE_WORK_DIR` (`~/.rishi-claude`), and the turn resumes that id. So the model reads real messages: an `image` block for a picture, `document` for a PDF, and a `tool_use` answered by the `tool_result` that carries its id. `transcript=False`, or no `llmsurgery`, falls back to one flattened prompt, which carries no media.
- `stateful=True` (default) keeps one Claude Code session per chat: one subprocess for the whole conversation, and a mid-turn tool result goes up as text, since a live session takes user turns. `stateful=False` files every turn as records instead, at one subprocess each. Fast against faithful.
- `workspace=` names the directory Claude Code works in, and is where its transcripts are then filed. Unset means `CLAUDE_WORK_DIR`, to keep synthesized records out of a real project's history; `workspace='.'` opts back in.
- Claude Code's own tools are off. `claude_disallowed` is `('Bash', 'Write', 'Edit', 'NotebookEdit')` and `tools=[]` goes out whenever this chat carries tools of its own. `claude_tools=` allowlists some back. `claude_server_tools=CLAUDE_SERVER_TOOLS` is the exception worth having: `WebSearch` and `WebFetch` run on Claude Code's side, so they need no schema and never reach rishi's tool loop.
- An ambient `ANTHROPIC_API_KEY` is blanked for the subprocess: it would silently turn a subscription session into a metered API one. `api_key=True` allows it.
- `chat.use.cost` is what Claude Code itself reported for the turn, not a price table, and `cached_tokens`/`cache_creation_tokens` come straight off its usage block. Claude Code's own system prompt adds 48k to 53k prompt tokens per turn, most of it a cache read.
- A failed turn raises `ClaudeError`, a `RuntimeError` carrying `.status` (429, 529, ...) and the raw `.raw` result, so a caller can tell a rate limit from a bad prompt. A cancelled turn is not a failure: whatever arrived first is the reply.
- `ClaudeChat(model=None, *, sp='', messages=None, tools=None, permission_mode='auto', claude_tools=None, claude_disallowed=CLAUDE_DISALLOWED, claude_server_tools=(), workspace=None, effort=None, bare=True, stateful=True, transcript=True, api_key=False, max_buffer=MAX_BUFFER, bin='claude', timeout=600, settings=None, **kw)`, plus the usual `Chat` arguments. Model ids are `opus5`, `opus48`, `sonnet5`, `sonnet46`, `haiku45`, `fable5`, and `CLAUDE_MODELS` holds them all.
- Prefix only. `Chat('claude/claude-sonnet-5')` or `ClaudeChat(...)`, because a bare `claude-...` id still means the hosted API through `remote`.
- `bare=True` answers as a model rather than as your IDE agent: no `CLAUDE.md`, skills, plugins or hooks. Tool calls depend on the model emitting the tags correctly, so use a Sonnet-tier or stronger model for tool-using turns.

## GitHub Copilot (rishi.copilot)

`rishi[copilot]`, plus a GitHub account with a Copilot subscription. Copilot answers OpenAI chat completions, but fastllm has no vendor entry for it and cannot have one. The endpoint takes a token that lasts about half an hour, and rejects any request that does not carry an editor's headers. `rishi.copilot` does that handshake and then reuses `RemoteChat` for the turn itself.

```python
from rishi import Chat
from rishi.copilot import copilot_models, copilot_login, CopilotAuth

print(copilot_models()[:5])            # what this account can actually reach
chat = Chat('copilot/gpt-4.1', sp='You are concise.')
```

- `CopilotChat(model=None, *, oauth_token=None, api_key=None, base_url=None, auth=None, integration_id='vscode-chat', hdrs=None, **kw)`, plus every `RemoteChat` argument. `copilot_default` is `'gpt-4.1'`.
- Prefix only. `Chat('copilot/claude-sonnet-4.5')` or `CopilotChat(...)`, because a bare `gpt-...` or `claude-...` id still means the hosted API through `remote`.
- Credentials. `copilot_oauth()` reads `GITHUB_COPILOT_OAUTH_TOKEN` or `GH_COPILOT_TOKEN`, then the files an editor sign-in leaves behind (`~/.config/rishi/copilot.json`, `~/.config/github-copilot/apps.json` or `hosts.json`, `%LOCALAPPDATA%`, `~/.copilot/config.json`), then `GH_TOKEN` or `GITHUB_TOKEN` last: those two are general-purpose GitHub variables, and a personal access token in one of them would otherwise hide a sign-in that works. `copilot_login()` runs GitHub's device flow and saves one. A personal access token will not work, because GitHub only mints Copilot tokens for apps it knows: the exchange answers it with a 404, which `copilot_exchange` raises as `PermissionError` alongside 401 and 403.
- Tokens. `copilot_exchange()` trades the OAuth token for a `CopilotToken` (bearer, endpoint, expiry). `CopilotAuth` holds one and re-mints it five minutes before expiry, so a long session does not stop mid-turn on a 401. Share one `CopilotAuth` across chats to share the exchange. `api_key=` uses a Copilot token you got some other way, and rishi cannot renew that one.
- Catalogue. `copilot_models()` lists the chat ids this plan can reach; `kind=None` adds the completion and embedding ones. `copilot_catalog()` returns the whole `{id: entry}` payload, and `copilot_ctx(entry)` reads the prompt window Copilot reports for one, which beats guessing from a vendor table.
- Endpoint. The exchange names one per plan, such as `https://api.individual.githubcopilot.com`, and `COPILOT_API` is the fallback.
- Headers. `copilot_hdrs()` sets `copilot-integration-id`, the editor version strings, `openai-intent` and `x-github-api-version`. Per turn, `x-initiator` is `user` or `agent` depending on whether the model is round-tripping its own tool calls, and `copilot-vision-request` goes on when the history carries an image. `Authorization` is left to fastllm, and there is deliberately no `x-request-id`, because fastllm caches its HTTP client on the arguments it was built from.
- Everything else is `RemoteChat`: the same tool loop, approval gate, budget, streaming, `structured` and `classify`.
- Reverse-engineered, and GitHub supports none of it. Your Copilot subscription terms apply.

## Working on rishi itself

It's an nbdev project. Edit the notebooks in `nbs/`, from `00_core.ipynb` through `08_ollama.ipynb`, not the generated files in `rishi/`. Tests are non-exported `#| hide` cells, and model-dependent cells are `#| eval: false` to keep the test run offline. `nbs/03_mlx.ipynb` is also marked `skip_exec: true` in its frontmatter, because CI runs on linux where MLX does not exist. Run it on a Mac. Run `nbdev-prepare`, with a hyphen, after changes.

The tool loop itself lives once, in `rishi.core.ToolLoopMixin`. A backend that receives tool calls as data, such as llama or mlx, supplies `_model_step` and `_stream_step` plus an `ns` tool namespace. The mixin owns approval, history, the budget, parallel dispatch and context recovery. litert runs its loop inside the engine and bridges back through `ChatToolHandler` instead. `rishi.remote`'s tests patch `acomplete` with a fake that streams the typed `aidialog` parts fastllm sends, so the conversions, tool loop and streaming are covered in CI without a key. `rishi.copilot`'s tests assert the request rather than sending one, so they need no subscription. `rishi.ollama`'s run the whole backend against an `httpx.MockTransport` daemon, so they need no Ollama.

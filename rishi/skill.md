---
name: rishi
description: Run models through rishi's one Chat API. Local engines are Gemma .litertlm over litert_lm (rishi.litert), any GGUF over llama-cpp-python (rishi.llama), quantized models on Apple silicon over MLX (rishi.mlx) and anything an Ollama daemon serves (rishi.ollama). Hosted ones are vendor APIs over fastllm (rishi.remote), Claude Code (rishi.claude) and GitHub Copilot (rishi.copilot). All of them share tool calling with human approval, a tool-call budget, streaming, thinking, a python sandbox, structured output, classification and graded answers. Use when writing or debugging offline LLM chat, local tool-use agents, or anything mentioning rishi, litert_lm, gemma .litertlm models, local GGUF/llama.cpp chat, mlx-lm/mlx-vlm, ollama, Claude Code or GitHub Copilot.
---

# rishi

rishi wraps seven backends in one callable `Chat`. A backend is a `Chat` subclass that connects rishi to a model engine or service. Four backends run on your device. They need no API key and no network after the model weights are cached. Urai defines the backend-independent API. Import its shared names from `rishi` or `urai`. `rishi.core` registers the backends and does not define `Chat`. The local backends are `rishi.litert` (Gemma `.litertlm` over litert_lm), `rishi.llama` (any GGUF over llama-cpp-python), `rishi.mlx` (Apple silicon over mlx-lm and mlx-vlm) and `rishi.ollama` (any model that a local Ollama daemon serves). The hosted backends are `rishi.remote` for vendor APIs over fastllm, `rishi.claude` and `rishi.copilot`. `Chat(model)` selects a backend from the model name.

The base `rishi` install includes `rishi.litert`, `rishi.remote`, `rishi.claude` and `rishi.copilot`. The other local backends need extras: `rishi[llama]`, `rishi[mlx]`, `rishi[mlx-vlm]` and `rishi[ollama]`. `rishi[all]` installs all four. rishi loads a backend module when a chat first needs it. If you ask for a local backend without its extra, rishi raises an `ImportError` that names the extra.

## The one thing to remember

`chat(msg)` returns the backend response wrapped in `Resp`. It does not return a string. Get the text with `resp_text(r)`. In a notebook, `r` renders itself as markdown with the thinking, text and tool calls. When you stream, you iterate over markdown chunks instead.

```python
from rishi import Chat, resp_text
chat = Chat()                       # downloads gemma-4-E2B once, then loads from cache
r = chat("Say hello.")
print(resp_text(r))
```

`Chat()` builds an engine and a conversation. Each call runs one turn, appends to `chat.hist` and updates `chat.use`. The next call continues the same conversation. LiteRT-LM stores the keys and values computed for earlier tokens in a key-value cache, called the KV cache.

## API surface

- `Chat(model=None, *, runtime=None, model_path=None, opts=None, engine=None, backend=None, multimodal=True, cache_dir=None, enable_speculative_decoding=None, eng_kw=None, filter_think=True, sampler_config=None, constrain=None, conv_kw=None, **kw)`. `**kw` takes every `urai.ChatOpts` setting, such as `sp`, `tools`, `approve`, `ctx`, `think` (default `None`), `temp`, `cbs` and `default_cbs`. `model` comes first, as a repo id or a local path. `backend=None` tries the GPU first and falls back to the CPU with a warning. `backend=Backend.CPU()` or `backend=Backend.GPU()` skips that fallback. `RISHI_LITERT_GPU=0` stops the GPU attempt. `Chat` selects a backend from `runtime` and the model name, and returns a `LitertChat`, `LlamaChat`, `MlxChat`, `OllamaChat`, `RemoteChat`, `ClaudeChat` or `CopilotChat`. The signature above shows the litert arguments. llama adds `quant`, `n_ctx`, `n_gpu_layers`, `mmproj` and `comp_kw`. mlx and the hosted backends have their own arguments, in their sections.
- `chat(msg=None, stream=False, cbs=None, **kw)` runs a turn. `stream=True` returns a generator of markdown chunks. `cbs=` registers callbacks for that turn only. `**kw` takes the per-turn generation settings listed under "Options", such as `max_output_tokens`.
- State: `chat.hist` (the history as Python objects; print it with `chat.print_hist()`), `chat.use` (a `UsageStats`: `prompt_tokens`, `completion_tokens`, `total_tokens`, `n`), `chat.token_count` (live context size), `chat.pct_full` (that over `ctx_limit`).
- Chat methods: `run_py(code)`, `classify(text, labels)`, `structured(prompt, schema)`, `check(question, expected, ...)`, `grades(question, expected, actual)`, `count_tokens(text)`, `render(msg)`, `cancel()`, `add_cb`/`add_cbs`/`remove_cb`/`remove_cbs`, `close()`.
- `create_engine(...)` is a classmethod on each backend class (`LitertChat.create_engine`, `LlamaChat.create_engine`, `MlxChat.create_engine`) that builds the engine. It resolves the model, makes `cache_dir` and wires the multimodal backends. The `Chat` selector has no `create_engine`. To override it, patch the backend's `create_engine` or pass `engine=`. The hosted backends have no engine to build.
- Module helpers: `resp_text`, `thought`, `display_stream`, `hitl_policy`, `output_matches`, `task_complete`. `bench` and the model ids `gemma4_e2b`, `gemma4_e4b` and `gemma4_12b` come from `rishi.litert`. `from rishi import *` exports urai's generic message builders `mk_msg`, `mk_content` and `mk_msgs`. A backend can also define its own builders and model resolver. Call `chat.mk_msg(...)` or `LitertChat.mk_msg` to get the version of that backend.
- Callbacks: import `ChatCallback` (base), `PyFenceCallback`, `TruncationCallback`, `UsageCallback` and `ToolReminderCallback` from `rishi` or `urai`. The Python-driven backends (llama, mlx, Ollama, hosted, Claude Code) enable `UsageCallback`, `ToolReminderCallback` and `SlidingWindowCallback` by default through `RishiToolLoop`. The history and usage callbacks of litert are internal. All default callbacks are on unless you pass `default_cbs=False`.
- Tool-call budget: `max_steps` (default 10) caps tool *calls* per turn on every backend. Past the cap, rishi denies calls with `budget_msg_` and sends `final_prompt`, which asks the model to answer with what it has. A runaway loop then ends in prose. `max_steps=None` removes the cap.
- `parallel_tools=True` runs independent calls from one turn concurrently, on llama and mlx. litert raises `NotImplementedError`. Approval stays sequential. The HITL order, the budget accounting and the history are the same either way.
- Context recovery: if the window fills during a turn, rishi truncates the oldest tool results, rebuilds the backend state and asks for a summary. rishi raises `ContextWindowExceededError` only if that retry also fails.
- `SlidingWindowCallback(threshold=0.9, keep_first=2, keep_last=8, summarize=False, mx=4000)` is the *proactive* version and works on every backend. Before each turn it checks `pct_full`, and if the context is nearly full it drops whole message groups from the **middle** of `hist`, keeping the earliest turns and the live thread, then calls `chat._recreate_conv()` so the backend rebuilds from the shortened history. It needs `ctx_limit` set, and no-ops without one. `evict_middle` and `msg_groups` are exported if you want the policy without the callback. A tool call and its results are one group and are never split. The callback is on by default. To customize it, remove the default with `chat.remove_cb(SlidingWindowCallback)`, then add your own with `chat.add_cb(SlidingWindowCallback(threshold=0.8))`. `summarize=True` spends one model call to replace the dropped middle with a summary. `mx` is the number of characters of dropped conversation that the summarizer reads.
- This matters most on **litert**, whose KV cache has no automatic recycling upstream ([gallery#856](https://github.com/google-ai-edge/gallery/issues/856)): a full cache OOMs on GPU/NPU and makes the CPU path repeat itself forever, rather than raising cleanly. litert now also evicts and retries once reactively, and its system prompt lives outside `hist` so a rebuild always re-applies it.
- `chat.use` is a `UsageStats` with `prompt_tokens`, `completion_tokens`, `total_tokens`, `n`, `cached_tokens` (prompt tokens served from the backend's KV/prefix cache), `reasoning_tokens`, `cache_creation_tokens`, plus `cost`/`model` for merging with hosted-API usage.
- Streaming has two modes: `chat(msg, stream=True)` yields **markdown strings** (print them, or hand to `display_stream`); `chat(msg, stream='raw')` yields the underlying **chunk dicts** (`{'content': [{'type': 'text', ...}]}`, `{'channels': {'thought': ...}}`, `{'content': [{'type': 'tool_call', ...}]}`) for programmatic consumers that want structure rather than rendered text. Both run the same tool loop.
- `ToolCall(name, arguments, id=None, server=False)` builds a canonical tool call. It is a `dict` subclass, so indexing still works, with `.name`, `.arguments` and `.server` accessors. A call with `server=True` is one the *provider* runs, and the tool loop records it and never executes it locally. `mk_tool_res_msg(tc, result)` and `mk_tool_res_msgs(tcs, results)` build the `role='tool'` reply messages, if you're driving a loop by hand.

## Options: one name per setting

[urai](https://github.com/vedicreader/urai) holds everything backend-agnostic. rishi depends on urai and re-exports it. A setting has the same name on every backend:

```python
Chat('qwen3-4b.gguf', ctx=32_000, temp=0.2, max_output_tokens=512)   # llama.cpp
Chat('gpt-5.1',       ctx=32_000, temp=0.2, effort='high')           # a hosted API
```

`ctx` is the context window on every backend. Each backend renames it to the name its engine uses: `n_ctx` on llama, `num_ctx` on Ollama, `eng_kw['max_num_tokens']` on litert, and `ctx_limit` on mlx and remote. `urai.ChatOpts` holds the full portable set: `sp`, `tools`, `messages`, `approve`, `max_steps`, `tool_max_len`, `parallel_tools`, `max_parallel_tools`, `final_prompt`, `cbs`, `default_cbs`, `ctx`, `max_output_tokens`, `temp`, `top_k`, `top_p`, `seed`, `think`, `effort`, `tool_mode`, `api_key`, `api_key_env` and `base_url`. A setting that belongs to one backend keeps its own name on that backend's constructor, for example `quant`, `mmproj`, `keep_alive`, `conv_kw` and `comp_kw`. Any other keyword goes into `ChatOpts.extra`. A per-turn call forwards those keywords to the request on llama, mlx, Ollama, remote and copilot.

Generation settings also apply to a single turn. You do not have to change the chat to make one turn think harder. The per-turn settings are `max_output_tokens`, `temp`, `top_k`, `top_p`, `seed`, `think`, `effort` and `tool_mode`:

```python
chat('a hard question', effort='high', temp=0.9, max_output_tokens=2048)
```

A backend drops an option it cannot use, and it gives no warning. The table lists what each backend drops.

| Backend | Options it drops |
|---|---|
| litert, llama, mlx, Ollama | `effort`, `tool_mode`, `api_key`, `base_url` |
| remote, copilot | `top_k`, `top_p`, `seed`, `think` |
| claude | `temp`, `top_k`, `top_p`, `seed`, `max_output_tokens`, `think`, `api_key`, `base_url` |

llama and mlx also ignore `ctx` and `think` on a single turn, and mlx ignores `seed` on a single turn. The window and the thinking switch are fixed when the chat is built.

The older spellings work on every backend. `reasoning_effort`, `temperature`, `max_tokens`, `ctx_limit`, `n_ctx` and `system` are aliases of `effort`, `temp`, `max_output_tokens`, `ctx`, `ctx` and `sp`.

`resolve(name)` returns a `ModelSpec` without loading the model. A `ModelSpec` holds `name`, `runtime`, `model_id`, `ctx`, `note` and `opts`. `mk_chat(spec, **kw)` builds a `Chat` from one.

The table lists the numeric defaults. A dash means the backend sends no value.

| Setting | Backend | Default |
|---|---|---|
| `max_steps` | every backend | 10 |
| `max_output_tokens` | mlx | 1024 |
| `max_output_tokens` | remote, copilot | the model maximum that fastllm reports, else 16000 |
| `max_output_tokens` | litert, llama, Ollama | - |
| `ctx` | llama | 8192 |
| `ctx` | mlx | `max_position_embeddings` of the model config, else 8192 |
| `ctx` | Ollama | `$OLLAMA_CONTEXT_LENGTH`, else 4096 |
| `ctx` | litert, remote, copilot, claude | - |
| `retries` | remote, copilot | 2 |
| `timeout` | claude | 240 seconds |
| `skew` of `CopilotAuth` | copilot | 300 seconds |

## Streaming and thinking

```python
for chunk in chat("Count to five.", stream=True): print(chunk, end='', flush=True)
display_stream(chat("Count to five.", stream=True))   # renders live in a notebook
```

`Chat(think=True)` turns on the thinking channel. `resp_text(r)` is the answer, `thought(r)` is the reasoning, and `r` renders the thinking as a quoted block in a notebook. `filter_think=True` (the default) keeps thinking out of the KV cache.

## Tools and approval

Pass plain functions as `tools`. The schema comes from each function's signature and docstring. The backend calls the function during the turn.

```python
def add(a: int, b: int) -> int:
    "Add two integers."
    return a + b
chat = Chat(tools=[add])
```

Pass `approve` to gate execution. `approve(tool_call) -> bool` runs before every call. With `approve=None`, every call runs. `hitl_policy` builds an `approve` function from a per-tool rule:

```python
from rishi import hitl_policy
def danger(path: str) -> str:
    "Delete a file."
    return f'deleted {path}'
chat = Chat(tools=[add, danger], approve=hitl_policy({'add': 'approved', 'danger': 'dont_run'}))
```

Modes are `approved` (run), `dont_run` (block) and `check` (ask). A tool that `modes` does not list uses `check`. `check` asks on the console unless you pass `ask=` or `http`. In a Leela web IDE kernel, `hitl_policy(modes, http=True)` sends checked calls to Leela's browser approval card and does not call `input()`. `http='http://host:port'` sets the Leela address. Without it, the address comes from `URAI_APPROVAL_URL`, and `http://127.0.0.1:5001` is the fallback. `browser_approval(url=None, timeout=300)` is also available as a standalone callback. It is an alias of urai's `http_approval`. `approve` blocks a call by returning a false value. rishi records a blocked call as "Denied by human operator" and reports it to the model. An approver that returns a false object with a `reply()` method supplies its own text instead. For custom logic, pass your own function. On litert, `ChatToolHandler` routes calls through `approve` and writes calls and results into `hist`.

## Running python from replies

`PyFenceCallback` makes the chat a code interpreter: it runs the last ```python fence through a sandbox (`safepyrun`, so `socket`/`importlib` are blocked), feeds the output back as a ```result block, and loops until the model answers in prose or `done(chat)` is true, capped by `max_rounds`.

```python
from rishi import PyFenceCallback, output_matches
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
from rishi.litert import gemma4_12b
judge = Chat(gemma4_12b, multimodal=False, cache_dir='.cache/litertlm')
chat.check("Name a primary colour.", "red, blue, or yellow", judge=judge).ok  # graded by a bigger model
```

`check` extracts the answer from a ```answer fence and grades it. Default grade is `grade_fn(answer, expected)` (`matches_`, a contains check). Pass `llm_judge=True` or a `judge=` chat to grade with a model, or your own `grade_fn`. It returns `AttrDict(question, expected, answer, ok)`.

## Callbacks

Subclass `ChatCallback` and define any of `before_send`, `after_response`, `before_tool_calls` and `after_tool_calls`. A callback reads turn state from the chat. `self.turn_res` is `chat.turn_res`. Callbacks run in ascending `order`, and `ChatCallback` sets `order` to 0. Register a callback with `chat.add_cb(MyCb)` or `Chat(cbs=[...])`. Run one for a single turn with `chat(msg, cbs=[...])`. Remove one with `chat.remove_cb(MyCb)`, by instance or by class. Every default callback is on unless you pass `default_cbs=False`. The table lists the callbacks that ship with rishi.

| Callback | `order` | On by default |
|---|---|---|
| `_HistoryCallback` (litert, internal) | 0 | litert |
| `SlidingWindowCallback` | 5 | every backend |
| `UsageCallback` | 10 | llama, mlx, Ollama, remote, copilot, claude |
| `_UsageCallback` (litert, internal) | 10 | litert |
| `TruncationCallback` | 20 | no |
| `ToolReminderCallback` | 30 | llama, mlx, Ollama, remote, copilot, claude |
| `_ToolReminderCallback` (litert, internal) | 30 | litert |
| `PyFenceCallback` | 50 | no |

## Sharing a model

Loading costs seconds and gigabytes. Build one engine and reuse it:

```python
from rishi.litert import LitertChat
eng = LitertChat.create_engine(cache_dir='.cache/litertlm')      # `create_engine` is per backend
a, b = Chat(engine=eng), Chat(engine=eng)
```

A Chat that built its own engine frees it on `close()`. A Chat handed an engine leaves it alone, so siblings keep working.

## Gotchas

- A repo can ship a native `.litertlm` file and a `-web` build. The web build has no CPU or GPU decode graph and fails with `TF_LITE_PREFILL_DECODE not found`. rishi's model resolver skips any `.litertlm` path that contains `web`.
- GPU needs a writable `cache_dir`. Without it you get `Could not open ... mldrift_weight_cache.bin: No such file or directory`. `create_engine` creates the directory when you pass `cache_dir`.
- The log line `WebGPU sampler not available, falling back to statically linked C API` is harmless. Quiet the noise with `set_min_log_severity(3)`.
- Tool and structured-output arguments arrive as floats (`21.0`) from the model's JSON. Cast inside the tool if you need strict ints.
- `run_text_scoring` is not available on this runtime. `classify` and `check` grade by generation and do not use log-likelihood scoring.
- A re-signing corporate proxy breaks TLS. `certifi` does not know the proxy's root certificate. Every hosted backend then fails with `CERTIFICATE_VERIFY_FAILED`. Importing rishi calls `use_system_certs()`, which verifies against the OS trust store through `truststore`. `URAI_SYSTEM_CERTS=0` turns it off. `RISHI_SYSTEM_CERTS=0` also turns it off when `URAI_SYSTEM_CERTS` is unset. The fix covers the connections that Python opens: `remote` and `copilot`. It does not cover separate binaries. Claude Code and the Ollama daemon carry trust stores of their own.

## One interface for every backend

`Chat` selects the backend from the model name, as fastllm does, and returns the `Chat` subclass of that backend: `LitertChat`, `LlamaChat`, `MlxChat`, `OllamaChat`, `RemoteChat`, `ClaudeChat` or `CopilotChat`. The result is a real subclass and not a wrapper. `isinstance(chat, Chat)` is true, and `chat.runtime` names the backend. Callbacks, tools, `hist`, `use` and streaming work as documented for each backend. `**kw` passes straight through to the backend. Backend-specific arguments such as `backend=Backend.GPU()`, `mmproj=`, `n_gpu_layers=` and `kv_bits=` work.

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

Resolution order: first an explicit `runtime=`. Then a `runtime/` prefix, if it names a known runtime. A name such as `litert-community/...` is not a prefix. Then the patterns of the id or path. Last, the default `litert`. Urai checks the model-name patterns in the registration order of `rishi.core.BACKENDS`, and local runtimes come before `remote`. The table lists the patterns.

| runtime | patterns |
|---|---|
| `litert` | `.litertlm`, `litertlm`, `litert-community`, `litert-lm` |
| `ollama` | `hf.co/`, `huggingface.co/` |
| `llama` | `.gguf`, `gguf` |
| `mlx` | `mlx-community`, `mlx_lm`, `-mlx`, `mlx-` |
| `remote` | `claude-`, `gpt-`, `gemini-`, `kimi-`, `deepseek-`, `grok-`, `sonnet`, `opus`, `haiku`, `fable` |

The `hf.co/...` pattern means ollama. The registration order checks it before `.gguf`. rishi never infers three things. They need a prefix. `claude` and `copilot` serve models under names that the hosted vendors also use. A bare Ollama id such as `qwen3:4b` has a `name:tag` form, which is also how Windows writes a path. A bare name that rishi cannot place raises an error with instructions. There is no alias table, so pass a full hub repo id or path. `resolve_runtime`, `split_runtime`, `infer_runtime` and `get_runtime` are exported if you want the decision without building anything.

The selector argument is `runtime=`. `backend=` is the hardware backend of litert, such as `Backend.GPU()`, and passes straight through.

## llama.cpp backend (rishi.llama)

`pip install 'rishi[llama]'` installs llama-cpp-python. `LlamaChat` runs any GGUF repo from the HuggingFace Hub through the same `Chat` API. `AsyncChat` comes from `rishi`, and the model ids come from `rishi.llama`.

```python
from rishi import Chat, AsyncChat, resp_text
from rishi.llama import qwen3_4b

chat = Chat(qwen3_4b, think=False)               # or model_path='path/to/model.gguf'
r = chat("Say hello.")
print(resp_text(r))

achat = AsyncChat(chat)                          # or AsyncChat(model) to build its own
r = await achat("Again?")
async for c in await achat("Stream it.", stream=True): print(c, end='')
```

The list below gives the differences from the litert backend.

- `LlamaChat(model=None, *, runtime=None, model_path=None, opts=None, engine=None, quant='Q4_K_M', n_gpu_layers=0, mmproj=None, eng_kw=None, preserve_cache=False, comp_kw=None, **kw)`. `**kw` takes every `urai.ChatOpts` setting, such as `ctx`, `think`, `temp` and `max_steps`. `model` is positional, as a repo id or a local path. `model_id=` does not exist.
- The model ids are `qwen3_06b`, `qwen3_17b`, `qwen3_4b`, `gemma3_1b` and `gemma3_4b`. `quant` selects the `.gguf` file in the repo. `n_gpu_layers=-1` offloads every layer to the GPU.
- A multimodal GGUF needs an `mmproj` projector next to the model. `Chat(gemma3_4b, mmproj=True)` finds the projector in the same repo and checks the cache first, as the model lookup does. `get_mmproj` does the same on its own. You can also pass an explicit path. The projector builds llama.cpp's `MTMDChatHandler`.
- Pass images and audio as `bytes` or a `Path` in the message list: `chat(['Describe this.', Path('cat.jpg')])` or `chat(['Transcribe this.', Path('clip.wav')])`. One turn can carry both. Each item becomes a media marker in document order.
- Upstream `MTMDChatHandler` handles images only. rishi patches it for audio. `get_image_urls` also collects `input_audio` parts. `_get_template_messages` maps them to the media marker. `_create_bitmap_from_bytes` sends audio to `mtmd_bitmap_init_from_audio`. `_init_mtmd_context` accepts audio-only projectors. Images keep the upstream code path.
- The patch makes `MTMDChatHandler.get_image_urls` an instance method. Upstream defines it as a `staticmethod`. Every call site inside llama-cpp-python uses `self.`. Do not call `get_image_urls` on the class.
- `read_audio(o, sr=16000)` decodes audio to mono float32 at `sr` with soundfile and libsndfile. It reads WAV, FLAC and OGG, and reads MP3 with libsndfile 1.1 or later. Any other format raises `ValueError` with the MIME type.
- The tool loop runs in Python. litert runs it inside the engine. rishi parses structured `tool_calls` and Hermes or Qwen `<tool_call>` text tags. Each call goes through `approve`, and `hitl_policy` works unchanged. Results return as `role='tool'` messages, up to `max_steps` rounds per turn. A tool is a Python callable (the schema comes from `fastcore.funccall`) or an OpenAI tool-spec dict.
- llama.cpp keeps no state between calls. `chat.hist` is the conversation state, and there is no `HistoryCallback`. Messages are OpenAI-style dicts. rishi splits thinking from `<think>` tags into `channels.thought` and never sends it back.
- `think=True` appends `/think` to the system prompt, and `think=False` appends `/no_think`. This is the Qwen soft switch. `think=None` keeps the model default.
- `structured` forces the tool call with a JSON-schema grammar, so the arguments always parse.
- llama has no `render()`, `cancel()` or `bench()`.
- `AsyncChat` wraps a `Chat`. It takes a `Chat` or the arguments to build one. Calls run in a worker thread. Use `await achat(msg)` or `async for c in await achat(msg, stream=True)`.

llama.cpp reuses the KV cache itself. `Llama.generate` trims the cache to the longest common prefix with the new prompt and evaluates only the tail. An appended turn re-prefills nothing. rishi reports the reuse as `use.cached_tokens`. Three events break the prefix:

- A one-shot call on the same engine: `classify`, `structured`, `check`, `grades`, a shared `engine=`, or a `judge=` on the same engine. A `Llama` has one context, and any completion overwrites the conversation.
- A rewritten history, from eviction or context recovery.
- Media. The live turn carries the real image and later turns carry an `[image]` placeholder. The turn after a media turn re-prefills.

`preserve_cache=True` saves the llama state before a one-shot call and restores it after. That is a full KV copy and pays off only on large contexts. `save_cache(path)` and `load_cache(path)` write the context to disk and read it back. `rishi.mlx` has the same two methods.

## MLX backend (rishi.mlx)

`pip install 'rishi[mlx]'` works on Apple silicon only. `pip install 'rishi[mlx-vlm]'` adds vision and audio. `MlxChat` runs any [mlx-community](https://huggingface.co/mlx-community) repo through the same `Chat` API.

```python
from rishi import resp_text
from rishi.mlx import MlxChat, qwen3_4b

chat = MlxChat(qwen3_4b, sp='You are concise.', think=False)
print(resp_text(chat("Say hello.")))
print(chat.use)          # cached_tokens is above 0 from the second turn on
```

- `MlxChat(model=None, *, runtime=None, model_path=None, opts=None, vlm=None, engine=None, adapter_path=None, draft_model=None, eng_kw=None, min_p=None, prompt_cache=True, max_kv_size=None, kv_bits=None, kv_group_size=64, quantized_kv_start=0, tmpl_kw=None, gen_kw=None, **kw)`. `**kw` takes every `urai.ChatOpts` setting. `model` is positional. `model_id=` does not exist.
- The model ids are `qwen3_06b`, `qwen3_17b`, `qwen3_4b`, `qwen3_8b`, `qwen3_30b`, `gemma3_4b`, `llama32_3b`, `qwen3vl_4b`, `gemma4_e4b` and `qwen3omni_30b`. `qwen3vl_4b` takes images. The table lists the two models that take audio.

| Model id | Input | Download size |
|---|---|---|
| `gemma4_e4b` | image and audio | about 5 GB |
| `qwen3omni_30b` | audio | about 22 GB |

- Each turn, rishi renders the conversation to token ids and compares them with the tokens in the prompt cache (`common_prefix_len`). rishi trims the diverged tail from the cache and prefills only the new tokens. It reports the reuse as `use.cached_tokens`. `prompt_cache=False` turns the reuse off.
- The token comparison makes an edited history safe. A chat template can render an assistant turn as different tokens from the ones the model generated, and context recovery rewrites history. A mismatch costs one re-prefill.
- LiteRT keeps state in its `Conversation`. llama.cpp re-renders the history and reuses its longest matching KV prefix. MLX owns its prompt cache and trims it explicitly.
- `save_cache(path)` and `load_cache(path)` write a warmed cache to disk and read it back. A long system prompt is prefilled once and reused in later sessions.
- `kv_bits=4` quantizes the KV cache for long contexts. `kv_group_size` and `quantized_kv_start` tune it. `draft_model=qwen3_06b` turns on speculative decoding. `adapter_path='./adapters'` applies a LoRA adapter when the model loads.
- mlx-lm has no built-in tool-call parser. Tool calls come back as `<tool_call>{json}</tool_call>` text. rishi parses them with the same `StreamSplit` as llama. Thinking arrives in `<think>` tags. `think=True` or `think=False` goes to the chat template as `enable_thinking`, which Qwen3-style templates read.
- `structured` has no grammar constraint on this backend. It asks for JSON and parses the reply: a fenced `json` block first, then the outermost braces. If neither parses, it raises `ValueError`. `classify`, `check` and `grades` work as on the other backends.
- `Chat` reads the repo's `config.json`. A model with a vision or audio tower gets `MlxVlmChat` (mlx-vlm). `vlm=True` or `vlm=False` overrides that choice. Pass media as `bytes` or a `Path` in the message list, as on llama.
- mlx-vlm has no per-model tool-call parser. Tool use there needs the model to emit `<tool_call>` tags. mlx-vlm manages its own vision-feature cache, so cross-turn token prefix reuse is off on that path.
- A text-only MLX model given an image raises `TypeError` that points at `rishi[mlx-vlm]`. rishi does not drop the image silently.
- Audio in: `chat([Path('speech.wav'), 'Transcribe this audio.'])` works on `gemma4_e4b` and `qwen3omni_30b`. mlx-vlm decodes the file and resamples it to the sampling rate of the model's feature extractor. Do not pass `sampling_rate`.
- rishi passes its own `think` value to the mlx-vlm chat template. mlx-vlm alone defaults to `enable_thinking=False`, which prefills an empty `<think></think>` block. A model given a finished thought can end the turn at once. Qwen3-Omni then transcribes nothing.

## Ollama backend (rishi.ollama)

`pip install 'rishi[ollama]'`. Ollama is a server, and this backend drives the daemon as well as the conversation. On a machine without Ollama, `Chat('ollama/qwen3:4b')` installs Ollama under `~/.cache/rishi/ollama`, starts `ollama serve`, pulls the model and answers. rishi stops the daemon at interpreter exit. A daemon that is already listening is left running. rishi never starts a daemon on a host that is not on this machine. A chat aimed at such a host with nothing listening raises `OllamaError`.

```python
from rishi import Chat
from rishi.ollama import ensure_ollama, OllamaServer, install_ollama, stop_ollama, qwen3_4b

chat = Chat(f'ollama/{qwen3_4b}', think='low', ctx=8192, sp='You are concise.')
cl = ensure_ollama()                       # the daemon itself
print(cl.version(), cl.models(), cl.ps())
cl.pull('gemma3:4b', on_progress=print)    # streamed progress records
```

- `OllamaChat(model=None, *, runtime=None, model_path=None, opts=None, host=None, client=None, quant='Q4_K_M', pull=True, install=True, serve=True, srv_kw=None, on_progress=None, n_gpu_layers=None, keep_alive=None, options=None, comp_kw=None, **kw)`. `**kw` takes every `urai.ChatOpts` setting. The model ids are `qwen3_06b`, `qwen3_17b`, `qwen3_4b`, `gemma3_1b`, `gemma3_4b` and `llama32_3b`. Any id from Ollama's library also works.
- `ollama_model` maps a hub GGUF repo to `hf.co/<repo>:<quant>`. `Chat('Qwen/Qwen3-4B-GGUF', runtime='ollama')` and the llama backend take the same id. A local `.gguf` path raises an error that names `runtime='llama'`. Ollama serves only what its own store holds.
- Thinking is a request field and not a system-prompt switch. `think` takes `True`, `False`, `'low'`, `'medium'`, `'high'` or `'max'`. A model without thinking refuses the field. rishi then drops the field, retries once and stops sending it for that chat.
- `ctx` goes out as `num_ctx` and `n_gpu_layers` goes out as `num_gpu`. `temp`, `top_k`, `top_p`, `seed` and `max_output_tokens` map onto the other `options`. Pass any further option in `options=`. `keep_alive=` sets how long the model stays loaded after a turn. `chat.unload()` unloads it at once.
- `structured` uses Ollama's own `format` field with the JSON schema, so the arguments parse. `classify`, `check` and `grades` work as on the other backends.
- `OllamaServer(host=None, bin=None, dir=OLLAMA_DIR, models=None, n_ctx=None, keep_alive=None, flash_attn=None, kv_cache_type=None, num_parallel=None, max_loaded=None, log=None)` wraps `ollama serve` and its environment variables. `install_ollama()` unpacks the release archive for the current user and needs no root. `ensure_ollama()` returns a client and starts a daemon when none is running. `stop_ollama()` ends the daemon that rishi started. `OllamaClient` covers `/api/chat`, `/api/tags`, `/api/show`, `/api/ps`, `/api/pull` and `/api/delete`.
- `model_caps(model, runtime='ollama')` asks `/api/show`. It reports what the daemon knows and does not guess from file names. The result has `source='runtime'`.
- Audio in is not available, because Ollama takes images only.
- `save_cache` and `load_cache` are not available. `cached_tokens` is not a real count, because the KV cache lives in the daemon and has no handle.
- An exact `count_tokens` before a turn is not available, because the daemon has no tokenizer endpoint. `use` holds the true count after the turn.
- There is no broker, because the daemon is one. Set `OLLAMA_NUM_PARALLEL` and `OLLAMA_MAX_LOADED_MODELS` to size it.

## Hosted models (rishi.remote)

Plain `rishi` includes [fastllm](https://github.com/AnswerDotAI/fastllm). Set the vendor's key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and so on) and the same `Chat` API talks to Anthropic, OpenAI, Gemini, DeepSeek, Moonshot, OpenRouter and the other vendors that fastllm supports.

```python
from rishi import Chat, resp_text
chat = Chat('claude-sonnet-4-5', sp='You are concise.')
print(resp_text(chat("Say hello.")))
```

- `RemoteChat(model=None, *, runtime=None, model_path=None, opts=None, vendor_name=None, api_name=None, tool_choice=None, retries=2, comp_kw=None, **kw)`. `**kw` takes every `urai.ChatOpts` setting, including `api_key`, `base_url`, `effort` and `tool_mode`.
- `RemoteChat` uses the same tool loop as llama and mlx. Approval, the budget, `parallel_tools`, callbacks and `PyFenceCallback` behave the same way. The wire call is async (`fastllm.acomplete`). `run_coro` and `sync_iter` bridge it to the sync API.
- `tool_choice` takes `'auto'`, `'required'`, `'none'` or a tool name. rishi passes it through unchanged.
- `effort` takes `'low'`, `'medium'`, `'high'`, `'xhigh'` or `'max'`. `reasoning_effort` is an alias. `EFFORT_MAP` rewrites the value for some providers: `max` becomes `xhigh` on OpenAI and Azure, and `xhigh` and `max` become `high` on Gemini.
- A 400 response that names the effort makes rishi repeat the call without it. `chat.dropped_effort` then holds the reason. rishi sends no effort while `dropped_effort` is set.
- `tool_mode` takes `'native'` (the default) or `'tags'`. You can pass it for one turn, streamed or not.
- A provider-run tool, such as web search, comes back with `server=True` on the `ToolCall`. The tool loop records it and never runs it locally.
- `to_msg` and `to_hist` convert between rishi's canonical dicts and fastllm's `Msg` and `Part`. Text, thinking, tool calls, tool results, images and audio all round-trip. Media travels as a data URL and not as a placeholder, so a hop from a local backend to a hosted one keeps the picture.
- `structured` forces the tool call with `tool_choice` set to the tool name, so the arguments parse. If that fails, it parses a JSON reply.
- A cut-off or malformed tool call, or a reply that is all thinking, goes back to the model once. If the second reply has the same fault, rishi raises `ToolCallError`.
- `chat.use.cached_tokens` comes from the provider's prompt-cache accounting. MLX fills the same field from prefix reuse. A tally that mixes local and hosted usage adds up in one `UsageStats`.
- `close()` does nothing, because the HTTP client belongs to fastllm.

## Claude Code (rishi.claude)

Plain `rishi` includes this backend. It needs Claude Code on `$PATH` and one `claude /login`. Claude Code is an agent with its own harness and not a completion endpoint. One turn is one `query()` on a live session. rishi drives the binary as a subprocess and never reads your credentials. `ClaudeChat.local` is `False`.

```python
from rishi import Chat
from rishi.claude import ClaudeChat, sonnet5, CLAUDE_SERVER_TOOLS

chat = Chat('claude/claude-sonnet-5', sp='You are concise.')   # or ClaudeChat(sonnet5)
```

- `ClaudeChat(model=None, *, runtime=None, model_path=None, opts=None, permission_mode='auto', claude_tools=None, claude_disallowed=CLAUDE_DISALLOWED, claude_server_tools=(), mcp_servers=None, mcp_tools=None, strict_mcp_config=False, workspace=None, fallback=None, cleanup=True, bare=True, stateful=True, transcript=True, api_key=False, max_buffer=MAX_BUFFER, bin='claude', settings=None, timeout=240, on_stall=None, timeout_hint=None, **kw)`. `**kw` takes every `urai.ChatOpts` setting.
- Model ids are `opus5`, `opus48`, `sonnet5`, `sonnet46`, `haiku45` and `fable5`. `CLAUDE_MODELS` holds all of them.
- You must use the prefix: `Chat('claude/claude-sonnet-5')` or `ClaudeChat(...)`. A bare `claude-...` id selects the hosted API through `remote`.
- A model name resolves in one of three ways: a `CLAUDE_MODELS` key (`'opus5'`), a pinned id (`'claude-opus-5'`), or a tier alias from `CLAUDE_ALIASES` (`'opus'`, `'sonnet'`, `'haiku'` or `'fable'`). A tier alias names the latest model of that tier on your plan. `claude_model` does the resolving and passes any other name through unchanged.
- `fallback='sonnet,haiku'` is Claude Code's own `--fallback-model` chain. An overloaded or retired primary model moves down the chain, and the turn continues.
- `chat.set_model('haiku45')` switches the model during a conversation. A live session is told directly and is not torn down. `set_model(None)` returns the choice to Claude Code.
- `bare=True` answers as a model and not as your IDE agent: no `CLAUDE.md`, skills, plugins or hooks. Tool calls depend on the model emitting the tags correctly. Use a Sonnet-tier or stronger model for turns that use tools.

Tools travel to Claude Code in one of two ways. `tool_mode` selects the way, and `chat.tool_channel` reports it.

- `tool_mode='tags'` is the default, and `chat.tool_channel` is `'tags'`. rishi opens no MCP server. The tool schemas go out as `<tool_call>` tags in the system prompt, and `parse_tool_tags_ex` reads the replies. An organisation-managed configuration forbids every dynamic MCP server. With tags the model still has its tools on such a machine.
- `tool_mode='native'` sends the tools over MCP. rishi declares an in-process MCP server named `rishi` with one tool per toolspec. Each tool is allowed as `mcp__rishi__NAME`, and `chat.tool_channel` is `'native'`. Every call passes through rishi's approval gate, the step budget and `tool_max_len`. rishi writes each call to `hist`.
- A managed configuration refuses the `rishi` server. The chat then raises `ClaudeMcpRefused`, a `ClaudeError` that carries Claude Code's message. Catch it and fall back to `tool_mode='tags'`.
- `mcp_servers` declares further MCP servers, and `mcp_tools` selects which of their tools to allow. The default `mcp_servers=None` declares none. `mcp_tools=None` allows every tool of every server that `mcp_servers` names.
- `strict_mcp_config` defaults to `False`. A machine with an enterprise MCP configuration refuses `strict_mcp_config=True` outright.

rishi files the conversation with Claude Code as a session transcript.

- `anth_msgs` turns `hist` into Anthropic messages. `llmsurgery` writes them as records under `CLAUDE_WORK_DIR` (`~/.rishi-claude`). The turn then resumes that session id. The model reads real messages: an `image` block for a picture, a `document` block for a PDF, and a `tool_use` followed by the `tool_result` that carries its id.
- `transcript=False` and a missing `llmsurgery` both fall back to one flattened prompt. A flattened prompt carries no media.
- A chat owns the transcripts it files. `cleanup=True` (the default) removes the transcript that the next one replaces, and removes the rest when the chat closes.
- A session id hashes the messages together with a nonce created when the chat is built. Refiling the same conversation reuses the same id. Two chats with the same history never share a file.
- `prune_sessions(cwd=None, keep=0, age=None, entrypoint='sdk-py')` removes the backlog left by a crash or by `cleanup=False`. `cwd=None` means `CLAUDE_WORK_DIR`. `keep` spares the newest transcripts. `age` spares transcripts younger than that many seconds. It touches only records whose `entrypoint` matches. It returns the deleted paths. Records carry the version of the installed binary, read once from `claude --version`.
- `stateful=True` (the default) keeps one Claude Code session and one subprocess for the whole conversation. A tool result in the middle of a turn goes up as text, because a live session takes user turns. `stateful=False` files every turn as records and starts one subprocess per turn. That is slower and more faithful.
- `workspace=` is the directory Claude Code works in, and rishi files its transcripts there. Unset, it is `CLAUDE_WORK_DIR`, which keeps synthesized records out of a real project's history. `workspace='.'` files them in the current project.

Claude Code's own tools follow the rules below.

- A chat that carries tools of its own sends `tools=[]` to Claude Code. Only rishi's tools exist for that chat.
- `claude_disallowed` is `('Bash', 'Write', 'Edit', 'NotebookEdit')`. Claude Code is refused those four tools in every chat.
- A chat with no tools of its own keeps Claude Code's default tool set minus the four. `Read`, `Grep`, `Glob` and `Task` stay live. `Read` is not confined to `workspace`. This is intended, because the backend runs rishi's tools inside Claude Code.
- `claude_tools=[]` turns Claude Code into a completion endpoint. `claude_tools=['Read']` allows one of its tools back.
- `claude_server_tools=CLAUDE_SERVER_TOOLS` enables `WebSearch` and `WebFetch`. They run on the Claude Code side, need no schema and never reach rishi's tool loop.
- rishi blanks an ambient `ANTHROPIC_API_KEY` for the subprocess. A key left in place would turn a subscription session into a metered API session. `api_key=True` lets the key through.
- `effort` takes `'low'`, `'medium'`, `'high'`, `'xhigh'` or `'max'`. A call whose `effort` differs from the grade the live session opened with reconnects the session, resumed from `hist`. A call with no `effort` runs at the chat's own grade and reconnects the same way.

Usage and failures follow the rules below.

- `chat.use.cost` is the cost Claude Code reported for the turn. It is not read from a price table. `cached_tokens` and `cache_creation_tokens` come from its usage block.
- Claude Code's own system prompt adds 48k to 53k prompt tokens to each turn. Most of that is a cache read.
- A failed turn raises `ClaudeError`, a `RuntimeError` with `.status` (for example 429 or 529) and the raw result in `.raw`. A caller can tell a rate limit from a bad prompt. A cancelled turn is not a failure, and the reply is whatever arrived first.
- A turn that produces no stream event for `timeout` seconds is ended and tried once more. `on_stall` receives a status note, and `warnings.warn` is the default. Text already shown is not sent again, and the retry asks Claude Code to finish it.
- A second silence raises `ClaudeStall`, a `TimeoutError`. Its message names the limit and `timeout_hint`.

| Setting | Default |
|---|---|
| `timeout` | 240 seconds |
| `max_buffer` | 10485760 bytes |
| `permission_mode` | `'auto'` |

## GitHub Copilot (rishi.copilot)

Plain `rishi` includes this backend. It needs a GitHub account with a Copilot subscription. Copilot answers OpenAI chat completions. fastllm has no vendor entry for Copilot. The endpoint takes a token that lasts about half an hour and rejects any request without an editor's headers. `rishi.copilot` does that handshake and then uses `RemoteChat` for the turn.

```python
from rishi import Chat
from rishi.copilot import copilot_models, copilot_login, CopilotAuth

print(copilot_models()[:5])            # what this account can reach
chat = Chat('copilot/gpt-4.1', sp='You are concise.')
```

- `CopilotChat(model=None, *, oauth_token=None, auth=None, integration_id='vscode-chat', hdrs=None, tool_choice=None, retries=2, comp_kw=None, **kw)`. `**kw` takes every `urai.ChatOpts` setting, including `api_key` and `base_url`. `copilot_default` is `'gpt-4.1'`.
- You must use the prefix: `Chat('copilot/claude-sonnet-4.5')` or `CopilotChat(...)`. A bare `gpt-...` or `claude-...` id selects the hosted API through `remote`.
- `copilot_oauth()` reads the OAuth token from these places, in order: `GITHUB_COPILOT_OAUTH_TOKEN` or `GH_COPILOT_TOKEN`; the files that an editor sign-in leaves behind (`~/.config/rishi/copilot.json`, `~/.config/github-copilot/apps.json` or `hosts.json`, `%LOCALAPPDATA%`, `~/.copilot/config.json`); then `GH_TOKEN` or `GITHUB_TOKEN`. The last two are general GitHub variables. They come last because a personal access token in one of them would hide a sign-in that works.
- `copilot_login()` runs GitHub's device flow and saves the token.
- A personal access token does not work. GitHub mints Copilot tokens only for apps it knows. The exchange answers a personal access token with a 404. `copilot_exchange` raises `PermissionError` for that 404, and for 401 and 403.
- `copilot_exchange()` trades the OAuth token for a `CopilotToken` (bearer, endpoint, expiry). `CopilotAuth` holds the token and mints a new one 300 seconds (`skew`) before expiry. A long session does not fail with a 401 in the middle of a turn. Share one `CopilotAuth` between chats to share the exchange.
- `api_key=` takes a Copilot token that you obtained another way. rishi cannot renew that token.
- `copilot_models()` lists the chat ids that this plan can reach. `kind=None` adds the completion and embedding ids. `copilot_catalog()` returns the whole `{id: entry}` payload. `copilot_ctx(entry)` reads the prompt window that Copilot reports for one entry.
- The exchange names one endpoint per plan, for example `https://api.individual.githubcopilot.com`. `COPILOT_API` is the fallback.
- `copilot_hdrs()` sets `copilot-integration-id`, the editor version strings, `openai-intent` and `x-github-api-version`. On each turn, `x-initiator` is `agent` when the model is returning its own tool calls and `user` otherwise. `copilot-vision-request` is set when the history carries an image. fastllm sets `Authorization`. rishi sends no `x-request-id`, because fastllm caches its HTTP client on the arguments that built it.
- Everything else is `RemoteChat`: the tool loop, the approval gate, the budget, streaming, `structured` and `classify`.
- The Copilot protocol is reverse-engineered. GitHub supports none of it. Your Copilot subscription terms apply.

## Working on rishi itself

rishi is an nbdev project. Edit the notebooks in `nbs/`, from `00_core.ipynb` through `08_ollama.ipynb`. Do not edit the generated files in `rishi/`. Run `nbdev-prepare` after a change.

Tests are non-exported `#| hide` cells. Cells that need a model have `#| eval: false`, which keeps the test run offline. `nbs/03_mlx.ipynb` also has `skip_exec: true` in its frontmatter, because CI runs on Linux and MLX needs a Mac. Run that notebook on a Mac.

The tool loop lives in `urai.ToolLoopMixin`, and `rishi.core.RishiToolLoop` extends it. A backend that receives tool calls as data, such as llama or mlx, supplies `_model_step`, `_stream_step` and an `ns` tool namespace. The mixin handles approval, history, the budget, parallel dispatch and context recovery. litert runs its loop inside the engine and bridges back through `ChatToolHandler`.

The backend tests need no key and no installed service.

- `rishi.remote` patches `acomplete` with a fake that streams the typed `aidialog` parts that fastllm sends. The tests cover the conversions, the tool loop and streaming.
- `rishi.copilot` asserts the request and does not send it, so the tests need no subscription.
- `rishi.ollama` runs the whole backend against an `httpx.MockTransport` daemon, so the tests need no Ollama.

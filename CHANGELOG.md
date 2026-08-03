# Release notes

<!-- do not remove -->

## 0.1.0

A third backend - MLX on Apple silicon - plus the tool-loop hardening that goes with it.

**`rishi.mlx`.** The same `Chat` API over [mlx-lm](https://github.com/ml-explore/mlx-lm), routed
automatically from an `mlx-community` model id. It is the only backend that keeps its KV cache alive
between turns: each turn is tokenized, compared against what the cache already holds, trimmed where
the two diverge, and only the new tail is prefilled - reported as `use.cached_tokens`.
`save_cache`/`load_cache` persist a warmed cache across sessions. Also `kv_bits` for a quantized KV
cache, `draft_model` for speculative decoding, and `adapter_path` for LoRA adapters.

Vision and audio models are routed to `MlxVlmChat` (via
[mlx-vlm](https://github.com/Blaizzy/mlx-vlm), `pip install 'rishi[mlx-vlm]'`) by reading the repo's
`config.json`; `vlm=True`/`False` overrides. A text-only MLX model given an image now raises a
`TypeError` that names the extra to install rather than dropping the image silently.

**Backends are now opt-in.** `pip install rishi` no longer pulls litert-lm-api or
llama-cpp-python; install what you need with `pip install 'rishi[litert]'`, `'rishi[llama]'`, or
`'rishi[all]'`. `import rishi` works with any subset installed, and `Chat(model)` imports the backend
it needs on demand. Asking for a backend that isn't installed now names the extra to install.

**A shared tool loop.** `ToolLoopMixin` in `rishi.core` owns the Python-side tool loop for backends
that receive tool calls as data (llama today, MLX next):

- `max_steps` is now a real budget, and is enforced on **litert** too - previously litert ignored it
  entirely, so a chat with tools had no cap. Past the cap, calls are denied, the model is told why,
  and one `final_prompt` round asks for a prose answer so the turn ends with an answer instead of a
  loop. Note `max_steps` now counts tool *calls* rather than tool *rounds*.
- `parallel_tools=True` runs independent calls from one model turn concurrently. Approval stays
  sequential, so HITL prompts keep their order and the budget counts each call once; history is
  identical either way. Not supported on litert, which runs its loop inside the engine.
- A context window that fills up mid-turn is now recovered: the oldest tool results in `hist` are
  shrunk, backend state is rebuilt, and the model is asked to summarize. Only if that retry also
  fails does it raise the new `ContextWindowExceededError`.

**Closing fastllm gaps.** `chat(msg, stream='raw')` yields the underlying chunk dicts instead of
rendered markdown, for consumers that want the text/thinking/tool-call structure (`stream=True` is
unchanged). `ToolCall` builds a canonical tool call as a `dict` subclass with `.name`/`.arguments`
accessors and a `server` flag for provider-run tools, which the loop records but never executes
locally. `mk_tool_res_msg`/`mk_tool_res_msgs` are exported for driving a tool loop by hand.

**Shared OpenAI-style layer.** The message, tool-schema, think/tool-tag parsing, streaming-split and
usage/reminder callback helpers moved from `rishi.llama` into `rishi.core`, where MLX can share them.
They keep their old names in `rishi.llama`, and `rishi.llama`'s public API is unchanged.

## 0.0.4
llama cpp support addedadded

## 0.0.2
examples added


## 0.0.1
initial stateful chat for litert models

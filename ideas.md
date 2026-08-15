High value:

1. Engine.create_session + run_text_scoring — the biggest unused capability. A Session gives you run_text_scoring(targets) which returns log-likelihood scores for candidate texts. That's local, cheap classification /
   best-of-N / structured choice: chat.classify(text, ["spam","ham"]) or "rank these 5 answers" by score, no generation needed. Nothing in fastllm-over-network does this as cleanly. This is the one I'd reach for first.
2. filter_channel_content_from_kv_cache=True — a create_conversation flag you're not setting. With thinking on, the thought tokens otherwise sit in the KV cache and eat your context. Filtering them keeps token_count  
   lean — directly serves the "when do I compress" goal you built usage tracking for. Basically free to wire into Chat(think=..., filter_think=...).
3. conv.cancel_process() — no way to stop an in-flight generation right now. On CPU a long reply can run for a while; a chat.cancel() (and a timeout/KeyboardInterrupt path in the stream loop) is a real usability gap.

4. SamplerConfig ergonomics — you pass sampler_config through but don't surface temp/top_k/top_p/seed. seed especially: deterministic outputs make your engine tests assertable instead of "assert non-empty."
5. process_tool_response for redaction/truncation — you use ToolEventHandler only to record. Its actual purpose is to modify a tool result before it goes back to the model. A huge tool output (file dump, HTML)        
   currently bloats the KV unbounded; fastllm truncates (_trunc_str). A max_tool_len that truncates in process_tool_response is a cheap safeguard.
6. Finish reason / truncation signal — send_message_async surfaces "Max number of tokens reached" as a stream break; you swallow it. Capturing "this reply was cut off" (the StopReasonCallback idea we deferred) lets   
   callers know to continue.
7. render_message_to_string — chat.render(msg) to see the exact templated prompt litert will send. Pure debugging, but you're currently blind to what the model actually receives (reminder injection, tool schemas,     
   etc.).                                                                                                                                                                                                                   

8. LoRA (lora_config / lora_rank_config) — if you ever run fine-tuned adapters. 9. Benchmark — a bench() for TTFT and tokens/sec to compare CPU vs GPU vs model sizes. 10. detokenize + a count_tokens(text) helper.

fastllm patterns that would transfer

- structured() — force/parse a single tool call to get typed output (define a schema tool, read back arguments). Works on top of your existing tool + ChatToolHandler path; nice for extraction.
- Richer print_hist — you already have Resp._repr_markdown_; give each history message the same treatment and print_hist becomes a proper rendered transcript (fastllm's display_list).
- A tool-loop bound — litert's automatic_tool_calling loops internally; a model that keeps calling tools has no ceiling on your side. fastllm's max_steps is the guardrail (you'd need automatic_tool_calling=False +    
  your own loop, or trust litert's limits — worth checking what they are).                                                                                                                                                 
                
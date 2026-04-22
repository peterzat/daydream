"""LLM access layer. Everything goes through client.acompletion_json so the
v1 GPU arbiter can wrap the single call site without touching gameplay code."""

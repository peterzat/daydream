"""Versioned prompt templates. Loadable from prompts/*.txt in v1 so admins
can tune voice without a code change.

(The legacy LLM skill-router prompt, INTERPRETER_SYSTEM, was removed in the
v1.0 cleanup — free text routes through daydream/parser.py's grounded
parse. The strict-JSON drift probes that mirrored its shape live on in
tests/drift/prompts/ as adherence anchors.)"""

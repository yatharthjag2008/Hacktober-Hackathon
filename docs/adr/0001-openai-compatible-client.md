# 0001 — One OpenAI-compatible client for model access

**Status:** Accepted (2026-10-25)

## Context
The hackathon requires open-source or open-weight AI to be central to how the project works. We also want the Harness to work with any model, closed or open.

## Decision
The Harness talks to models only through the OpenAI-compatible chat-completions API with tool calling. It is configured by `base_url`, `model` and `api_key`. There are no provider-specific SDKs.

## Consequences
- Ollama, vLLM, LM Studio, OpenRouter, Groq, Together, OpenAI and Anthropic's compatible endpoint all work without extra code.
- Tool-calling quality varies across open-weight models and their servers. The small toolset (five tools) exists partly to make up for this.
- Provider-specific features (prompt caching, extended thinking) are given up.
- The demo runs an open-weight model through Ollama (`http://localhost:11434/v1`) to satisfy the hackathon rule.

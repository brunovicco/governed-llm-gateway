# ADR-0004 — Native APIs vs OpenAI-Compatible Adapters

Status: Accepted
Date: 2026-08-31

## Context

Many providers expose OpenAI-like APIs, but behavioral/capability equivalence cannot be assumed.
Creating one adapter per concrete model would couple code to catalog churn.

## Decision

Initial adapter families will be:

- native OpenAI Responses;
- native Anthropic Messages;
- native Google Gemini;
- explicit OpenAI-compatible adapter configurable for NVIDIA, Groq, OpenRouter, and compatible custom
  endpoints.

Rule: **provider API family defines adapter; concrete model defines registry entry**.

OpenAI compatibility never permits inventing unsupported capabilities. Provider quirks stay explicit.
No provider adapter is implemented in Phase 0.

## Consequences

Kimi, DeepSeek, Nemotron, or future model families can usually enter via registry/provider
configuration rather than new domain code. Native adapters remain available where semantics require
them.

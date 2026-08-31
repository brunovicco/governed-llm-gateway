# Provider configuration

Phase 0 intentionally contains no provider endpoint, API key, or provider SDK configuration.

Future provider configuration is deployment-owned. Custom compatible endpoints must be validated and
must not be caller-controlled request values, reducing SSRF/substitution risk.

# Evaluation

Gateway routing is treated as empirical optimization. Runtime code must not encode personal model
preferences such as "model X is always best for agents".

Initial benchmark classes planned by the roadmap are `structured_extraction`, `rag_ptbr`,
`code_generation`, `tool_use`, and `agent_orchestration`, later expanding to multimodal/long-context
and other classes.

Offline quality evidence is separated from online operational health. A future approved benchmark
snapshot and ranking-policy version both become routing provenance.

No private/confidential benchmark fixture may be sent to free/dev provider endpoints.

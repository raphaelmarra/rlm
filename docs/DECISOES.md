# Log de decisões do fork

| ADR | Estado | Decisão |
|---|---|---|
| `0001` | Substituída por `0003` | SDK Codex e isolamento Docker como primeira arquitetura |
| `0002` | Substituída por `0003` | CLI global, skill companheira e worker Docker |
| `0003` | Aceita | Manter SDK Codex, CLI e skill; executar o RLM em worker local confiável, sem Docker; MCP fica adiado |
| `0004` | Aceita | A skill decide quando usar RLM, o shell do Codex invoca a CLI e a resposta volta à mesma sessão; sem MCP ou `run` inicial |
| `0005` | Aceita | Não recomendar RLM como CLI genérica sobre Codex no cenário OOLONG medido |

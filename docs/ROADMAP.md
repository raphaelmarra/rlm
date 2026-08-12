# Roadmap do backend Codex

| Etapa | Entrega | Estado | Gate de saída |
|---|---|---|---|
| 0 | Fork, ambiente e spec | Em execução | spec revisada pelo usuário e ambiente reproduzível |
| 1 | `CodexClient` | Planejada | testes unitários e checks de estilo verdes |
| 2 | Smoke direto por assinatura | Planejada | chamada real com autenticação `chatgpt` e sem API key |
| 3 | RLM isolado ponta a ponta | Bloqueada | Docker disponível e trajetória raiz+subconsulta comprovada |
| 4 | Benchmark | Planejada | RLM comparado com Codex direto em fixtures controladas |
| 5 | Decisão de continuidade | Planejada | ganho, consumo e latência documentados |

Estados válidos: `Planejada`, `Em execução`, `Bloqueada`, `Concluída`.

A etapa 3 está bloqueada apenas pela ausência de Docker nesta máquina. Não há
fallback autorizado para execução de Python gerado no host.

# Roadmap da ferramenta RLM–Codex

| Etapa | Entrega | Estado | Gate de saída |
|---|---|---|---|
| 0 | Fork, ambiente e specs | Em execução | specs auditadas e plano executável versionado |
| 1 | `CodexClient` | Planejada | testes unitários e checks de estilo verdes |
| 2 | Smoke direto por assinatura | Planejada | chamada real com autenticação `chatgpt` e sem API key |
| 3 | CLI e gerenciador | Planejada | comandos e máquina de estados passam com worker falso |
| 4 | Skill global | Planejada | Codex detecta `$usar-rlm` fora do fork |
| 5 | RLM isolado ponta a ponta | Bloqueada | WSL 2 e Docker disponíveis; trajetória raiz+subconsulta comprovada |
| 6 | Controle externo pelo Codex | Planejada | processo novo do Codex opera CLI até o resultado |
| 7 | Benchmark da skill | Planejada | baseline e candidato avaliados com rubric congelada |
| 8 | Decisão de continuidade | Planejada | ganho, consumo e latência documentados |

Estados válidos: `Planejada`, `Em execução`, `Bloqueada`, `Concluída`.

A etapa 5 está bloqueada pela ausência de WSL 2 e Docker nesta máquina. Não há
fallback autorizado para execução de Python gerado no host.

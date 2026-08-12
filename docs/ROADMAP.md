# Roadmap da ferramenta RLM–Codex

| Etapa | Entrega | Estado | Gate de saída |
|---|---|---|---|
| 0 | Fork, ambiente e specs | Concluída | specs auditadas e plano executável versionado |
| 1 | `CodexClient` | Concluída | testes unitários e checks de estilo verdes |
| 2 | Smoke direto por assinatura | Concluída | chamada real com autenticação `chatgpt` e sem API key |
| 3 | CLI e gerenciador | Concluída | comandos e máquina de estados passam com worker falso |
| 4 | Skill global | Concluída | `rlm-codex doctor` detecta `$usar-rlm` sincronizada fora do fork |
| 5 | RLM local ponta a ponta | Em execução | trajetória raiz+subconsulta comprovada sem Docker e sem processo residual |
| 6 | Controle externo pelo Codex | Planejada | processo novo do Codex opera CLI até o resultado |
| 7 | Benchmark da skill | Planejada | baseline e candidato avaliados com rubric congelada |
| 8 | Decisão de continuidade | Planejada | ganho, consumo e latência documentados |

Estados válidos: `Planejada`, `Em execução`, `Bloqueada`, `Concluída`.

A etapa 5 segue o ADR 0003. O usuário autorizou execução local confiável de Python
gerado; o worker local é uma fronteira de ciclo de vida, não uma sandbox.

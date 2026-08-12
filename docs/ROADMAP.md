# Roadmap da ferramenta RLM–Codex

| Etapa | Entrega | Estado | Gate de saída |
|---|---|---|---|
| 0 | Fork, ambiente e specs | Concluída | specs auditadas e plano executável versionado |
| 1 | `CodexClient` | Concluída | testes unitários e checks de estilo verdes |
| 2 | Smoke direto por assinatura | Concluída | chamada real com autenticação `chatgpt` e sem API key |
| 3 | CLI e gerenciador | Concluída | comandos e máquina de estados passam com worker falso |
| 4 | Skill global | Concluída | `rlm-codex doctor` detecta `$usar-rlm` sincronizada fora do fork |
| 5 | RLM local ponta a ponta | Em execução | trajetória raiz+subconsulta comprovada sem Docker e sem processo residual |
| 6 | Uso pelo Codex da sessão atual | Planejada | o agente invoca RLM pelo shell e usa a resposta na tarefa |
| 7 | Portabilidade para outro Codex | Planejada | processo novo fora do checkout descobre a skill e opera a CLI |
| 8 | Benchmark da skill | Planejada | baseline e candidato avaliados com rubric congelada |
| 9 | Decisão de continuidade | Planejada | ganho, consumo e latência documentados |

Estados válidos: `Planejada`, `Em execução`, `Bloqueada`, `Concluída`.

A etapa 5 segue o ADR 0003. O usuário autorizou execução local confiável de Python
gerado; o worker local é uma fronteira de ciclo de vida, não uma sandbox.

O objetivo central e o gate de uso na sessão atual são definidos na spec vigente e no ADR
0004. A sessão externa é prova de portabilidade, não o caminho primário de uso.

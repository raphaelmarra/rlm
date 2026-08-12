# Roadmap da ferramenta RLM–Codex

| Etapa | Entrega | Estado | Gate de saída |
|---|---|---|---|
| 0 | Fork, ambiente e specs | Concluída | specs auditadas e plano executável versionado |
| 1 | `CodexClient` | Concluída | testes unitários e checks de estilo verdes |
| 2 | Smoke direto por assinatura | Concluída | chamada real com autenticação `chatgpt` e sem API key |
| 3 | CLI e gerenciador | Concluída | comandos e máquina de estados passam com worker falso |
| 4 | Skill global | Concluída | `rlm-codex doctor` detecta `$usar-rlm` sincronizada fora do fork |
| 5 | RLM local ponta a ponta | Concluída | trajetória raiz+subconsulta comprovada sem Docker e sem processo residual |
| 6 | Uso pelo Codex da sessão atual | Concluída | o agente invocou RLM pelo shell e usou a resposta para aprovar a POC |
| 7 | Portabilidade para outro Codex | Planejada | processo novo fora do checkout descobre a skill e opera a CLI |
| 8 | Benchmark OOLONG do RLM | Em execução | 50 casos oficiais, baseline e candidato avaliados com protocolo congelado |
| 9 | Decisão de continuidade | Planejada | ganho, consumo e latência documentados |

Estados válidos: `Planejada`, `Em execução`, `Bloqueada`, `Concluída`.

A etapa 5 segue o ADR 0003. O usuário autorizou execução local confiável de Python
gerado; o worker local é uma fronteira de ciclo de vida, não uma sandbox.

As etapas 5 e 6 foram fechadas pela POC KISS registrada em
`docs/reviews/2026-08-12-rlm-codex-current-session-smoke.md`. Portabilidade e
benchmark permanecem separados e não condicionam o funcionamento do núcleo.

O objetivo central e o gate de uso na sessão atual são definidos na spec vigente e no ADR
0004. A sessão externa é prova de portabilidade, não o caminho primário de uso.

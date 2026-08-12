---
status: accepted
date: 2026-08-12
deciders:
  - usuário
  - Codex
---

# ADR 0005: não recomendar RLM como CLI genérica sobre Codex no OOLONG

## Decisão

Não recomendar RLM como camada CLI genérica sobre Codex para a configuração medida:
`gpt-5.6-terra`, esforço `medium`, `LocalREPL`, OOLONG `trec_coarse` de 131K.
Recomendar a chamada Codex direta para esse workload. RLM continua disponível para
casos em que decomposição iterativa seja requisito explícito.

## Evidência

Nos oito pares pontuáveis, RLM marcou 7/8 e o direto 6/8, mas o intervalo bootstrap
de 95% para a diferença foi `[-0.25, 0.5]`. RLM usou 149 chamadas contra 8, 13,2×
mais tempo, 2,7× mais tokens de entrada e 56,6× mais tokens de saída. O relatório
canônico registra a cobertura, a falha e os artefatos em
`benchmarks/oolong_codex/reports/2026-08-12-partial-verdict.md`.

O benchmark não é apresentado como estudo completo de 25 casos nem como refutação
geral de RLM. O ganho preliminar não compensa a penalidade operacional e a
instabilidade medida.

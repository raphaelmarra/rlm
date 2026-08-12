# Changelog do fork

Todas as mudanças relevantes deste fork serão registradas aqui.

## Não lançado

### Adicionado

- Fork dedicado `raphaelmarra/rlm` em `Desktop/RLM`.
- Ambiente Python 3.11 reproduzível com grupos de desenvolvimento e teste.
- Extra opcional `codex` baseado em `openai-codex 0.144.4`.
- Spec, ADR e estrutura de governança do backend Codex por assinatura.
- Auditoria de coerência e coesão da spec, com `15 PASSA` e `0 FALHA`.

### Verificado

- Baseline upstream: `271` testes passaram e `63` foram ignorados.
- Codex CLI e SDK reconhecem autenticação pela conta ChatGPT.
- Dois imports herdados do upstream foram apenas reordenados para restaurar o
  baseline verde do Ruff, sem mudança de comportamento.

### Limitação conhecida

- Docker não está instalado; o smoke RLM isolado permanece bloqueado.

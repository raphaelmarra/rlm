# Changelog do fork

Todas as mudanças relevantes deste fork serão registradas aqui.

## Não lançado

### Adicionado

- Fork dedicado `raphaelmarra/rlm` em `Desktop/RLM`.
- Ambiente Python 3.11 reproduzível com grupos de desenvolvimento e teste.
- Extra opcional `codex` baseado em `openai-codex 0.144.4`.
- Spec, ADR e estrutura de governança do backend Codex por assinatura.
- Auditoria de coerência e coesão da spec, com `15 PASSA` e `0 FALHA`.
- Spec e ADR da CLI global e da skill que tornam o RLM controlável pelo Codex.
- Auditoria da spec da ferramenta, com `15 PASSA` e `0 FALHA`.
- Plano executável TDD cobrindo backend, CLI, worker, Docker, skill e provas reais.
- Auditoria do plano executável, com `15 PASSA` e `0 FALHA`.
- Cliente `CodexClient` por assinatura, sem API key, com caminhos síncrono e assíncrono.
- Protocolo durável de jobs, armazenamento atômico, worker, cancelamento e CLI JSON/JSONL.
- Isolamento Docker por run com rede interna, usuário sem privilégio, limites e limpeza por rótulo.
- Skill `$usar-rlm`, referência operacional e instalador global idempotente com manifesto de origem.
- Diagnóstico de integridade da skill por commit e hashes SHA-256.
- Spec e ADR da arquitetura local confiável, preservando CLI, skill e trabalhos
  duráveis sem exigir Docker ou WSL 2.
- Auditoria da spec local, com `15 PASSA` e `0 FALHA`.

### Alterado

- A decisão vigente troca `DockerREPL` por `LocalREPL` no worker `rlm-codex` e
  explicita que o worker local não constitui sandbox.
- As specs, ADRs e o plano Docker foram preservados como histórico substituído.

### Verificado

- Baseline upstream: `271` testes passaram e `63` foram ignorados.
- Codex CLI e SDK reconhecem autenticação pela conta ChatGPT.
- Smoke real do SDK retornou `RLM_CODEX_OK` usando a assinatura ChatGPT.
- Suíte determinística da ferramenta chegou a `93 passed, 1 skipped` após a instalação da skill.
- `rlm-codex doctor` resolveu fora do fork e marcou somente os checks Docker como indisponíveis.
- Dois imports herdados do upstream foram apenas reordenados para restaurar o
  baseline verde do Ruff, sem mudança de comportamento.

### Limitação conhecida

- Python gerado pelo RLM local terá as permissões do usuário que iniciar a CLI;
  corpus não confiável não deve ser usado.

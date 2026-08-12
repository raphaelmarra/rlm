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
- Skill `$usar-rlm`, referência operacional e instalador global idempotente com manifesto de origem.
- Diagnóstico de integridade da skill por commit e hashes SHA-256.
- Spec e ADR da arquitetura local confiável, preservando CLI, skill e trabalhos
  duráveis sem exigir Docker ou WSL 2.
- Auditoria da spec local, com `15 PASSA` e `0 FALHA`.
- Objetivo central e ADR de uso na sessão atual: a skill decide, o shell do Codex
  invoca a CLI e a resposta RLM retorna ao mesmo agente.
- Plano TDD da execução local, incluindo smokes reais, auto-uso pelo Codex,
  portabilidade, benchmark controlado e fechamento dos treze critérios de aceite.
- Smoke real opt-in de um único fluxo `start → result --wait`, com `LocalREPL` e
  exatamente uma `llm_query`.
- Desenho do benchmark OOLONG isolado com 50 casos oficiais de 131K, baseline direto,
  RLM profundidade 1 e scorer upstream.

### Alterado

- A decisão vigente troca `DockerREPL` por `LocalREPL` no worker `rlm-codex` e
  explicita que o worker local não constitui sandbox.
- As specs, ADRs e o plano Docker foram preservados como histórico substituído.
- A saída JSON/JSONL da CLI passou a escapar caracteres fora de ASCII para funcionar
  também em consoles Windows configurados com `cp1252`.

### Verificado

- Baseline upstream: `271` testes passaram e `63` foram ignorados.
- Codex CLI e SDK reconhecem autenticação pela conta ChatGPT.
- Smoke real do SDK retornou `RLM_CODEX_OK` usando a assinatura ChatGPT.
- Suíte determinística da ferramenta: `92 passed, 1 skipped`.
- `rlm-codex doctor` resolveu fora do fork com autenticação `chatgpt`, skill sincronizada
  e modo `local trusted execution; not sandboxed`.
- POC na sessão atual: run `20260812T150510Z-48daec12` retornou
  `RLM-CODEX-7391`, registrou uma `llm_query`, ambiente `local` e encerrou o worker.
- Smoke real reproduzível: `1 passed in 22.33s` com `RLM_LIVE_CODEX=1`.
- Dois imports herdados do upstream foram apenas reordenados para restaurar o
  baseline verde do Ruff, sem mudança de comportamento.

### Limitação conhecida

- Python gerado pelo RLM local terá as permissões do usuário que iniciar a CLI;
  corpus não confiável não deve ser usado.

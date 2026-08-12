# Índice do fork RLM–Codex

Este índice separa a documentação específica do fork da documentação upstream.

## Documentação do fork

| Documento | Função | Diátaxis |
|---|---|---|
| `docs/STRUCTURE.md` | Locais canônicos dos artefatos do fork | Referência |
| `docs/ROADMAP.md` | Etapas e gates reais da integração | How-to |
| `docs/CHANGELOG.md` | Histórico de marcos do fork | Referência |
| `docs/DECISOES.md` | Log das decisões arquiteturais | Referência |
| `docs/ABERTO.md` | Dependências e questões ainda abertas | Referência |
| `docs/SOURCES.md` | Fontes externas utilizadas | Referência |
| `docs/DESCARTADO.md` | Questões e caminhos retirados, com justificativa | Referência |
| `docs/superpowers/specs/2026-08-12-rlm-codex-local-execution-design.md` | Spec vigente da CLI, skill, backend Codex e worker local confiável | Explicação |
| `docs/superpowers/specs/2026-08-12-codex-subscription-backend-design.md` | Spec histórica substituída pela execução local | Explicação |
| `docs/superpowers/specs/2026-08-12-rlm-tool-for-codex-design.md` | Spec histórica substituída pela execução local | Explicação |
| `docs/superpowers/plans/README.md` | Convenção dos planos executáveis | Referência |
| `docs/superpowers/plans/2026-08-12-rlm-codex-implementation.md` | Plano histórico da implementação Docker, substituído | How-to |
| `docs/superpowers/plans/2026-08-12-rlm-codex-local-execution.md` | Plano TDD vigente da execução local e das provas pelo Codex | How-to |
| `docs/decisions/0001-sdk-codex-como-backend-de-assinatura.md` | Decisão histórica do backend e Docker, substituída por `0003` | Explicação |
| `docs/decisions/0002-cli-global-e-skill-como-superficie-do-codex.md` | Decisão histórica da CLI/skill com Docker, substituída por `0003` | Explicação |
| `docs/decisions/0003-cli-skill-e-worker-local-confiavel.md` | Decisão vigente: CLI + skill + worker local confiável | Explicação |
| `docs/decisions/0004-skill-decide-e-shell-invoca-o-rlm.md` | Decisão vigente: descoberta por skill e invocação pelo shell na mesma sessão | Explicação |
| `.agents/skills/usar-rlm/SKILL.md` | Fluxo operacional do Codex para runs RLM extensos | How-to |
| `.agents/skills/usar-rlm/references/protocol.md` | Contrato JSON, estados e códigos da CLI `rlm-codex` | Referência |
| `docs/reviews/2026-08-12-codex-subscription-backend-spec-audit.md` | Auditoria de coerência e coesão da spec | Referência |
| `docs/reviews/2026-08-12-rlm-tool-for-codex-spec-audit.md` | Auditoria de coerência e coesão da spec da ferramenta | Referência |
| `docs/reviews/2026-08-12-rlm-codex-plan-audit.md` | Auditoria de coerência e coesão do plano executável | Referência |
| `docs/reviews/2026-08-12-rlm-codex-local-execution-spec-audit.md` | Auditoria da spec local vigente, com 15 critérios | Referência |
| `docs/reviews/2026-08-12-rlm-codex-current-session-smoke.md` | Evidência da POC KISS executada pelo Codex da sessão atual | Referência |

## Documentação upstream

| Local | Função |
|---|---|
| `README.md` | Visão geral e instalação do RLM |
| `AGENTS.md` | Regras de contribuição e contratos dos clientes |
| `docs/getting-started.md` | Introdução upstream |
| `docs/architecture.md` | Arquitetura upstream |
| `docs/api/rlm.md` | API pública upstream |
| `docs/src/` | Site da documentação upstream |

O plano Docker permanece como registro histórico. A implementação vigente segue o
plano local derivado da spec aprovada.

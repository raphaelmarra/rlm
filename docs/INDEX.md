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
| `docs/superpowers/specs/2026-08-12-codex-subscription-backend-design.md` | Spec do backend Codex por assinatura | Explicação |
| `docs/superpowers/specs/2026-08-12-rlm-tool-for-codex-design.md` | Spec da CLI e skill que tornam o RLM controlável pelo Codex | Explicação |
| `docs/superpowers/plans/README.md` | Convenção dos planos executáveis | Referência |
| `docs/superpowers/plans/2026-08-12-rlm-codex-implementation.md` | Plano TDD do backend, CLI, Docker e skill | How-to |
| `docs/decisions/0001-sdk-codex-como-backend-de-assinatura.md` | Escolha do SDK e do isolamento | Explicação |
| `docs/decisions/0002-cli-global-e-skill-como-superficie-do-codex.md` | Escolha da CLI global e da skill companheira | Explicação |
| `.agents/skills/usar-rlm/SKILL.md` | Fluxo operacional do Codex para runs RLM extensos | How-to |
| `.agents/skills/usar-rlm/references/protocol.md` | Contrato JSON, estados e códigos da CLI `rlm-codex` | Referência |
| `docs/reviews/2026-08-12-codex-subscription-backend-spec-audit.md` | Auditoria de coerência e coesão da spec | Referência |
| `docs/reviews/2026-08-12-rlm-tool-for-codex-spec-audit.md` | Auditoria de coerência e coesão da spec da ferramenta | Referência |
| `docs/reviews/2026-08-12-rlm-codex-plan-audit.md` | Auditoria de coerência e coesão do plano executável | Referência |

## Documentação upstream

| Local | Função |
|---|---|
| `README.md` | Visão geral e instalação do RLM |
| `AGENTS.md` | Regras de contribuição e contratos dos clientes |
| `docs/getting-started.md` | Introdução upstream |
| `docs/architecture.md` | Arquitetura upstream |
| `docs/api/rlm.md` | API pública upstream |
| `docs/src/` | Site da documentação upstream |

O plano de implementação da ferramenta está versionado em
`docs/superpowers/plans/2026-08-12-rlm-codex-implementation.md` e mantém
rastreabilidade com as duas specs.

# Estrutura canônica do fork

O fork preserva a organização upstream e adiciona somente os artefatos
necessários ao backend e à ferramenta Codex.

| Conteúdo | Local canônico | Estado |
|---|---|---|
| Cliente de linguagem | `rlm/clients/codex.py` | Planejado |
| CLI e gerenciador de trabalhos | `rlm/codex_tool/` | Planejado |
| Registro de clientes | `rlm/clients/__init__.py` | Existente; alteração planejada |
| Tipos públicos de backend | `rlm/core/types.py` | Existente; alteração planejada |
| Testes unitários do cliente | `tests/clients/test_codex.py` | Planejado |
| Testes da ferramenta | `tests/codex_tool/` | Planejado |
| Testes reais opt-in | `tests/live/` | Planejado |
| Exemplo seguro | `examples/codex_subscription.py` | Planejado |
| Skill versionada | `.agents/skills/usar-rlm/` | Planejado |
| Instalador local | `scripts/install_codex_tool.ps1` | Planejado |
| Specs | `docs/superpowers/specs/` | Existente; specs aprovadas |
| Planos executáveis | `docs/superpowers/plans/` | Existente; plano em execução |
| Decisões e trade-offs | `docs/decisions/` | Existente |
| Auditorias de documentação | `docs/reviews/` | Existente |
| Estado e governança do fork | `docs/INDEX.md`, `docs/ROADMAP.md`, `docs/CHANGELOG.md`, `docs/DECISOES.md`, `docs/ABERTO.md`, `docs/SOURCES.md` | Existente |

Arquivos da documentação upstream continuam em seus caminhos atuais. Um fato
específico do fork deve ter um único dono nos documentos acima; outros arquivos
apontam para ele.

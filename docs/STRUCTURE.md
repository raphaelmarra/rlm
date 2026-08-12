# Estrutura canônica do fork

O fork preserva a organização upstream e adiciona somente os artefatos
necessários ao backend e à ferramenta Codex.

| Conteúdo | Local canônico | Estado |
|---|---|---|
| Cliente de linguagem | `rlm/clients/codex.py` | Implementado e testado |
| CLI e gerenciador de trabalhos | `rlm/codex_tool/` | Implementado e testado |
| Registro de clientes | `rlm/clients/__init__.py` | Atualizado |
| Tipos públicos de backend | `rlm/core/types.py` | Atualizado |
| Testes unitários do cliente | `tests/clients/test_codex.py` | Existente |
| Testes da ferramenta | `tests/codex_tool/` | Existente |
| Testes reais opt-in | `tests/live/` | Smoke direto existente; smokes locais especificados |
| Exemplo seguro | `examples/codex_subscription.py` | Existente |
| Skill versionada | `.agents/skills/usar-rlm/` | Implementada e instalada no perfil |
| Instalador local | `scripts/install_codex_tool.ps1` | Implementado e testado |
| Specs | `docs/superpowers/specs/` | Spec local vigente; specs Docker preservadas como histórico |
| Planos executáveis | `docs/superpowers/plans/` | Plano Docker histórico e plano local vigente |
| Decisões e trade-offs | `docs/decisions/` | Existente |
| Auditorias de documentação | `docs/reviews/` | Existente |
| Estado e governança do fork | `docs/INDEX.md`, `docs/ROADMAP.md`, `docs/CHANGELOG.md`, `docs/DECISOES.md`, `docs/ABERTO.md`, `docs/DESCARTADO.md`, `docs/SOURCES.md` | Existente |

Arquivos da documentação upstream continuam em seus caminhos atuais. Um fato
específico do fork deve ter um único dono nos documentos acima; outros arquivos
apontam para ele.

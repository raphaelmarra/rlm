# Estrutura canônica do fork

O fork preserva a organização upstream e adiciona somente os artefatos
necessários ao backend Codex.

| Conteúdo | Local canônico | Estado |
|---|---|---|
| Cliente de linguagem | `rlm/clients/codex.py` | Planejado |
| Registro de clientes | `rlm/clients/__init__.py` | Existente; alteração planejada |
| Tipos públicos de backend | `rlm/core/types.py` | Existente; alteração planejada |
| Testes unitários do cliente | `tests/clients/test_codex.py` | Planejado |
| Testes reais opt-in | `tests/live/` | Planejado |
| Exemplo seguro | `examples/codex_subscription.py` | Planejado |
| Specs | `docs/superpowers/specs/` | Existente; spec em revisão |
| Planos executáveis | `docs/superpowers/plans/` | Reservado; sem plano aprovado |
| Decisões e trade-offs | `docs/decisions/` | Existente |
| Auditorias de documentação | `docs/reviews/` | Existente |
| Estado e governança do fork | `docs/INDEX.md`, `docs/ROADMAP.md`, `docs/CHANGELOG.md`, `docs/DECISOES.md`, `docs/ABERTO.md`, `docs/SOURCES.md` | Existente |

Arquivos da documentação upstream continuam em seus caminhos atuais. Um fato
específico do fork deve ter um único dono nos documentos acima; outros arquivos
apontam para ele.

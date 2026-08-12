---
status: accepted
date: 2026-08-12
deciders:
  - usuário
  - Codex
supersedes:
  - 0001
  - 0002
---

# ADR 0003: usar CLI, skill e worker local confiável

## Contexto

Os registros de decisão arquitetural (ADRs) 0001 e 0002 escolheram corretamente o
kit de desenvolvimento (SDK) Codex, a interface de linha de comando (CLI) global e
a skill, mas também tornaram Docker e Windows Subsystem for Linux 2 (WSL 2)
requisitos obrigatórios para executar o Recursive Language Model (RLM).
Essa dependência bloqueou o único smoke ponta a ponta restante e acrescentou
instalação, daemon, imagem, rede e limpeza de containers a uma ferramenta local.

A inspeção do fork confirmou que a CLI já inicia cada trabalho em um worker local,
que é um processo separado, e que o `LocalREPL` já implementa o contrato completo do RLM, incluindo
`llm_query` e `rlm_query`. Os testes combinados de cliente Codex, `LocalREPL`,
recursão e ferramenta passaram (`183 passed, 1 skipped`), e o smoke real do cliente
Codex pela assinatura ChatGPT também passou.

## Decisão

Manter o SDK oficial Codex como backend, somente com autenticação `chatgpt`, e
manter `rlm-codex` com `$usar-rlm` como superfície canônica. Trocar o executor da
ferramenta de `DockerREPL` para `LocalREPL`, dentro do worker local que já
existe. Remover Docker e WSL 2 dos preflights, do instalador e dos testes da
ferramenta.

O worker local oferece separação de ciclo de vida, heartbeat e cancelamento, mas não é
uma sandbox. O Python gerado pode usar as permissões do usuário, incluindo acesso a
arquivos, rede, imports e ambiente. O usuário aceitou explicitamente essa fronteira
de confiança.

Model Context Protocol (MCP) permanece adiado. Se necessário no futuro, deverá ser um adaptador fino sobre o
mesmo `JobManager`, após uma necessidade que a CLI não atenda ser demonstrada.

## Consequências

- A ferramenta deixa de depender de WSL 2, Docker Desktop, daemon e imagens.
- O caminho principal reutiliza componentes locais já implementados e testados.
- A CLI, o protocolo durável e a skill permanecem estáveis para o agente.
- Cancelamento forçado encerra a árvore local, sem limpeza de containers ou redes.
- Corpus não confiável passa a representar risco para os dados acessíveis ao
  usuário; documentação e diagnóstico devem dizer isso sem eufemismo.
- O `DockerREPL` upstream permanece disponível, mas não integra o caminho
  `rlm-codex`.

## Alternativas rejeitadas

### MCP como primeira superfície

Não reduz o risco do executor e adiciona servidor STDIO, configuração e schemas.
Será reconsiderado somente com benefício concreto sobre CLI + skill.

### Comando síncrono `ask`

Reduziria a superfície aparente, mas perderia acompanhamento, recuperação e
cancelamento de trabalhos longos. A skill já esconde a sequência operacional do
usuário.

### Orquestração sem Python

Evitaria execução local de código, mas deixaria de oferecer a semântica do RLM que
o projeto pretende expor.

## Referência canônica

- `docs/superpowers/specs/2026-08-12-rlm-codex-local-execution-design.md`

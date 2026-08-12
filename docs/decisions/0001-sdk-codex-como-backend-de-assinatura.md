---
status: accepted
date: 2026-08-12
deciders:
  - usuário
  - Codex
---

# ADR 0001: usar o SDK Codex como backend de assinatura

## Contexto

O RLM suporta clientes de API e modelos locais, mas não reutiliza a assinatura
ChatGPT quando configurado com o backend OpenAI. O objetivo deste fork é provar
o RLM real com o Codex sem cobrança separada da API.

Foram consideradas três pontes: subprocesso `codex exec`, SDK oficial e proxy
local compatível com OpenAI. O RLM precisa de respostas síncronas e assíncronas,
uso estruturado e autenticação verificável.

## Decisão

Criar um cliente `BaseLM` baseado no SDK Python oficial `openai-codex`, instalado
como extra opcional. O cliente aceitará somente autenticação de tipo `chatgpt`,
usará threads efêmeras, sandbox somente leitura, diretório temporário vazio e
negação de todas as elevações.

O teste RLM ponta a ponta usará Docker. A ausência de Docker interrompe esse
gate e não autoriza fallback para o REPL local.

O comportamento completo é definido na
`docs/superpowers/specs/2026-08-12-codex-subscription-backend-design.md`.

## Consequências

- A integração usa uma interface oficial e estruturada.
- A dependência binária permanece opcional para usuários do RLM.
- Chamadas consomem a franquia da assinatura ChatGPT.
- Uma instância curta do app-server por chamada aumenta a latência inicial, mas
  evita vazamento de processo e estado implícito nesta primeira versão.
- Docker torna-se requisito apenas do smoke RLM real, não dos testes unitários.
- Suporte a Claude, MCP e API paga permanece fora do escopo.

## Alternativas rejeitadas

### `codex exec`

É viável, mas exigiria controlar subprocessos e interpretar saída que o SDK já
entrega como objetos tipados.

### Proxy compatível com OpenAI

Evitaria alterar o registro do RLM, mas adicionaria servidor, porta e protocolo
local sem reduzir os riscos da integração.

### Codex como MCP

MCP expõe o Codex como ferramenta. O ponto de extensão necessário aqui é um
modelo `BaseLM`, portanto MCP não substitui o backend.

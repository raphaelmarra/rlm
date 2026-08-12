---
status: accepted
date: 2026-08-12
deciders:
  - usuário
  - Codex
---

# ADR 0002: usar CLI global e skill como superfície do Codex

## Contexto

O ADR 0001 escolheu o SDK oficial para o RLM consultar a assinatura ChatGPT, mas
essa decisão não oferece ao Codex uma ferramenta descoberta e gerenciável. O objetivo
do fork exige que o Codex opere o RLM de qualquer projeto, acompanhe trabalhos longos
e recupere resultados sem código Python ad hoc.

A documentação oficial recomenda CLIs componíveis disponíveis de qualquer pasta e
skills companheiras para fluxos repetidos. MCP também é suportado, mas exige servidor,
configuração e reinicialização do cliente.

## Decisão

Criar a CLI `rlm-codex` como contrato operacional canônico e a skill `$usar-rlm`
como instrução de descoberta e uso. A CLI persistirá trabalhos no perfil do usuário,
usará JSON/JSON Lines e exporá diagnóstico, início, status, eventos, resultado,
cancelamento, listagem e limpeza.

O comando será instalado globalmente por `uv tool`; a skill terá fonte versionada no
fork e cópia instalada em `~/.codex/skills`. O worker executará o backend do ADR 0001
e o `DockerREPL`. WSL 2 e Docker Desktop são requisitos operacionais desta máquina.

MCP não faz parte do primeiro gate. Se for adicionado, será um adaptador sem estado
que chama o mesmo gerenciador, nunca uma segunda implementação.

## Consequências

- O Codex pode operar o RLM sem conhecer o caminho ou a API Python do fork.
- Trabalhos sobrevivem ao processo que executou `start` e possuem histórico auditável.
- O protocolo JSON permite futura integração MCP sem quebrar a CLI.
- A instalação global cria estado fora dos repositórios e precisa detectar drift.
- O isolamento real depende de WSL 2 e Docker Desktop no Windows atual.
- O RLM continua sem fallback para execução de Python no host.

## Alternativas rejeitadas

### Skill chamando `uv run`

Rejeitada porque acopla a ferramenta ao checkout e não entrega gerenciamento de
trabalhos.

### MCP primeiro

Adiado porque acrescenta servidor e configuração antes da prova do executor. Pode ser
adicionado sobre a CLI quando houver benefício demonstrado.

### Serviço HTTP residente

Rejeitado porque expõe porta e ciclo de vida sem necessidade para uso local.

## Referências

- `docs/superpowers/specs/2026-08-12-rlm-tool-for-codex-design.md`
- `docs/decisions/0001-sdk-codex-como-backend-de-assinatura.md`

---
status: accepted
date: 2026-08-12
deciders:
  - usuário
  - Codex
supplements:
  - 0003
---

# ADR 0004: a skill decide e o shell invoca o RLM

## Contexto

“Transformar o RLM em ferramenta do Codex” pode significar duas arquiteturas
diferentes: registrar uma ferramenta MCP de primeira classe ou ensinar o agente a
usar um executável por sua ferramenta de shell. O requisito real é que o próprio
Codex possa recorrer ao RLM opcionalmente durante a sessão atual para
facilitar uma tarefa, sem Docker e sem pedir que o usuário opere o protocolo.

Nesta sessão, `$usar-rlm` já está na lista de skills, `rlm-codex.exe` já resolve no
`PATH`, a instalação `uv tool` é editável e o Codex já possui shell. Não existe MCP
configurado. A documentação oficial descreve skills como instruções ativadas
implícita ou explicitamente e recomenda uma CLI no `PATH` com skill companheira.
Clientes MCP carregam servidores configurados e podem exigir reinicialização.

## Decisão

Usar a descrição da skill como descoberta e política de decisão, o corpo da skill
como procedimento, o shell já disponível como ferramenta de invocação e
`rlm-codex` como adaptador executável. O resultado JSON volta ao
Codex da sessão atual, que deve usá-lo na tarefa original.

Não adicionar MCP nem um comando síncrono `run` nesta etapa. O caminho feliz usa
`doctor` uma vez por sessão, `start` uma vez por trabalho e `result --wait` para
recuperação. `status` e `events` ficam condicionais a demora ou diagnóstico.

## Consequências

- Nenhuma reinicialização ou nova sessão é necessária para o uso normal.
- O usuário não precisa escolher comandos nem acompanhar manualmente um `run-id`;
  essa responsabilidade pertence à skill e ao agente.
- A interface durável existente continua sendo a única implementação operacional.
- O uso pelo Codex da sessão atual passa a ser gate anterior ao teste em sessão
  nova.
- MCP e `run` só serão reconsiderados se uso real demonstrar uma lacuna concreta.

## Referências

- `docs/superpowers/specs/2026-08-12-rlm-codex-local-execution-design.md`
- https://learn.chatgpt.com/docs/build-skills
- https://learn.chatgpt.com/use-cases/agent-friendly-clis
- https://learn.chatgpt.com/docs/extend/mcp?surface=cli

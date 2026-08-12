# Auditoria da spec RLM–Codex com execução local

**Documento auditado:**
`docs/superpowers/specs/2026-08-12-rlm-codex-local-execution-design.md`<br>
**Data:** 2026-08-12<br>
**Método:** checklist de coerência e coesão em camada mecânica e semântica

## Resultado

| # | Dimensão | Veredito | Evidência | Correção sugerida |
|---:|---|---|---|---|
| 1 | Termo canônico grafado igualmente | PASSA | “Codex da sessão atual”, “worker local”, `LocalREPL`, CLI e MCP são usados de forma estável (`spec:12-25`, `spec:102-128`, `spec:132-174`) | — |
| 2 | Um nome por conceito | PASSA | O agente consumidor é sempre “Codex da sessão atual” (`spec:53-54`, `spec:108-128`, `spec:179-197`); o executor é sempre “worker local” (`spec:20-21`, `spec:143-157`) | — |
| 3 | Um conceito por nome | PASSA | descrição/corpo da skill, shell, CLI, worker e Codex consumidor têm papéis diferentes na tabela de integração (`spec:102-113`) | — |
| 4 | Acrônimos definidos na primeira ocorrência | PASSA | RLM, CLI, JSON, MCP e WSL 2 são expandidos no resumo antes do uso abreviado (`spec:12-22`) | — |
| 5 | Ausência de conflito direto | PASSA | O shell é a ferramenta de invocação (`spec:75-78`, `spec:102-113`) e MCP permanece explicitamente adiado (`spec:81-88`); o worker é ciclo de vida, não segurança (`spec:156-159`, `spec:219-233`) | — |
| 6 | Condições e exceções consistentes | PASSA | `run` e MCP só voltam à decisão após lacuna observada (`spec:81-100`); Docker sai apenas de `rlm-codex`, enquanto `DockerREPL` upstream permanece (`spec:174-175`) | — |
| 7 | Sem duplicação divergente | PASSA | Objetivo central, fluxo, testes e aceite exigem o mesmo retorno ao Codex da sessão atual (`spec:27-37`, `spec:177-197`, `spec:260-275`, `spec:287-309`) | — |
| 8 | Sem dependência circular | PASSA | O fluxo é unidirecional: skill → shell → CLI → gerenciador/store → worker → RLM → resultado → Codex (`spec:102-113`, `spec:132-153`, `spec:177-197`) | — |
| 9 | Referências resolvem | PASSA | Os paths citados em componentes e metadados existem; o índice aponta a spec e os ADRs 0003/0004 (`docs/INDEX.md:15-24`) | — |
| 10 | Anáforas inequívocas | PASSA | “Esse worker” retoma “worker local” na mesma sentença (`spec:20-21`); “Ele” retoma o snapshot no parágrafo contíguo (`spec:199-200`) | — |
| 11 | Um assunto por seção | PASSA | Descoberta, arquitetura, componentes, fluxo, CLI, confiança, erros e testes têm seções separadas (`spec:102`, `spec:132`, `spec:161`, `spec:177`, `spec:202`, `spec:219`, `spec:236`, `spec:248`) | — |
| 12 | Regras sob cabeçalho correto | PASSA | Política do agente fica em “Como o Codex descobre”, riscos em “Fronteira de confiança” e gates em “Critérios de aceite” (`spec:102-128`, `spec:219-245`, `spec:287-309`) | — |
| 13 | Progressão lógica | PASSA | O documento progride de objetivo e opções para integração do agente, arquitetura, fluxo, segurança, testes e aceite (`spec:10-316`) | — |
| 14 | Transições explícitas | PASSA | “Portanto” liga o shell existente à dispensa de nova ferramenta (`spec:75-78`); “Por isso” liga permissões ao requisito de confiança (`spec:231-233`); o benchmark depende do ponta a ponta verde (`spec:278-285`) | — |
| 15 | Unidade de propósito | PASSA | A definição final de “funcional” exige escolha, invocação e aproveitamento pelo Codex da sessão atual, além de portabilidade (`spec:287-316`) | — |

## Camada mecânica

- Nenhum `TBD`, `TODO`, `FIXME`, placeholder ou referência órfã foi encontrado.
- Os ADRs 0001 e 0002 têm `status: superseded` e `superseded-by: 0003`; o ADR
  0003 lista ambos em `supersedes`.
- O ADR 0004 suplementa o ADR 0003 sem alterar sua decisão de execução local.
- `docs/DECISOES.md` e `docs/INDEX.md` identificam os ADRs 0003/0004 e a nova spec
  como vigentes.
- `git diff --check` passou sem erro.

## Camada semântica

A distinção entre sandbox do backend Codex e execução não isolada do `LocalREPL` é
explícita. O worker local não recebe garantias que pertenciam ao Docker. A única
exceção histórica — manter `DockerREPL` para usuários upstream — está limitada ao
componente genérico e não reabre fallback no `rlm-codex`.

A descrição da skill, o shell e a CLI não são tratados como três implementações da
mesma ferramenta: são descoberta, invocação e execução, respectivamente. O uso na
sessão atual é o gate primário; uma sessão nova prova apenas portabilidade.

## Veredito

**15 PASSA, 0 FALHA.** Não restou defeito bloqueante. Top-3 defeitos: nenhum.

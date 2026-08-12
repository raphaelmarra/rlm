# Auditoria da spec RLM–Codex com execução local

**Documento auditado:**
`docs/superpowers/specs/2026-08-12-rlm-codex-local-execution-design.md`<br>
**Data:** 2026-08-12<br>
**Método:** checklist de coerência e coesão em camada mecânica e semântica

## Resultado

| # | Dimensão | Veredito | Evidência | Correção sugerida |
|---:|---|---|---|---|
| 1 | Termo canônico grafado igualmente | PASSA | “worker local”, `LocalREPL`, CLI e MCP são usados de forma estável (`spec:12-25`, `spec:52-75`, `spec:101-120`) | — |
| 2 | Um nome por conceito | PASSA | O processo executor é definido uma vez como “worker local” (`spec:20-21`) e esse nome é reutilizado no fluxo (`spec:131-138`) | — |
| 3 | Um conceito por nome | PASSA | `CodexClient`, `LocalREPL`, `JobManager` e `RunStore` possuem papéis distintos na arquitetura e na tabela de componentes (`spec:77-120`) | — |
| 4 | Acrônimos definidos na primeira ocorrência | PASSA | RLM, CLI, JSON, MCP e WSL 2 são expandidos no resumo antes do uso abreviado (`spec:12-22`) | — |
| 5 | Ausência de conflito direto | PASSA | O worker é explicitamente fronteira de ciclo de vida e não de segurança (`spec:101-104`); a fronteira de confiança repete a mesma regra (`spec:161-176`) | — |
| 6 | Condições e exceções consistentes | PASSA | Docker sai apenas do caminho `rlm-codex`, enquanto `DockerREPL` upstream permanece disponível (`spec:116-120`) | — |
| 7 | Sem duplicação divergente | PASSA | Objetivos, fluxo, testes e aceite exigem a mesma CLI, worker local, assinatura ChatGPT e ausência de Docker (`spec:27-40`, `spec:122-142`, `spec:190-215`, `spec:226-246`) | — |
| 8 | Sem dependência circular | PASSA | O fluxo é unidirecional: skill → CLI → gerenciador/store → worker → RLM → cliente Codex (`spec:77-99`, `spec:124-139`) | — |
| 9 | Referências resolvem | PASSA | Os onze paths citados em componentes e metadados existem; `Test-Path` retornou `True` para todos. O índice aponta a spec e o ADR 0003 (`docs/INDEX.md:15-23`) | — |
| 10 | Anáforas inequívocas | PASSA | “Esse worker” retoma “worker local” na mesma sentença (`spec:20-21`); “Ele” retoma o snapshot no parágrafo contíguo (`spec:141-142`) | — |
| 11 | Um assunto por seção | PASSA | Arquitetura, componentes, fluxo, CLI, confiança, erros e testes têm seções separadas (`spec:77`, `spec:106`, `spec:122`, `spec:144`, `spec:161`, `spec:178`, `spec:190`) | — |
| 12 | Regras sob cabeçalho correto | PASSA | Riscos ficam em “Fronteira de confiança”, estados excepcionais em “Erros e cancelamento” e gates em “Critérios de aceite” (`spec:161-188`, `spec:226-246`) | — |
| 13 | Progressão lógica | PASSA | O documento progride de propósito e alternativas para arquitetura, fluxo, segurança, testes e aceite (`spec:10-253`) | — |
| 14 | Transições explícitas | PASSA | “Por isso” conecta capacidades locais ao requisito de confiança (`spec:173-176`); “Depois do ponta a ponta verde” condiciona o benchmark (`spec:217-224`) | — |
| 15 | Unidade de propósito | PASSA | Todos os critérios convergem para a definição final de “funcional” como descoberta, operação e resposta RLM real (`spec:226-253`) | — |

## Camada mecânica

- Nenhum `TBD`, `TODO`, `FIXME`, placeholder ou referência órfã foi encontrado.
- Os ADRs 0001 e 0002 têm `status: superseded` e `superseded-by: 0003`; o ADR
  0003 lista ambos em `supersedes`.
- `docs/DECISOES.md` e `docs/INDEX.md` identificam somente o ADR 0003 e a nova spec
  como vigentes.
- `git diff --check` passou sem erro.

## Camada semântica

A distinção entre sandbox do backend Codex e execução não isolada do `LocalREPL` é
explícita. O worker local não recebe garantias que pertenciam ao Docker. A única
exceção histórica — manter `DockerREPL` para usuários upstream — está limitada ao
componente genérico e não reabre fallback no `rlm-codex`.

## Veredito

**15 PASSA, 0 FALHA.** Não restou defeito bloqueante. Top-3 defeitos: nenhum.

---
name: usar-rlm
description: Use when a task requires analysis of a large corpus, searching many files, recursive decomposition or subqueries, or explicitly asks for RLM; not for simple questions with a direct local answer.
---

# Usar RLM

## Visão geral

Use `rlm-codex` para delegar análise extensa a um Recursive Language Model isolado. Um run é uma execução durável: inicie uma vez, preserve o `run.id` e acompanhe a mesma execução até um estado terminal. Use o valor de `run.id` onde os comandos mostram `<run-id>`.

## Decidir

Use esta skill quando houver corpus grande, busca em muitos arquivos, necessidade real de decomposição/subconsultas ou pedido explícito por RLM.

Não use para pergunta simples, arquivo único já conhecido, alteração local direta ou tarefa que o Codex atual resolve sem decomposição. Nesses casos, responda ou trabalhe diretamente.

## Executar

1. Rode `rlm-codex doctor`. Se algum check falhar, não inicie; informe os checks com falha e a ação necessária.
2. Formule uma pergunta autocontida. Passe arquivos com `--context-file` repetido ou texto pequeno com `--context-text`; não combine os dois modos.
3. Rode exatamente um `rlm-codex start` e capture `run.id` do JSON:

   ```powershell
   rlm-codex start --question "Analise o corpus e responda com evidências" --context-file "dados/parte-1.txt" --context-file "dados/parte-2.json"
   ```

4. Consulte `rlm-codex status <run-id>` e `rlm-codex events <run-id>`. Para observar continuamente, use `rlm-codex events <run-id> --follow`.
5. Obtenha o desfecho com `rlm-codex result <run-id> --wait`. Se expirar, consulte status e eventos da mesma execução; não crie outro run.

Se perder o ID, use `rlm-codex list` para reencontrar a execução. Nunca repita `start` silenciosamente por demora, saída perdida ou resultado ainda pendente.

## Cancelar

Use `rlm-codex cancel <run-id>` somente quando o usuário pedir, um limite acordado for atingido ou status/eventos confirmarem que o run está travado. Use `--force` apenas depois de o cancelamento cooperativo não encerrar o worker no período de graça.

## Entregar

Separe claramente:

- **Resposta do RLM:** campo `result.response`, sem rebatizá-lo como conclusão do Codex.
- **Avaliação do Codex:** sua síntese ou ressalvas, identificadas como avaliação externa.
- **Execução:** `run.id`, estado terminal, trajetória de iterações/subconsultas obtida de eventos/metadados, `usage_summary`, tempo e limites usados.
- **Evidência durável:** tome o caminho do check `state_directory` no `doctor` e acrescente `runs/<run-id>`; `RLM_CODEX_HOME`, quando definido, substitui esse diretório-base. Não exponha tokens, credenciais ou conteúdo privado desnecessário.

Leia [references/protocol.md](references/protocol.md) quando precisar interpretar estados, códigos de saída ou envelopes JSON/JSONL.

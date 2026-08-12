---
name: usar-rlm
description: Use when a task requires analysis of a large corpus, searching many files, recursive decomposition or subqueries, or explicitly asks for RLM; not when a direct local answer is enough.
---

# Usar RLM

## Contrato

Use `rlm-codex` para delegar análise extensa e devolver o resultado à tarefa atual. A execução é `local trusted execution; not sandboxed`: Python gerado executa com as permissões do usuário. Use somente corpus e instruções confiáveis.

Um run é durável. Inicie uma vez, preserve `run.id` e acompanhe essa mesma execução até um estado terminal.

## Decidir

Use para corpus grande, busca em muitos arquivos, decomposição/subconsultas ou pedido explícito por RLM. Trabalhe diretamente quando a resposta estiver num arquivo conhecido ou não exigir decomposição.

## Fluxo normal

1. Antes do primeiro uso na sessão, rode `rlm-codex doctor`. Reutilize esse diagnóstico enquanto instalação e ambiente não mudarem. Se falhar, não inicie um run.
2. Formule uma pergunta autocontida. Use `--context-file` repetido ou `--context-text`, nunca ambos.
3. Rode exatamente um `rlm-codex start` e capture `run.id`:

   ```powershell
   rlm-codex start --question "Analise o corpus e responda com evidências" --context-file "dados/parte-1.txt" --context-file "dados/parte-2.json"
   ```

4. Aguarde o mesmo run com `rlm-codex result <run-id> --wait`.
5. Leia `result.response`, confira afirmações importantes contra as fontes quando possível e use a resposta para continuar a tarefa original.

Não repita `start` por demora, saída perdida ou timeout.

## Recuperar e cancelar

Se a espera expirar ou o comportamento parecer anormal, use `rlm-codex status <run-id>` e `rlm-codex events <run-id>`. Use `rlm-codex events <run-id> --follow` somente quando observação contínua ajudar. Se perder o ID, use `rlm-codex list`.

Use `rlm-codex cancel <run-id>` quando o usuário pedir, um limite acordado for atingido ou a trajetória confirmar travamento. Use `--force` somente após o período de graça.

## Entregar

Separe a resposta do RLM de sua avaliação quando houver diferença relevante e aplique ambas à tarefa original. Ao concluir um run, inclua uma nota curta no formato `RLM <run-id>: <estado>; local trusted execution; not sandboxed`. Acrescente uso somente quando ajudar auditoria ou diagnóstico; não despeje telemetria sem utilidade. Para localizar evidência durável, use o `state_directory` retornado pelo `doctor` e acrescente `runs/<run-id>`.

Para estados, erros, JSON/JSONL e evidência durável, leia [references/protocol.md](references/protocol.md).

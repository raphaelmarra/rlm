# Protocolo de `rlm-codex`

## Contrato de saída

Todos os comandos, exceto `events --follow`, escrevem exatamente um objeto JSON em `stdout`. O campo `schema_version` identifica o formato, `ok` indica sucesso do comando e `command` identifica a operação.

Em erro, leia:

```json
{
  "ok": false,
  "error": {
    "code": "PREFLIGHT_FAILED",
    "message": "3 preflight check(s) failed",
    "retryable": true
  }
}
```

`events --follow` escreve JSONL: um objeto por linha, até o estado terminal ou o timeout.

## Fluxo recomendado

```powershell
rlm-codex doctor
rlm-codex start --question "..." --context-file "arquivo-1" --context-file "arquivo-2"
rlm-codex result <run-id> --wait --wait-timeout 900
```

No caminho normal, vá de `start` para `result --wait`. Consulte `status` e `events`
somente quando a espera expirar, houver demora relevante ou for necessário diagnosticar
a trajetória.

O `start` aceita:

- `--question` obrigatório;
- `--context-file` repetível ou `--context-text`, nunca ambos;
- `--model`, `--max-iterations` e `--max-timeout` como limites explícitos.

Guarde o `run.id` retornado. Cada `start` cria um run novo; acompanhamento e recuperação sempre reutilizam o mesmo ID.

## Estados

| Estado | Significado | Ação normal |
|---|---|---|
| `queued` | Worker ainda não confirmou início | Aguarde e consulte o mesmo run |
| `running` | RLM em execução | Observe status/eventos |
| `cancelling` | Cancelamento cooperativo solicitado | Aguarde estado terminal |
| `succeeded` | Resultado completo disponível | Leia `result.response` |
| `failed` | Worker terminou com erro | Leia o erro sanitizado e eventos |
| `cancelled` | Execução cancelada | Informe eventual `partial_answer` |
| `orphaned` | Worker sumiu ou heartbeat expirou | Preserve evidência; não reinicie sem decisão explícita |

Estados terminais: `succeeded`, `failed`, `cancelled` e `orphaned`.

## Comandos de recuperação e manutenção

```powershell
rlm-codex list
rlm-codex list --status running
rlm-codex cancel <run-id>
rlm-codex cancel <run-id> --force --grace-seconds 30
rlm-codex prune --older-than 7d
```

Use `list` quando a saída inicial tiver sido perdida. `prune` remove apenas runs terminais
antigos. Cancelamento forçado encerra a árvore do worker local após o período de graça.

## Fronteira de confiança

O worker é um processo separado para heartbeat e cancelamento, não uma fronteira de
segurança. O `LocalREPL` usa diretório temporário, mas Python gerado pode ler arquivos,
escrever, importar módulos, acessar a rede e usar as permissões da conta local. Aceite
somente corpus e instruções confiáveis.

## Códigos de saída

| Código | Significado |
|---:|---|
| `0` | Operação concluída |
| `2` | Argumento ou entrada inválida |
| `3` | Preflight do `doctor` falhou |
| `4` | Run não encontrado |
| `5` | Conflito de estado ou timeout de espera |
| `10` | Worker/RLM falhou |

Não interprete código `5` após `result --wait` como autorização para iniciar outro run. Inspecione `status` e `events` do mesmo ID.

## Resultado

Em sucesso, preserve estes campos:

- `response`: resposta produzida pelo RLM;
- `usage_summary`: chamadas e tokens por modelo; `total_cost` pode ser `null` na assinatura ChatGPT;
- `metadata`: iterações, código executado e trajetória registrada pelo núcleo RLM;
- `execution_time` e `root_model`.

Eventos `iteration_started`, `iteration_completed`, `subcall_started` e `subcall_completed` permitem relatar a trajetória sem inventar passos. Mensagens são sanitizadas, mas ainda assim evite reproduzir conteúdo privado que não seja necessário para a resposta.

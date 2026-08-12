# POC KISS do RLM no Codex da sessão atual

**Data:** 2026-08-12  
**Veredito:** aprovada

## Hipótese

O Codex desta sessão consegue invocar `rlm-codex` pelo shell, executar o RLM com
`LocalREPL`, receber uma resposta produzida por `llm_query` e continuar a tarefa sem
Docker, MCP ou processo residual.

## Evidência

| Verificação | Resultado |
|---|---|
| Run | `20260812T150510Z-48daec12` |
| Estado | `succeeded` |
| Resposta | `RLM-CODEX-7391` |
| Ambiente | `local` |
| Chamadas `llm_query` | `1` |
| PID inicial do worker | `16928` |
| Estado final do PID | encerrado; `status.pid` igual a `null` |
| Tempo do RLM | `14.745s` |

O resultado foi usado nesta sessão para decidir que o caminho central funciona e que
o projeto pode avançar para melhorias incrementais.

## Repetição automatizada

`tests/live/test_rlm_codex_cli.py` preserva a mesma prova como smoke opt-in. A execução
com `RLM_LIVE_CODEX=1` terminou com `1 passed in 22.33s`.

## Limite da prova

A POC comprova funcionamento, não isolamento de segurança nem ganho de qualidade sobre
o Codex sem RLM. O corpus deve ser confiável; portabilidade e benchmark continuam como
gates posteriores e independentes.

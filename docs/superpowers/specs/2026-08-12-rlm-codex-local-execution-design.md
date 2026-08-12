# RLM–Codex local, controlado por CLI e skill

**Estado:** Aprovada para implementação<br>
**Data:** 2026-08-12<br>
**Decisão:** ADR 0003<br>
**Substitui:** `docs/superpowers/specs/2026-08-12-codex-subscription-backend-design.md`
e `docs/superpowers/specs/2026-08-12-rlm-tool-for-codex-design.md` como definição
operacional vigente

## Resumo

O fork disponibilizará o Recursive Language Model (RLM) ao Codex por meio da
interface de linha de comando (CLI) global `rlm-codex` e da skill `$usar-rlm`. A
CLI continuará sendo o contrato operacional canônico, com trabalhos duráveis,
JavaScript Object Notation (JSON), JSON Lines, observação, cancelamento e
recuperação. Model Context Protocol (MCP) não fará parte desta versão porque não
reduz o risco nem a complexidade do executor e não demonstrou ganho sobre a CLI
acompanhada pela skill.

Cada trabalho será executado em um worker local, usando o `LocalREPL`. Esse worker
é um processo separado. A mudança remove Windows Subsystem for Linux 2 (WSL 2) e
Docker do caminho crítico, mas também remove o isolamento de
segurança: Python gerado pelo modelo executará com as permissões do usuário que
iniciou a CLI. O usuário aprovou explicitamente esse modo de execução local
confiável em 2026-08-12.

## Objetivos

1. Tornar o RLM utilizável pelo Codex de qualquer diretório com autenticação da
   assinatura ChatGPT, sem `OPENAI_API_KEY`.
2. Preservar a CLI durável já implementada: `doctor`, `start`, `status`, `events`,
   `result`, `cancel`, `list` e `prune`.
3. Usar a skill `$usar-rlm` como mecanismo de descoberta e instrução do agente.
4. Executar cada trabalho em um worker local separado, cancelável e com
   diretório temporário próprio.
5. Remover Docker e WSL 2 dos requisitos, diagnósticos e testes da ferramenta.
6. Provar o fluxo real completo, incluindo iteração raiz, `llm_query`, resultado,
   persistência e cancelamento.
7. Descrever honestamente a fronteira de confiança e evitar qualquer alegação de
   sandbox ou isolamento do host.

## Fora do escopo

- criar um servidor MCP nesta versão;
- expor a ferramenta ao ChatGPT web ou a clientes remotos;
- restringir o Python local como se fosse uma sandbox;
- remover o `DockerREPL` genérico do projeto upstream;
- substituir trabalhos duráveis por um comando síncrono `ask`;
- aceitar API key paga ou autenticação diferente de `chatgpt`;
- prometer que RLM melhora toda tarefa sem benchmark controlado.

## Decisão entre CLI e MCP

### CLI global com skill — escolhida

A CLI já oferece contrato estruturado, funciona fora do checkout, preserva estado
e pode ser combinada com as ferramentas normais do agente. A skill registra quando
usar o RLM, qual comando executar primeiro e como acompanhar o mesmo `run-id`.
Essa combinação é a menor superfície que satisfaz descoberta, execução e
recuperação.

### MCP fino sobre o gerenciador — adiado

Um servidor MCP local ainda precisaria chamar o mesmo `JobManager` e o mesmo
worker. Ele acrescentaria inicialização STDIO, configuração, schemas de ferramentas
e timeouts sem alterar a segurança da execução. MCP só deverá ser reconsiderado se
aparecer pelo menos uma necessidade concreta que a CLI não atenda, como um
consumidor sem shell, distribuição remota ou ganho mensurável de confiabilidade por
argumentos tipados.

### Orquestração sem REPL — rejeitada

Eliminar o Python gerado reduziria o risco, mas mudaria a semântica central do RLM:
o modelo deixaria de explorar programaticamente o contexto. Essa alternativa não
entrega o sistema solicitado.

## Arquitetura

```text
Codex
  |
  +--> skill $usar-rlm
          |
          +--> rlm-codex doctor/start/status/events/result/cancel/list/prune
                    |
                    +--> JobManager + RunStore
                              |
                              +--> worker local
                                        |
                                        +--> RLM(environment="local")
                                                  |
                                                  +--> LocalREPL
                                                  |     +--> Python gerado
                                                  |     +--> llm_query/rlm_query
                                                  |
                                                  +--> CodexClient
                                                        +--> SDK Codex
                                                        +--> conta ChatGPT
```

O worker local é uma fronteira de ciclo de vida: permite heartbeat, cancelamento e
encerramento da árvore de processos. Ele **não** é uma fronteira de segurança. O
`LocalREPL` muda temporariamente para um diretório próprio, mas permite `open`,
`__import__`, acesso à rede e acesso a caminhos disponíveis à conta do usuário.

## Componentes e mudanças

| Componente | Contrato vigente |
|---|---|
| `rlm/clients/codex.py` | Adaptar o SDK ao `BaseLM`, exigir conta `chatgpt`, rejeitar API key e contabilizar uso |
| `rlm/codex_tool/runner.py` | Validar limites e criar `RLM(environment="local")` sem fallback |
| `rlm/codex_tool/worker.py` | Executar um trabalho, emitir heartbeat/eventos e produzir estado terminal em encerramento normal ou cooperativo |
| `rlm/codex_tool/jobs.py` | Criar e encerrar grupos de processos locais, finalizar cancelamento forçado e não conhecer recursos Docker |
| `rlm/codex_tool/store.py` | Preservar requisição, snapshot, estado, eventos, resultado e logs atomicamente |
| `rlm/codex_tool/cli.py` | Manter a superfície e o protocolo existentes; diagnosticar explicitamente a execução local confiável |
| `.agents/skills/usar-rlm/` | Ensinar descoberta, acompanhamento e o limite de confiança do executor |
| `scripts/install_codex_tool.ps1` | Instalar CLI e skill sem verificar ou instalar Docker/WSL |

O `DockerREPL` permanece disponível aos demais usuários do RLM upstream. A mudança
atinge somente o caminho `rlm-codex` e seus exemplos, documentação e testes.

## Fluxo de dados

1. O agente executa `rlm-codex doctor`.
2. `doctor` valida Python, pacote, SDK, ausência de API key, conta ChatGPT,
   diretório de estado e integridade da skill. Um check positivo `execution_mode`
   informa `local trusted execution; not sandboxed`.
3. `start` valida pergunta, limites e contexto antes de criar qualquer processo.
4. Os arquivos de entrada são lidos uma vez e copiados para `context.json`, com
   nomes, tamanhos e hashes em `request.json`.
5. `JobManager` inicia um worker local em novo grupo de processos e devolve o `run-id`.
6. O worker local cria o RLM com `environment="local"`, `max_depth=1`, uma subconsulta
   concorrente no máximo e esforço `medium`.
7. O `LocalREPL` executa os blocos Python no worker e encaminha `llm_query` ao
   `LMHandler`, que usa `CodexClient` e a conta ChatGPT.
8. Callbacks registram iterações e subconsultas em `events.jsonl`; heartbeat e
   estado ficam recuperáveis por outro processo.
9. O resultado terminal é gravado antes de o worker local encerrar. A CLI apenas lê e
   serializa o estado persistido.

O snapshot evita depender de alterações posteriores nos arquivos de entrada. Ele
não impede o Python gerado de acessar outros arquivos do host.

## Superfície da CLI

A superfície atual será preservada, sem introduzir `ask`:

- `doctor`: preflight sem inferência;
- `start`: inicia exatamente um trabalho e retorna seu identificador;
- `status`: consulta o snapshot atual;
- `events [--follow]`: lê a trajetória em JSON Lines;
- `result [--wait]`: recupera o desfecho;
- `cancel [--force]`: solicita cancelamento e, se autorizado, encerra a árvore;
- `list`: reencontra trabalhos;
- `prune`: remove somente trabalhos terminais antigos.

Os limites atuais permanecem: contexto entre 1 byte e 50 MiB, no máximo 200
arquivos, `max_iterations` de 1 a 20 e `max_timeout` de 30 a 3600 segundos. Todo
comando, exceto `events --follow`, escreve exatamente um objeto JSON em `stdout`.

## Fronteira de confiança

O sistema fará as seguintes afirmações e nenhuma mais forte:

- o backend Codex produz texto em thread efêmera, diretório vazio, sandbox
  somente leitura e sem aprovações;
- o Python do RLM executa no worker local e em diretório temporário;
- cancelamento forçado encerra a árvore do worker;
- os arquivos de contexto são copiados, não montados nem lidos continuamente;
- o `LocalREPL` não restringe leitura, escrita, imports, rede ou variáveis de
  ambiente disponíveis ao usuário.

Por isso a skill deverá usar o RLM apenas com corpus e instruções confiáveis, avisar
que o modo não é sandboxed e nunca descrever o sistema como isolado. Uma entrada
hostil ou contaminada por prompt injection deve ser tratada como capaz de induzir
ações com as permissões do usuário.

## Erros e cancelamento

- `OPENAI_API_KEY` não vazia causa falha antes de criar o worker ou inferir.
- Falha de autenticação, contexto ou limites não possui fallback.
- Exceções do RLM são sanitizadas, persistidas em `result.json` e levam a
  `failed`.
- Um worker local morto após expiração do heartbeat leva a `orphaned`.
- Cancelamento cooperativo usa o grupo de processos. `--force` encerra a árvore
  após o período de graça, sem executar limpeza Docker.
- `prune` continua proibido para estados ativos.
- Logs não podem ser misturados ao JSON de `stdout` nem conter credenciais.

## Estratégia de testes

### Determinísticos

- `runner` constrói exclusivamente `environment="local"`;
- `doctor` não procura Docker/WSL e expõe o modo de execução;
- `jobs` cancela e encerra árvores locais sem limpador Docker;
- protocolo, store, worker, CLI e skill preservam seus contratos;
- `LocalREPL`, `llm_query`, callbacks e limites permanecem cobertos;
- exemplos e documentação não apresentam Docker como requisito da ferramenta;
- ausência de referências vigentes ao plano/ADRs Docker é verificada.

### Reais opt-in

1. `CodexClient` retorna `RLM_CODEX_OK` usando a assinatura ChatGPT.
2. Um RLM local usa uma fixture sintética, executa Python e comprova ao menos uma
   subconsulta `llm_query` na trajetória.
3. A CLI prova `start`, `status`, `events`, `result`, `list`, `cancel` e `prune`,
   sem processo residual.
4. Um processo novo do Codex, iniciado fora do checkout, usa `$usar-rlm`, preserva
   um único `run-id` e recupera a resposta correta.
5. O diretório de teste é comparado antes e depois para detectar escrita não
   esperada; isso é uma prova do caso testado, não uma garantia de sandbox.

Testes reais exigem `RLM_LIVE_CODEX=1` e ausência de `OPENAI_API_KEY`. Não haverá
mais `RLM_LIVE_DOCKER`.

## Avaliação incremental da skill

Depois do ponta a ponta verde, uma comparação neutra `1 x 1` mede apenas o valor da
skill: baseline e candidato recebem o mesmo modelo, ferramentas, fixture, limites e
CLI; somente o candidato recebe `$usar-rlm`. Saídas são preservadas e avaliadas de
forma cega por diagnóstico, início único, monitoramento, resposta, uso e relato da
trajetória. Uma dupla produz evidência não replicada e não autoriza alegação ampla
de ganho de qualidade.

## Critérios de aceite

O sistema estará concluído somente quando evidência recente provar todos os itens:

1. `rlm-codex` resolve pelo `PATH` fora do checkout.
2. `doctor` retorna `ok=true`, conta `chatgpt`, skill sincronizada e execução local
   confiável explícito, sem qualquer requisito Docker/WSL.
3. `OPENAI_API_KEY` presente bloqueia `doctor` e `start` antes de inferência.
4. Ruff, formatação, pre-commit, `ty` e todos os testes determinísticos passam.
5. O smoke direto do `CodexClient` passa pela assinatura ChatGPT.
6. O smoke RLM local executa Python e comprova iteração raiz e `llm_query` real.
7. A CLI real comprova início, observação, resultado, listagem, cancelamento e
   limpeza sem processo residual.
8. Um Codex novo fora do checkout ativa `$usar-rlm` e obtém sozinho a resposta
   correta sem duplicar o trabalho.
9. O benchmark `1 x 1` separa funcionamento da CLI do ganho incremental da skill.
10. Fixture, logs, resultados e diff não contêm segredo, token ou e-mail privado.
11. Nenhum arquivo do projeto usado no smoke é alterado; o relatório reconhece que
    essa evidência não equivale a isolamento.
12. Código, skill, documentação, decisão, plano e evidências estão versionados e
    coerentes entre si.

## Garantia honesta

“Funcional” significa que um agente novo descobre a skill, opera a CLI durável e
recebe uma resposta RLM real usando a assinatura ChatGPT, com testes e trajetória
auditáveis. Não significa que Python gerado seja seguro contra entradas hostis nem
que RLM produza respostas melhores em toda tarefa.

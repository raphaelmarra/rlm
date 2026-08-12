# Recursive Language Models (RLM) como ferramenta controlada pelo Codex

**Estado:** Aprovada para implementação<br>
**Data:** 2026-08-12<br>
**Repositório:** `raphaelmarra/rlm`<br>
**Branch:** `feat/codex-subscription-backend`

## Resumo

O fork entregará o RLM como uma ferramenta local que o Codex consegue descobrir,
iniciar, acompanhar, cancelar e consultar a partir de qualquer diretório. A
superfície primária será a interface de linha de comando (CLI) `rlm-codex`, com
respostas estruturadas, acompanhada pela skill global `$usar-rlm`. A CLI controlará
trabalhos duráveis; cada trabalho
executará o RLM real com o backend Codex por assinatura e com o Python gerado
isolado no `DockerREPL`.

Esta spec define a camada de controle. O contrato do backend de linguagem continua
em `docs/superpowers/specs/2026-08-12-codex-subscription-backend-design.md`.

## Problema que esta camada resolve

O backend `codex` sozinho permite que o RLM consulte a conta ChatGPT, mas não torna
o RLM uma ferramenta operacional do Codex. Sem uma camada adicional, um agente
precisaria conhecer o caminho do fork, construir código Python ad hoc, permanecer
preso ao processo e interpretar saída humana. Também não teria contrato para
inspecionar progresso, recuperar um resultado anterior ou cancelar uma execução.

O estado upstream confirma:

- não existe entrada `[project.scripts]` nem CLI do RLM;
- o `RLM` já expõe resposta, uso e trajetória;
- o `RLMLogger` captura metadados e iterações;
- o `DockerREPL` já isola o Python em container;
- callbacks de subconsulta existem, mas os callbacks de iteração ainda não são
  disparados;
- Docker Desktop e Windows Subsystem for Linux 2 (WSL 2) ainda não estão
  instalados nesta máquina.

## Objetivos

1. Disponibilizar o comando `rlm-codex` no caminho de comandos (`PATH`),
   independentemente do diretório.
2. Oferecer comandos estáveis para diagnóstico, início, observação, resultado,
   cancelamento, listagem e limpeza de trabalhos.
3. Usar JavaScript Object Notation (JSON) como contrato padrão e JSON Lines para
   fluxo de eventos.
4. Persistir estado fora dos repositórios analisados.
5. Usar somente a autenticação ChatGPT do Codex, sem API key (chave de API) paga.
6. Executar código gerado apenas no Docker.
7. Instalar uma skill que ensine o Codex a operar a CLI e escolher quando o RLM
   vale o consumo adicional.
8. Provar, com um processo novo do Codex, que a ferramenta é descoberta e usada
   até um resultado correto.
9. Preservar a MUTATIO e qualquer projeto analisado contra escrita involuntária.

## Fora do escopo

- Expor o RLM ao ChatGPT web por servidor remoto.
- Tornar Model Context Protocol (MCP) o transporte inicial.
- Oferecer interface gráfica.
- Suportar Claude nesta etapa.
- Usar API OpenAI, OpenRouter ou outro gateway cobrado por token.
- Executar o `LocalREPL` como fallback quando Docker estiver indisponível.
- Manter workers ou containers depois de um estado terminal.
- Prometer ganho de qualidade sem benchmark controlado.

## Abordagens consideradas

### CLI global com skill companheira — escolhida

A documentação oficial do Codex recomenda uma CLI componível, disponível de
qualquer pasta, com saída previsível e uma skill que preserve o fluxo. Essa opção
é verificável no ambiente atual, funciona no Codex CLI e no aplicativo e não exige
um servidor residente.

### MCP como primeira superfície — adiada

MCP daria ferramentas nativas ao modelo, mas exigiria servidor, configuração e
reinicialização antes de provar o núcleo. Um MCP futuro poderá delegar para o mesmo
gerenciador de trabalhos sem alterar o protocolo local.

### Skill chamando `uv run` no fork — rejeitada

Seria simples, porém presa a um caminho, sem contrato de estado, sem cancelamento e
sem garantia de funcionar fora do repositório.

## Arquitetura

O backend usa o kit de desenvolvimento do Codex (SDK). A camada de ferramenta não
fala diretamente com o SDK; ela sempre passa pelo `CodexClient`.

```text
Codex
  |
  +--> skill $usar-rlm
          |
          +--> rlm-codex doctor/start/status/events/result/cancel/list/prune
                    |
                    +--> armazenamento de trabalhos no perfil do usuário
                    |
                    +--> worker Python isolado do processo chamador
                              |
                              +--> RLM
                                      |
                                      +--> CodexClient --> SDK --> conta ChatGPT
                                      |
                                      +--> DockerREPL --> Python gerado
```

Os módulos terão responsabilidades separadas:

| Módulo | Responsabilidade |
|---|---|
| `rlm/clients/codex.py` | adaptar SDK Codex ao contrato `BaseLM` |
| `rlm/codex_tool/protocol.py` | estados, envelopes JSON, erros e serialização |
| `rlm/codex_tool/paths.py` | localizar o diretório global e cada trabalho |
| `rlm/codex_tool/store.py` | gravação atômica de requisição, estado, eventos e resultado |
| `rlm/codex_tool/runner.py` | validar entrada e construir a instância segura do `RLM` |
| `rlm/codex_tool/worker.py` | executar um trabalho e traduzir callbacks em eventos |
| `rlm/codex_tool/jobs.py` | iniciar, observar, cancelar e limpar processos |
| `rlm/codex_tool/cli.py` | analisar argumentos, chamar serviços e imprimir o protocolo |
| `.agents/skills/usar-rlm/SKILL.md` | ensinar o fluxo ao Codex |
| `scripts/install_codex_tool.ps1` | instalar CLI e skill no perfil do usuário |

## Superfície da CLI

### `rlm-codex doctor`

Verifica, sem inferência:

- versão do pacote e do Python;
- presença do extra `codex`;
- ausência de `OPENAI_API_KEY` não vazia;
- conta reportada pelo SDK como `chatgpt`;
- comando e daemon Docker;
- imagem configurada;
- diretório de estado gravável;
- skill global instalada e sincronizada com a origem.

O comando termina com código zero somente quando uma execução real pode começar.

### `rlm-codex start`

Inicia um worker em segundo plano e retorna o identificador do trabalho. Contrato:

```text
rlm-codex start \
  --question "pergunta" \
  --context-file caminho-a.txt \
  --context-file caminho-b.json \
  [--model gpt-5.6-terra] \
  [--max-iterations 6] \
  [--max-timeout 600]
```

`--question` é obrigatório. Um ou mais `--context-file` preservam nome e conteúdo
em um dicionário. `--context-text` aceita uma entrada curta inline. Exatamente uma
das duas formas de contexto deve ser usada. `start` lê e valida a entrada antes de
criar o worker, grava um snapshot protegido no diretório do trabalho e nunca monta
os arquivos originais dentro do container.

O comando rejeita limites fora das faixas:

| Limite | Mínimo | Padrão | Máximo |
|---|---:|---:|---:|
| `max_iterations` | `1` | `6` | `20` |
| `max_timeout` | `30 s` | `600 s` | `3600 s` |
| tamanho total do contexto | `1 byte` | — | `50 MiB` |
| quantidade de arquivos | `1` | — | `200` |

O primeiro release fixa `max_depth=1`, `max_concurrent_subcalls=1`, ambiente
`docker` e esforço `medium`.

### Observação e resultado

- `rlm-codex status <run-id>` lê o snapshot atual, incluindo o identificador do
  processo (PID) quando houver worker ativo.
- `rlm-codex events <run-id> [--follow] [--wait-timeout 900]` imprime JSON Lines
  em ordem e encerra ao chegar a um estado terminal ou ao timeout.
- `rlm-codex result <run-id> [--wait] [--wait-timeout 900]` devolve o resultado
  terminal; sem `--wait`, um trabalho ativo causa conflito `5`.
- `rlm-codex list [--status STATUS]` lista trabalhos do mais recente ao mais
  antigo.

### Cancelamento e limpeza

- `rlm-codex cancel <run-id>` grava a intenção de cancelamento e sinaliza o worker.
- O worker converte o sinal em cancelamento do RLM e executa os blocos `finally`.
- Se o período de graça padrão de `30 s` terminar, `--force` encerra a árvore do
  processo e remove containers e redes com o rótulo do trabalho.
- `rlm-codex prune --older-than 7d` remove somente trabalhos terminais antigos.
- Um trabalho ativo nunca é removido por `prune`.

## Protocolo de saída

Todo comando, exceto `events --follow`, imprime exatamente um objeto JSON em
`stdout`. Logs diagnósticos vão para arquivos do trabalho; `stderr` é reservado a
falha do próprio processo da CLI.

```json
{
  "schema_version": "1",
  "ok": true,
  "command": "status",
  "run": {
    "id": "20260812T120000Z-a1b2c3d4",
    "status": "running",
    "created_at": "2026-08-12T12:00:00Z",
    "updated_at": "2026-08-12T12:00:05Z",
    "pid": 1234,
    "progress": {"iteration": 2, "subcalls_completed": 1}
  }
}
```

Falhas usam:

```json
{
  "schema_version": "1",
  "ok": false,
  "command": "result",
  "error": {
    "code": "RUN_NOT_FOUND",
    "message": "Run 'x' was not found",
    "retryable": false
  }
}
```

Códigos de saída:

| Código | Significado |
|---:|---|
| `0` | comando concluído |
| `2` | argumentos ou contexto inválidos |
| `3` | preflight indisponível |
| `4` | trabalho inexistente |
| `5` | conflito com o estado atual |
| `10` | worker terminou com falha |

## Máquina de estados do trabalho

Estados permitidos:

```text
queued -> running -> succeeded
                  -> failed
                  -> cancelling -> cancelled
queued -------------------------> cancelled
queued/running -----------------> orphaned
```

Estados terminais são `succeeded`, `failed`, `cancelled` e `orphaned`. Toda mudança
atualiza `updated_at` e acrescenta um evento. `status` marca como `orphaned` um
trabalho não terminal cujo PID não existe e cuja pulsação expirou. O worker
atualiza a pulsação a cada `2 s`; `15 s` sem pulsação caracteriza expiração.

## Persistência

O diretório padrão é:

- Windows: `%LOCALAPPDATA%/rlm-codex`;
- Linux/macOS: `$XDG_STATE_HOME/rlm-codex` ou `~/.local/state/rlm-codex`.

`RLM_CODEX_HOME` pode substituir o local em testes. Cada trabalho contém:

```text
runs/<run-id>/
  request.json
  context.json
  state.json
  events.jsonl
  result.json
  worker.stdout.log
  worker.stderr.log
  cancel.requested
```

Snapshots são gravados em temporário adjacente, descarregados e renomeados
atomicamente. `request.json` registra caminhos e hashes; `context.json` preserva o
conteúdo exato necessário ao worker. Ambos herdam permissões restritas ao usuário,
nunca são montados no container e são removidos por `prune` com o restante do
trabalho.

## Backend Codex por assinatura

`CodexClient` seguirá `BaseLM` e implementará `completion`, `acompletion`,
`get_usage_summary` e `get_last_usage`. Cada chamada:

1. rejeita `OPENAI_API_KEY` não vazia;
2. abre o SDK em contexto curto;
3. exige `Codex.account().account.root.type == "chatgpt"`;
4. cria thread efêmera em diretório temporário vazio;
5. usa `Sandbox.read_only` e `ApprovalMode.deny_all`;
6. instrui o Codex a devolver somente a próxima mensagem do RLM e não executar os
   blocos Python;
7. retorna `TurnResult.final_response` e contabiliza `usage.last`;
8. remove o temporário e fecha o app-server em sucesso ou erro.

O adaptador aceita string ou histórico de mensagens. Mensagens `system` e
`developer` viram instruções; `user` e `assistant` são serializadas em ordem. Conteúdo
não textual, resposta vazia, conta diferente de ChatGPT e timeout causam erro
explícito, sem fallback.

## Isolamento Docker

O worker sempre cria `RLM(environment="docker")`. O container:

- não monta o repositório nem os arquivos de contexto;
- monta somente seu temporário de trabalho;
- recebe rótulo `io.rlm-codex.run-id=<run-id>`;
- conecta-se a uma rede bridge interna e descartável, capaz de alcançar somente o
  proxy do host, sem rota de saída para a internet;
- usa usuário sem privilégios quando a imagem permitir;
- remove capabilities desnecessárias e impede novos privilégios;
- recebe limites de memória, processador (CPU) e processos;
- é removido, junto com a rede interna, no encerramento normal e no cancelamento
  forçado.

Ausência de Docker causa preflight `3`; nunca seleciona `local` ou `ipython`.

## Skill `$usar-rlm`

A skill dispara quando o usuário pede análise de corpus grande, busca estruturada
em muitos arquivos, decomposição com subconsultas ou uso explícito do RLM. Ela não
dispara para perguntas simples que o Codex resolve diretamente.

Fluxo obrigatório:

1. executar `rlm-codex doctor`;
2. explicar qualquer preflight bloqueado;
3. construir uma pergunta específica e uma lista mínima de arquivos;
4. executar `start` e guardar o `run-id`;
5. acompanhar `status` e `events`, sem iniciar duplicata silenciosa;
6. usar `result --wait` e distinguir resposta do RLM de avaliação do Codex;
7. informar trajetória, uso, limites atingidos e caminho do trabalho;
8. cancelar apenas quando solicitado, quando um limite operacional for violado ou
   quando a execução estiver comprovadamente presa.

A fonte versionada vive em `.agents/skills/usar-rlm`. O instalador copia essa pasta
para `~/.codex/skills/usar-rlm` e registra o commit de origem. `doctor` detecta drift.

## Instalação nesta máquina

O instalador do fork executará, de forma repetível:

1. sincronização `uv` do repositório;
2. `uv tool install --editable` com o extra `codex`;
3. instalação da skill global;
4. verificação do comando a partir de diretório externo;
5. diagnóstico da conta ChatGPT;
6. diagnóstico de WSL 2 e Docker.

Nesta máquina, WSL 2 e Docker Desktop serão instalados pelos distribuidores
oficiais disponíveis no Windows. Reinicialização ou aceite interativo são tratados
como gate operacional visível, não como sucesso presumido.

## Testes

### Determinísticos

- cliente Codex com SDK falso: autenticação, serialização, uso, timeout e limpeza;
- protocolo: envelopes, estados, transições e códigos de saída;
- store: escrita atômica, corrupção e concorrência;
- jobs: start, heartbeat, resultado, órfão, cancelamento e prune com worker falso;
- CLI em subprocesso com `RLM_CODEX_HOME` temporário;
- skill: frontmatter, gatilhos, comandos existentes e ausência de caminhos absolutos;
- DockerREPL: rótulo e opções de isolamento com `subprocess.run` falso.

### Reais opt-in

1. `CodexClient` faz uma chamada mínima e recebe `RLM_CODEX_OK`.
2. RLM usa Docker e fixture sintética que exige `llm_query`.
3. CLI inicia o RLM, observa eventos e recupera resposta correta.
4. Um processo novo do Codex, fora do fork, ativa `$usar-rlm` e opera a CLI.

Os testes reais exigem `RLM_LIVE_CODEX=1`; os que usam Docker também exigem
`RLM_LIVE_DOCKER=1`. Nenhum teste real aceita `OPENAI_API_KEY` no ambiente.

## Avaliação incremental da skill

Depois da CLI funcionar, será executado um teste `1 x 1`:

- tarefa neutra e fixture idênticas;
- mesmo modelo, ferramentas, tempo e CLI disponível;
- baseline sem a skill testada;
- candidato com somente `$usar-rlm` adicionada;
- saídas preservadas e avaliadas anonimamente por critérios congelados.

Critérios: diagnóstico correto, início único, monitoramento, resultado correto,
ausência de API key e relato de trajetória. O ganho é material apenas se a skill
fechar um critério crítico que o baseline não fecha ou mudar o veredito operacional.
Uma única dupla produz evidência `não replicada`.

## Critérios de aceite

O objetivo só estará completo quando houver evidência recente para todos os itens:

1. `rlm-codex` resolve pelo `PATH` em diretório fora do fork.
2. `doctor` retorna `ok=true`, conta `chatgpt`, Docker disponível e skill sincronizada.
3. `OPENAI_API_KEY` presente faz `doctor` e `start` falharem antes de inferência.
4. Unitários, Ruff, formatação, ty e pre-commit passam.
5. O smoke direto do `CodexClient` passa por assinatura.
6. O smoke RLM executa Python em Docker e comprova uma subconsulta `llm_query`.
7. A CLI comprova `start`, `status`, `events`, `result`, `list` e `prune`.
8. Cancelamento cooperativo chega a `cancelled` e não deixa worker nem container.
9. Um Codex novo ativa `$usar-rlm` e recupera sozinho o resultado correto.
10. O relatório `1 x 1` separa funcionamento da CLI do ganho incremental da skill.
11. Nenhum arquivo da MUTATIO ou do projeto analisado é alterado.
12. O diff, os logs e os resultados não contêm segredo, token ou e-mail.
13. A branch remota contém código, skill, docs e evidências reproduzíveis.

## Garantia honesta

“Controlado e gerenciado pelo Codex” significa que o Codex possui uma interface
instalada para criar, observar, cancelar e consultar trabalhos RLM, e que um teste
externo ao repositório prova o fluxo completo. Não significa que toda tarefa melhora
com RLM. A decisão de qualidade depende do benchmark separado; o funcionamento da
ferramenta depende dos treze critérios de aceite.

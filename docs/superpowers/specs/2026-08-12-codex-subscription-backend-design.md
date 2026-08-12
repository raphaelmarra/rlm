# Backend Codex por assinatura para Recursive Language Models (RLM)

**Estado:** Substituída por `docs/superpowers/specs/2026-08-12-rlm-codex-local-execution-design.md`<br>
**Data:** 2026-08-12<br>
**Repositório:** `raphaelmarra/rlm`<br>
**Branch de trabalho:** `feat/codex-subscription-backend`

## Resumo

Este projeto adicionará ao RLM um backend chamado `codex` que usa o kit oficial
de desenvolvimento do Codex (SDK) e a autenticação da conta ChatGPT já
conectada. O backend não aceitará nem utilizará uma API key (chave da API
OpenAI). A integração será opcional, isolada do núcleo existente e comprovada
por testes unitários determinísticos e por um teste rápido real do backend
(`smoke direto`), explicitamente habilitado pelo operador.

O resultado esperado é permitir esta configuração:

```python
from rlm import RLM

rlm = RLM(
    backend="codex",
    backend_kwargs={"model_name": "gpt-5.6-terra"},
    environment="docker",
    max_depth=1,
    max_iterations=6,
    max_concurrent_subcalls=1,
)
```

O trecho só será considerado suportado quando os critérios de aceite deste
documento estiverem verdes. A existência do código não substitui os critérios
de aceite.

## Problema atual

O RLM `0.1.3` conhece backends de API e modelos locais, mas não conhece o Codex
como backend. Selecionar `backend="openai"` usa a API OpenAI e sua cobrança por
consumo; o backend OpenAI não reutiliza automaticamente uma assinatura ChatGPT.

O RLM cria o cliente pelo registro interno `rlm/clients/__init__.py`. Todas as
iterações raiz e subconsultas passam pela interface `BaseLM`, que exige quatro
operações: resposta síncrona, resposta assíncrona, uso acumulado e uso da última
chamada. Portanto, apenas instalar a interface de linha de comando do Codex
(CLI) ou iniciá-lo como Model Context Protocol (MCP) não resolve a integração.

Há ainda dois riscos operacionais:

1. o Codex é um agente, enquanto o RLM espera que o backend devolva o próximo
   texto do modelo sem modificar o projeto;
2. o ambiente `local` do RLM executa Python produzido pelo modelo no processo
   hospedeiro. Esse executor Python é chamado de REPL no projeto.

A integração precisa limitar o Codex à produção de texto e isolar a execução do
Python gerado.

## Evidências verificadas no ambiente

| Evidência | Resultado em 2026-08-12 |
|---|---|
| RLM upstream | `0.1.3`, commit `caf0bff` |
| Python solicitado pelo repositório | `3.11` |
| Python instalado no ambiente do fork | `3.11.15` |
| Codex CLI local | `0.147.0` |
| Autenticação do CLI | ChatGPT |
| SDK Python instalado | `openai-codex 0.144.4` |
| Autenticação vista pelo SDK | `chatgpt`, plano `pro` |
| Testes upstream antes da mudança | `271 passed`, `63 skipped` |
| Docker | indisponível nesta máquina |

A indisponibilidade do Docker impede o smoke ponta a ponta (E2E) do RLM até
Docker Desktop ou um motor Docker compatível ser instalado e iniciado. Não
haverá fallback silencioso para execução local.

## Objetivos

1. Adicionar `codex` como backend opcional e compatível com `BaseLM`.
2. Usar exclusivamente autenticação `chatgpt` no modo assinatura.
3. Preservar mensagens e instruções do RLM ao convertê-las para uma entrada do
   Codex.
4. Impedir escrita do Codex no repositório durante uma chamada de modelo.
5. Executar o REPL do RLM em Docker no smoke E2E.
6. Medir chamadas e tokens sem inventar custo monetário por chamada.
7. Manter os testes normais independentes de conta, rede e franquia.
8. Produzir evidência auditável de que raiz, REPL e subconsulta foram usados.

## Fora do escopo

- Usar a API OpenAI, OpenRouter ou qualquer gateway cobrado por token.
- Implementar suporte ao Claude.
- Transformar o RLM em MCP ou usar MCP como transporte do modelo.
- Processar o corpus do MUTATIO ou alterar o repositório MUTATIO.
- Prometer resposta determinística de um modelo probabilístico.
- Publicar pacote no PyPI ou abrir PR upstream nesta etapa.
- Executar código gerado no host como alternativa à ausência de Docker.

## Decisão de arquitetura

Será usado o SDK Python oficial `openai-codex`, instalado pelo extra opcional
`rlms[codex]`. Cada chamada de `BaseLM.completion()` abrirá uma instância curta do
app-server e uma thread Codex efêmera. Uma instância curta por chamada sacrifica
alguma latência para evitar processo órfão, estado oculto entre iterações e
mudanças amplas no ciclo de vida dos clientes existentes.

Não serão usados:

- `codex exec` como subprocesso: exigiria parsing de processo e duplicaria o
  protocolo que o SDK já fornece;
- um proxy compatível com OpenAI: acrescentaria servidor, porta e protocolo sem
  benefício para a prova inicial;
- `codex mcp-server`: o RLM precisa de um backend `BaseLM`, não de uma ferramenta
  MCP.

A decisão e seus trade-offs estão registrados em
`docs/decisions/0001-sdk-codex-como-backend-de-assinatura.md`.

## Arquitetura esperada

```text
Aplicação
   |
   v
RLM.completion()
   |
   +--> CodexClient(BaseLM)
   |       |
   |       +--> preflight de autenticação
   |       +--> serialização das mensagens
   |       +--> openai-codex / app-server
   |       +--> conta ChatGPT
   |
   +--> DockerREPL
           |
           +--> executa somente o Python emitido pelo RLM
           +--> llm_query() retorna ao LMHandler
                           |
                           +--> CodexClient(BaseLM)
```

Existem duas fronteiras distintas de segurança:

- **Codex:** diretório temporário vazio, thread efêmera, sandbox somente leitura
  e toda solicitação de elevação negada;
- **REPL RLM:** container Docker descartável, sem montagem do repositório e com
  apenas o canal já previsto pelo RLM para subconsultas.

## Componentes

### `CodexClient`

Viverá em `rlm/clients/codex.py`, herdará de `BaseLM` e seguirá o padrão dos
clientes existentes.

Responsabilidades:

- validar dependência opcional e autenticação;
- aceitar texto ou histórico de mensagens;
- abrir e fechar uma chamada Codex sem deixar processos persistentes;
- devolver apenas `TurnResult.final_response` ao RLM;
- acumular quantidade de chamadas e tokens;
- expor os resumos de uso esperados pelo núcleo.

O construtor aceitará:

| Parâmetro | Tipo | Padrão | Finalidade |
|---|---|---|---|
| `model_name` | `str` | obrigatório | Modelo enviado ao Codex |
| `timeout` | `float` | padrão de `BaseLM` | Limite da chamada |
| `reasoning_effort` | `str` | `medium` | Esforço configurável |
| `service_tier` | `str \| None` | `None` | Tier da assinatura, quando suportado |
| `require_chatgpt_auth` | `bool` | `True` | Impede uso acidental de API key |

Não serão expostos `api_key`, `base_url` nem um modo de fallback.

### Registro do backend

`rlm/clients/__init__.py` receberá o caso `backend == "codex"`. O literal
`ClientBackend` em `rlm/core/types.py` e a documentação de backends serão
atualizados no mesmo conjunto de mudanças.

A importação de `openai_codex` ocorrerá apenas quando o backend for selecionado.
Usuários que não instalarem `rlms[codex]` não receberão a dependência binária do
Codex.

### Conversão de mensagens

O RLM envia o histórico completo a cada iteração. Para evitar uma segunda
memória de conversa, cada chamada usará uma thread Codex nova e efêmera.

A conversão obedecerá às seguintes regras:

1. texto simples vira a entrada única da thread;
2. mensagens `system` e `developer` formam as instruções-base da thread;
3. mensagens `user` e `assistant` são serializadas em ordem, com papel e
   conteúdo inequívocos;
4. o adaptador acrescenta uma instrução fixa: produzir somente a próxima
   mensagem do modelo e não executar os blocos Python emitidos para o RLM;
5. conteúdo desconhecido ou não textual causa erro explícito.

Não haverá truncamento silencioso nem resumo automático no adaptador. Limites de
contexto permanecem responsabilidade do RLM e do Codex.

### Execução Codex

Cada chamada usará:

- `ephemeral=True`;
- `cwd` apontando para um diretório temporário vazio;
- `Sandbox.read_only`;
- `ApprovalMode.deny_all`;
- instruções-base específicas para o papel de backend RLM;
- fechamento do SDK em bloco de contexto, inclusive em erro.

O diretório temporário será removido ao final. Nenhuma chamada receberá o caminho
do projeto como diretório de trabalho.

### Autenticação fail-closed

Antes da primeira inferência, o cliente deverá:

1. rejeitar `OPENAI_API_KEY` não vazio no ambiente do processo quando
   `require_chatgpt_auth=True`;
2. consultar `Codex.account()`;
3. desembrulhar `GetAccountResponse.account.root`;
4. aceitar somente `type == "chatgpt"`;
5. nunca registrar e-mail, token ou identificador da conta.

Conta ausente, `apiKey`, provedor externo ou resposta desconhecida interrompem a
execução antes de enviar o prompt.

### Uso e custo

`TurnResult.usage.last` fornece tokens de entrada e saída. O cliente os acumulará
em `ModelUsageSummary` com:

- `total_calls`: chamadas concluídas;
- `total_input_tokens`: soma dos tokens de entrada;
- `total_output_tokens`: soma dos tokens de saída;
- `total_cost`: `None`.

`None` significa que não existe custo monetário por chamada informado pelo modo
assinatura; não significa uso ilimitado. A franquia da conta continua sendo
consumida.

## Fluxo de uma execução

1. A aplicação cria `RLM(backend="codex", ...)`.
2. O RLM cria `CodexClient` pelo registro de backends.
3. A primeira chamada valida dependência, variáveis de ambiente e tipo da conta.
4. O cliente converte o histórico do RLM em instruções e entrada Codex.
5. O SDK abre app-server e thread efêmera no diretório temporário.
6. O Codex devolve um texto contendo análise ou bloco `repl` para o RLM.
7. O RLM executa o bloco no DockerREPL.
8. Se o bloco chama `llm_query`, o `LMHandler` retorna ao mesmo backend Codex.
9. O RLM continua até `answer["ready"] = True` ou atingir um limite.
10. A resposta, a trajetória e o resumo de uso são devolvidos à aplicação.

## Erros esperados

| Condição | Comportamento |
|---|---|
| Extra `codex` ausente | erro com comando de instalação |
| `OPENAI_API_KEY` presente | abortar antes da inferência |
| Conta não autenticada | abortar e orientar `codex login` |
| Tipo de conta diferente de `chatgpt` | abortar sem fallback |
| Resposta final vazia | erro explícito, sem aceitar string vazia |
| Limite da assinatura atingido | propagar erro de uso com mensagem acionável |
| Timeout | encerrar app-server e propagar timeout |
| Falha ao remover temporário | erro de limpeza registrado sem expor conteúdo |
| Docker indisponível no smoke E2E | teste marcado como não executável; nunca usar host |

## Estratégia de testes

### Testes normais

`tests/clients/test_codex.py` usará um executor falso injetado no cliente. Não
abrirá rede, Codex nem conta. Cobrirá:

- texto e histórico de mensagens;
- preservação da ordem e dos papéis;
- autenticação ChatGPT aceita;
- API key e outros tipos de conta rejeitados;
- resposta vazia;
- contabilização da última chamada e do acumulado;
- limpeza após sucesso, erro e cancelamento;
- `completion()` e `acompletion()`.

Os testes do registro confirmarão que `get_client("codex", ...)` cria o tipo
correto somente quando o extra está disponível.

### Smoke direto do backend

Um teste opt-in executará uma única chamada de `CodexClient` com um caso
sintético curto (fixture) e exigirá o marcador `RLM_CODEX_OK`. O smoke direto
provará SDK, autenticação, modelo e retorno, mas ainda não provará a recursão.

### Smoke E2E do RLM

O smoke E2E opt-in usará Docker e uma fixture sintética. O prompt exigirá uma
subconsulta e terá resultado verificável. O teste aceitará a execução apenas se
a trajetória demonstrar:

- ao menos uma iteração raiz;
- ao menos uma chamada por `llm_query`;
- resposta final correta;
- `root_model` correspondente ao Codex configurado;
- uso com uma ou mais chamadas e `total_cost is None`;
- ausência de escrita no repositório.

Os smokes reais só rodam com `RLM_LIVE_CODEX=1`. O smoke E2E também requer
`RLM_LIVE_DOCKER=1`. A suíte padrão sempre usa fakes.

## Limites operacionais iniciais

| Limite | Valor inicial |
|---|---:|
| `max_depth` | `1` |
| `max_iterations` | `6` |
| `max_concurrent_subcalls` | `1` |
| timeout por chamada Codex | `180 s` |
| timeout total do smoke E2E | `600 s` |
| contexto dos smokes | somente fixture sintética |

Esses valores pertencem à prova inicial. Aumentá-los exige benchmark que mostre
ganho sem consumo descontrolado da assinatura.

## Critérios de aceite

O backend será considerado executável pelo Codex somente quando todos os itens
abaixo tiverem evidência recente:

1. `uv sync --extra codex --group dev --group test` conclui sem erro.
2. A suíte upstream e os novos testes unitários passam.
3. Ruff e pre-commit passam sem mudanças automáticas pendentes.
4. O SDK reporta autenticação `chatgpt` antes da chamada.
5. O smoke direto retorna `RLM_CODEX_OK` sem API key no processo.
6. Docker está disponível e o smoke E2E termina corretamente.
7. A trajetória prova iteração raiz e subconsulta reais.
8. Nenhum arquivo do repositório é criado ou alterado pela chamada; apenas o
   temporário descartável e o estado operacional normal do Codex são permitidos.
9. O README de backends documenta instalação, limites e aviso de franquia.
10. O diff final não contém segredo, e-mail ou token.

Até o item 6 ficar verde, pode-se afirmar que o fork e o backend direto estão
preparados, mas não que o RLM completo foi executado com isolamento.

## Entregáveis previstos

Os caminhos desta tabela são alvos da implementação futura; não são arquivos já
existentes, exceto `pyproject.toml` e `uv.lock`.

| Arquivo | Responsabilidade |
|---|---|
| `rlm/clients/codex.py` | implementação de `CodexClient` |
| `rlm/clients/__init__.py` | registro do backend |
| `rlm/core/types.py` | inclusão de `codex` no tipo público |
| `tests/clients/test_codex.py` | testes determinísticos do cliente |
| `tests/live/test_codex_subscription.py` | smoke direto opt-in |
| `tests/live/test_rlm_codex_docker.py` | smoke E2E opt-in |
| `examples/codex_subscription.py` | exemplo mínimo seguro |
| `docs/src/app/backends/page.tsx` | documentação para usuários |
| `pyproject.toml` e `uv.lock` | extra opcional reproduzível |

## Implantação em etapas

1. **Fundação:** fork, ambiente, extra opcional, spec e baseline.
2. **Cliente isolado:** implementação orientada por testes com executor falso.
3. **Validação da conta:** smoke direto de uma chamada por assinatura.
4. **Isolamento RLM:** instalação do Docker e smoke E2E.
5. **Avaliação:** comparação entre Codex direto e RLM sobre fixtures controladas.
6. **Decisão:** manter apenas se o RLM demonstrar ganho mensurável.

## Garantia possível

Não é possível garantir que um modelo probabilístico sempre escolherá a mesma
trajetória ou produzirá a mesma qualidade. O projeto garantirá algo verificável:
quando os gates estiverem verdes, haverá evidência automática de que o RLM real
chamou o Codex pela conta ChatGPT, executou sua etapa Python em isolamento, fez
uma subconsulta e devolveu uma resposta correta para a fixture.

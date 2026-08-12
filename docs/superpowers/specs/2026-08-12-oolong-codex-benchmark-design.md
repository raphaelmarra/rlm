# Benchmark OOLONG do RLM–Codex

**Estado:** aprovado para implementação  
**Data:** 2026-08-12  
**Base metodológica:** Zhang, Kraska e Khattab, *Recursive Language Models*,
arXiv:2512.24601v3

## Objetivo

Executar uma reprodução metodológica, não uma reprodução numérica, do experimento
OOLONG dos autores do RLM. O benchmark deve responder separadamente:

1. o caminho completo `Codex → rlm-codex → LocalREPL → sub-LM → resultado` funciona
   de modo estável em 25 casos reais;
2. o RLM melhora a qualidade sobre o mesmo modelo chamado diretamente;
3. qual é a diferença de chamadas, tokens e tempo entre os dois métodos.

Vinte e cinco casos, metade da divisão de 50 tarefas descrita no paper, são suficientes
para validar estabilidade E2E e obter um sinal preliminar de qualidade. Eles têm menor
poder estatístico que a divisão completa e não provam superioridade universal do RLM
nem substituem replicações com outros modelos e sementes.

## O que será copiado dos autores

- Dataset oficial `oolongbench/oolong-synth`, revisão
  `f0d59eaf0febf130664cfceb710436c8e3216b2b`.
- Split `validation`, subconjunto `trec_coarse`, `context_len == 131072`.
- Vinte e cinco tarefas de classificação semântica e agregação sobre contexto denso.
- Comparação entre modelo-base com contexto integral e RLM com Python REPL.
- RLM com profundidade máxima 1.
- Mesmo modelo e parâmetros de raciocínio nos dois braços.
- Parser e scorer do ambiente OOLONG upstream: acerto exato para rótulos e datas;
  para respostas numéricas, `0.75 ** abs(gold - prediction)`.
- Relato de qualidade e custo de inferência por consulta.

O experimento do paper usa GPT-5 como raiz e GPT-5-mini nas subchamadas. Esta
reprodução usa `gpt-5.6-terra`, esforço `medium`, tanto no baseline quanto na raiz e
nas subchamadas, porque esse é o backend autenticado pela assinatura ChatGPT desta
integração. Por isso os números absolutos não serão comparados aos números do paper.

## Diretório isolado

O benchmark será um projeto `uv` independente, sem alterar as dependências principais:

```text
benchmarks/oolong_codex/
├── README.md
├── pyproject.toml
├── benchmark.toml
├── oolong_codex/
│   ├── __init__.py
│   ├── __main__.py
│   ├── config.py
│   ├── models.py
│   ├── storage.py
│   ├── dataset.py
│   ├── runner.py
│   ├── scorer.py
│   ├── report.py
│   └── cli.py
├── tests/
│   ├── test_dataset.py
│   ├── test_runner.py
│   ├── test_scorer.py
│   └── test_report.py
├── artifacts/
│   └── .gitignore
└── reports/
```

O `pyproject.toml` dependerá do fork local em modo editável, `datasets` e
`python-dateutil`, seguindo o ambiente OOLONG existente em
`training/environments/oolong/`. Cache do Hugging Face, amostras materializadas,
respostas brutas e checkpoints ficarão em `artifacts/` e não serão versionados.
Configuração, testes, manifestos sem o corpus e relatórios consolidados serão
versionados.

## Protocolo congelado

### Preparação

`prepare` baixa somente os shards necessários, filtra 25 casos e falha se a
cardinalidade não for exatamente 25. Ele grava:

- identificador e hash de cada caso;
- revisão, split, subconjunto, tamanho e ordem;
- contexto e pergunta sem resposta em arquivos de execução;
- respostas-ouro separadas dos prompts.

A seleção usa `seed = 42`. Nenhuma resposta-ouro ou regra de avaliação entra nos
prompts dos modelos.

O prompt lógico dos dois braços é o `_QUESTION_INSTRUCTION` do loader upstream,
seguido da pergunta oficial. No baseline, o contexto integral é acrescentado ao
prompt; no RLM, os mesmos bytes ficam exclusivamente no arquivo carregado como
`context`. O formato de resposta pedido pelo próprio caso é preservado.

### Braço A/B

Os artefatos permanecem `A` e `B` até o scorer terminar.

- **Baseline direto:** `CodexClient.completion` recebe instrução, pergunta e contexto
  integral em uma chamada lógica.
- **RLM:** a mesma instrução e pergunta são enviadas a `rlm-codex`; somente o contexto
  vai por `--context-file`. Cada caso cria exatamente um run durável, recuperado com
  `result --wait`; demora ou perda de saída nunca cria outro run silenciosamente.

Os braços usam `gpt-5.6-terra`, esforço `medium`, limite de 12 iterações, profundidade
máxima 1 e teto de 1.800 segundos por caso. O baseline recebe o mesmo teto, embora
normalmente faça uma única chamada. A execução é sequencial por padrão para evitar
que concorrência e limites da assinatura contaminem latência ou estabilidade. O
harness é retomável por caso e não repete automaticamente uma tentativa terminal.

### Scoring cego e relatório

O scorer determinístico recebe somente `case_id`, resposta prevista e ouro, sem saber
qual método produziu a resposta. Depois dos 50 resultados pontuados, o relatório
revela o mapa A/B e agrega:

- score médio e número de respostas exatas;
- diferença pareada RLM menos baseline;
- intervalo de confiança de 95% por bootstrap pareado com semente fixa;
- chamadas, tokens de entrada/saída e tempo;
- falhas, iterações e subchamadas do RLM.

Como a assinatura não fornece preço por token, `total_cost == null` será relatado
como indisponível, nunca convertido em custo zero.

## Gates e vereditos

O funcionamento E2E passa somente se:

1. os 25 resultados RLM terminarem em `succeeded`;
2. cada metadata indicar `environment_type == "local"`;
3. todos os runs terminarem com `pid == null` e sem PID original vivo;
4. houver trajetória RLM válida nos 25 casos e pelo menos uma subchamada real no
   conjunto;
5. os 25 baselines e os 25 candidatos forem pontuáveis;
6. o corpus e as perguntas materializadas permanecerem inalterados.

O ganho de qualidade é um veredito separado:

- **demonstrado:** diferença média de pelo menos `+0.10` e limite inferior do
  intervalo de confiança pareado de 95% acima de zero;
- **não demonstrado:** diferença menor, intervalo incluindo zero ou empate;
- **regressão:** diferença média negativa;
- **inválido:** braços desiguais, ouro exposto, corpus divergente ou falha do scorer.

O limiar de dez pontos percentuais é congelado antes da execução e é próximo ao ganho
de 12 pontos reportado no paper para GPT-5 no OOLONG de 131K. Passar o gate E2E não
implica automaticamente ganho de qualidade.

## Testes e comandos previstos

```powershell
uv sync --project benchmarks/oolong_codex
uv run --project benchmarks/oolong_codex pytest
uv run --project benchmarks/oolong_codex oolong-codex prepare
uv run --project benchmarks/oolong_codex oolong-codex run
uv run --project benchmarks/oolong_codex oolong-codex score
uv run --project benchmarks/oolong_codex oolong-codex report
uv run --project benchmarks/oolong_codex oolong-codex verify
```

Os testes determinísticos cobrirão seleção e hashes, ausência do ouro nos prompts,
parser/scorer copiado, retomada sem duplicar runs, agregação pareada e gates E2E.
`run` é o único comando que consome a assinatura ChatGPT.

## Segurança e limites

O corpus oficial é tratado como confiável. O RLM usa execução local confiável, não
isolada, sem Docker. O benchmark mede um modelo, um esforço de raciocínio, uma divisão
e uma execução por caso; portanto, o resultado autoriza uma decisão sobre esta
integração, não uma alegação geral sobre todos os RLMs.

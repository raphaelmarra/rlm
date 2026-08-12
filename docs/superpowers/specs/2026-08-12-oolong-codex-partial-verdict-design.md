# Publicação do veredito parcial OOLONG–Codex

**Estado:** aprovado para implementação  
**Data:** 2026-08-12

## Objetivo

Publicar no fork `raphaelmarra/rlm` uma avaliação reproduzível para quem considera
usar RLM como uma camada de CLI sobre uma assinatura Codex. O fork preserva a
estrutura e a documentação upstream, inclui o código da integração Codex e o projeto
completo do benchmark, e torna o resultado facilmente encontrável antes de alguém
investir em uma experimentação semelhante.

## Escopo do veredito

O veredito é deliberadamente específico: não recomendamos RLM como camada CLI
genérica sobre `gpt-5.6-terra` via assinatura Codex para o workload OOLONG
`trec_coarse` de 131K e a configuração congelada deste fork. Ele não é uma alegação
geral contra RLMs, contra outros modelos, nem contra tarefas que exigem decomposição
ou execução iterativa.

O lote planejado tinha 25 pares A/B. O baseline direto A terminou os 25 casos. O
braço RLM B foi interrompido intencionalmente após 9 tentativas: 8 concluídas com
sucesso e 1 falha por resposta vazia do Codex. A interrupção não esconde um
resultado: o relatório deve registrar explicitamente os 16 casos não iniciados, a
falha e a razão da decisão de parar.

## Informação publicada

### Raiz do fork

O `README.md` ganha uma nota curta e visível, sem alterar a apresentação do projeto
upstream. Ela aponta para o relatório parcial e resume o escopo, a conclusão e a
regra prática: para este cenário, uma chamada Codex direta é o caminho recomendado.

### Projeto do benchmark

`benchmarks/oolong_codex/` é versionado por inteiro, exceto `artifacts/`. Ele contém
o harness, testes, configuração congelada e instruções de reprodução. O corpus,
perguntas, ouro, cache, checkpoints e respostas brutas continuam ignorados para não
publicar dados de benchmark nem arquivos volumosos.

### Evidência canônica

`benchmarks/oolong_codex/reports/2026-08-12-partial-verdict.md` será o dono canônico
da análise humana; um JSON correspondente guardará os números agregados legíveis por
ferramentas. Ambos deverão conter:

- configuração A/B, dataset, revisão, modelo e limites;
- cobertura real: A 25/25; B 8 `succeeded`, 1 `failed`, 16 não iniciados;
- scoring dos oito pares completos e respostas que divergem entre os braços;
- chamadas, tokens de entrada e saída, tempo de parede e falhas;
- justificativa de encerramento e limites de inferência;
- comandos de reprodução, incluindo a observação de que `run` consome a assinatura.

Os números já observados nos oito pares B bem-sucedidos são parte da evidência:
149 chamadas contra 8, 1.608,4 s contra 122,0 s, 2.423.172 tokens de entrada contra
883.337 e 236.384 de saída contra 4.178. Isso equivale a 18,6× mais chamadas,
13,2× mais tempo, 2,7× mais entrada e 56,6× mais saída. Como a assinatura não
fornece preço por token, o relatório não deve inventar custo monetário.

## Governança

Uma ADR registra a decisão de não recomendar esta superfície como caminho padrão do
fork. `ROADMAP.md` fecha as etapas de benchmark e decisão com o qualificativo
“parcial”; `CHANGELOG.md` aponta para a evidência; `INDEX.md` e `STRUCTURE.md`
catalogam o projeto e seu relatório. Esses documentos não repetem as tabelas nem os
números do relatório.

## Critérios de aceite

1. O fork contém todo o código e testes do benchmark, sem artefatos privados.
2. Um leitor da raiz encontra o veredito e a evidência em no máximo um clique.
3. O relatório separa fatos medidos, conclusão de produto e limites metodológicos.
4. Nenhuma frase apresenta os oito pares como um estudo completo de 25 casos.
5. Os testes deterministas do benchmark e os checks de estilo passam antes da
   publicação.
6. A branch publicada no `origin` contém os commits da integração Codex, do benchmark
   e do veredito, preservando o relacionamento com `upstream`.

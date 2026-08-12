# RLM–Codex Local Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar ao Codex uma capacidade RLM descoberta por `$usar-rlm`, invocada pelo shell e executada localmente, sem Docker ou WSL, com prova real na sessão atual e em um processo Codex novo.

**Architecture:** A CLI global preserva jobs duráveis e inicia um worker em grupo de processos separado. O worker instancia `RLM(environment="local")`; o `LocalREPL` executa Python em seu diretório temporário e o `CodexClient` usa exclusivamente a conta ChatGPT. A skill decide quando delegar, compõe `start` com `result --wait` e devolve a resposta ao mesmo Codex.

**Tech Stack:** Python 3.11, `openai-codex`, `argparse`, JSON/JSONL, `LocalREPL`, `pytest`, Ruff, ty, pre-commit, PowerShell e Codex skills.

## Global Constraints

- Não usar Docker, WSL 2 ou MCP no caminho `rlm-codex`.
- O backend aceita somente autenticação `chatgpt`; `OPENAI_API_KEY` não vazia falha antes da criação do worker.
- O worker local é uma fronteira de ciclo de vida, não uma sandbox.
- Fixar `environment="local"`, `max_depth=1`, `max_concurrent_subcalls=1` e esforço `medium`.
- `max_iterations` fica entre `1` e `20`, com padrão `6`.
- `max_timeout` fica entre `30` e `3600` segundos, com padrão `600`.
- O contexto total fica entre `1 byte` e `50 MiB`, com no máximo `200` arquivos.
- Todo comando, exceto `events --follow`, escreve exatamente um objeto JSON em `stdout`.
- Estado operacional vive fora dos projetos e pode ser redirecionado por `RLM_CODEX_HOME`.
- Testes reais exigem somente `RLM_LIVE_CODEX=1` e ausência de `OPENAI_API_KEY`.
- Nenhum segredo, e-mail ou token aparece em estado, eventos, logs, testes ou documentação.

---

### Task 1: Trocar o runner para `LocalREPL`

**Files:**
- Modify: `tests/codex_tool/test_runner.py`
- Modify: `rlm/codex_tool/runner.py`

**Interfaces:**
- Consumes: `run_rlm(request: Mapping[str, Any], callbacks: Callbacks, *, rlm_factory=RLM)`.
- Produces: uma única construção de `RLM` com `environment="local"`, sem argumentos Docker e com os limites vigentes.

- [ ] **Step 1: Escrever o teste RED do ambiente local**

```python
def test_runner_always_builds_local_rlm() -> None:
    instances: list[FakeRLM] = []

    def factory(**kwargs: Any) -> FakeRLM:
        instance = FakeRLM(**kwargs)
        instances.append(instance)
        return instance

    result = run_rlm(valid_request(), callbacks=Callbacks(), rlm_factory=factory)

    instance = instances[0]
    assert result.response == "answer"
    assert instance.kwargs["environment"] == "local"
    assert "environment_kwargs" not in instance.kwargs
    assert instance.kwargs["max_depth"] == 1
    assert instance.kwargs["max_concurrent_subcalls"] == 1
```

- [ ] **Step 2: Executar o teste e confirmar a falha pelo valor `docker`**

Run: `uv run pytest tests/codex_tool/test_runner.py::test_runner_always_builds_local_rlm -q`

Expected: FAIL mostrando `docker != local`.

- [ ] **Step 3: Fazer a troca mínima no runner**

```python
with rlm_factory(
    backend="codex",
    backend_kwargs={
        "model_name": validated.model,
        "reasoning_effort": "medium",
    },
    environment="local",
    max_depth=1,
    max_iterations=validated.max_iterations,
    max_timeout=validated.max_timeout,
    max_concurrent_subcalls=1,
    logger=RLMLogger(),
    on_iteration_start=callbacks.on_iteration_start,
    on_iteration_complete=callbacks.on_iteration_complete,
    on_subcall_start=callbacks.on_subcall_start,
    on_subcall_complete=callbacks.on_subcall_complete,
) as rlm:
    return rlm.completion(validated.context, root_prompt=validated.question)
```

- [ ] **Step 4: Executar todos os testes do runner**

Run: `uv run pytest tests/codex_tool/test_runner.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rlm/codex_tool/runner.py tests/codex_tool/test_runner.py
git commit -m "feat: run rlm-codex locally"
```

### Task 2: Falhar antes do worker e remover limpeza Docker dos jobs

**Files:**
- Modify: `tests/codex_tool/test_jobs.py`
- Modify: `rlm/codex_tool/jobs.py`
- Modify: `rlm/codex_tool/runner.py`

**Interfaces:**
- Consumes: `JobManager.start(request)` e cancelamento por grupo de processos.
- Produces: `require_subscription_environment() -> None`, chamado antes de `RunStore.create_run`; cancelamento local sem `resource_cleaner`.

- [ ] **Step 1: Escrever testes RED de autenticação antecipada e cancelamento local**

```python
def test_start_rejects_api_key_before_creating_run_or_worker(
    store: RunStore,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    popen = FakePopen()
    manager = JobManager(store, popen_factory=popen, clock=clock)

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        manager.start(valid_request())

    assert popen.calls == []
    assert not store.paths.runs.exists()


def test_force_cancel_terminates_only_the_local_process_tree(
    store: RunStore,
    clock: Clock,
) -> None:
    state = store.create_run({"question": "question"}, {"x": "1"}, run_id="run-1")
    store.transition(state.id, RunStatus.RUNNING, pid=1234, heartbeat_at=clock.now)
    forced: list[int] = []
    manager = JobManager(
        store,
        signal_sender=lambda pid: None,
        force_terminator=forced.append,
        process_checker=lambda pid: True,
        sleeper=lambda seconds: None,
        clock=clock,
    )

    cancelled = manager.cancel(state.id, force=True, grace_seconds=0)

    assert forced == [1234]
    assert cancelled.status is RunStatus.CANCELLED
```

- [ ] **Step 2: Executar os testes e confirmar as duas falhas esperadas**

Run: `uv run pytest tests/codex_tool/test_jobs.py -q`

Expected: FAIL porque `start` ainda cria o run e `JobManager` ainda possui limpeza Docker.

- [ ] **Step 3: Implementar o preflight mínimo e simplificar `JobManager`**

```python
def require_subscription_environment() -> None:
    if os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY must be unset when using the Codex backend")
```

Chamar essa função depois de validar a requisição e antes de `create_run`. Remover `cleanup_docker_resources`, `resource_cleaner` e todas as chamadas relacionadas; preservar sinal cooperativo e encerramento forçado da árvore.

- [ ] **Step 4: Executar jobs, worker e cliente Codex**

Run: `uv run pytest tests/codex_tool/test_jobs.py tests/codex_tool/test_worker.py tests/clients/test_codex.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rlm/codex_tool/runner.py rlm/codex_tool/jobs.py tests/codex_tool/test_jobs.py
git commit -m "feat: enforce local worker preflight"
```

### Task 3: Tornar `doctor` e o instalador locais e autossuficientes

**Files:**
- Modify: `tests/codex_tool/test_cli.py`
- Modify: `tests/codex_tool/test_skill.py`
- Modify: `rlm/codex_tool/cli.py`
- Modify: `scripts/install_codex_tool.ps1`

**Interfaces:**
- Consumes: `run_doctor(paths) -> list[dict[str, Any]]` e o instalador PowerShell.
- Produces: check positivo `execution_mode` com `local trusted execution; not sandboxed`; nenhum check ou requisito Docker/WSL.

- [ ] **Step 1: Escrever o teste RED do diagnóstico real**

```python
def test_doctor_reports_trusted_local_execution_without_docker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    checks = run_doctor(CodexPaths(tmp_path / "state"))
    by_name = {check["name"]: check for check in checks}

    assert by_name["execution_mode"] == {
        "name": "execution_mode",
        "ok": True,
        "message": "local trusted execution; not sandboxed",
    }
    assert not {"docker_command", "docker_daemon", "docker_image", "wsl"} & by_name.keys()
```

- [ ] **Step 2: Executar o teste e confirmar a ausência de `execution_mode`**

Run: `uv run pytest tests/codex_tool/test_cli.py::test_doctor_reports_trusted_local_execution_without_docker -q`

Expected: FAIL porque o check local ainda não existe.

- [ ] **Step 3: Remover o diagnóstico Docker e adicionar o contrato explícito**

```python
checks.append(
    diagnostic(
        "execution_mode",
        True,
        "local trusted execution; not sandboxed",
    )
)
```

No instalador, exigir código `0` do `doctor`, remover a lista `allowedFailures` e retirar a sondagem WSL.

- [ ] **Step 4: Provar CLI e instalador determinísticos**

Run: `uv run pytest tests/codex_tool/test_cli.py tests/codex_tool/test_skill.py -q`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_codex_tool.ps1 -WhatIf`

Expected: PASS e nenhuma alteração de perfil no `-WhatIf`.

- [ ] **Step 5: Commit**

```powershell
git add rlm/codex_tool/cli.py scripts/install_codex_tool.ps1 tests/codex_tool/test_cli.py tests/codex_tool/test_skill.py
git commit -m "feat: diagnose trusted local execution"
```

### Task 4: Ensinar a skill a decidir, invocar e reintegrar o resultado

**Files:**
- Modify: `.agents/skills/usar-rlm/SKILL.md`
- Modify: `.agents/skills/usar-rlm/references/protocol.md`
- Modify: `.agents/skills/usar-rlm/agents/openai.yaml`
- Modify: `tests/codex_tool/test_skill.py`
- Create: `docs/reviews/2026-08-12-usar-rlm-forward-test.md`

**Interfaces:**
- Consumes: a CLI local já verde e um processo Codex limpo executado fora do checkout.
- Produces: uma skill curta que roda `doctor` uma vez por sessão, inicia um único run, usa `result --wait`, consulta `status/events` somente quando necessário e incorpora `result.response` na tarefa original.

- [ ] **Step 1: Congelar o cenário comportamental antes da edição**

Usar a fixture `tests/live/fixtures/recursive_context.json` e a mesma demanda neutra em todas as execuções: “Analise o arquivo fornecido com as ferramentas locais adequadas, encontre o código derivado e explique de onde veio.” O sucesso exige um único `run.id`, resultado correto, distinção entre resposta RLM e avaliação Codex e reconhecimento de execução local não isolada.

- [ ] **Step 2: Executar o baseline sem disponibilizar `$usar-rlm` e preservar a saída bruta**

Run: `$fixture = (Resolve-Path "tests/live/fixtures/recursive_context.json").Path; codex exec -C "$env:TEMP" --json "Analise o arquivo fornecido com as ferramentas locais adequadas, encontre o código derivado e explique de onde veio: $fixture"`

Expected: registrar a decisão natural do agente e qualquer omissão; não interpretar o baseline como prova de ganho.

- [ ] **Step 3: Escrever a revisão mínima da skill**

O corpo deve declarar `local trusted execution; not sandboxed`, o caminho feliz abaixo e a obrigação de usar a resposta na tarefa:

```powershell
rlm-codex doctor
$start = rlm-codex start --question "Analise o corpus e responda com evidências" --context-file "arquivo" | ConvertFrom-Json
rlm-codex result $start.run.id --wait --wait-timeout 900
```

Manter `status`, `events`, `list`, `cancel` e `prune` na referência para recuperação; remover toda menção a container ou limpeza Docker.

- [ ] **Step 4: Validar estrutura e executar o mesmo cenário com a skill**

Run: `uv run python C:/Users/gouve/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/usar-rlm`

Run: `uv run pytest tests/codex_tool/test_skill.py -q`

Run: `$fixture = (Resolve-Path "tests/live/fixtures/recursive_context.json").Path; codex exec -C "$env:TEMP" --json "`$usar-rlm Analise o arquivo fornecido, encontre o código derivado e explique de onde veio: $fixture"`

Expected: PASS estrutural; o agente executa um único run, espera seu resultado e o usa na resposta.

- [ ] **Step 5: Registrar RED, GREEN e limitações sem segredos**

O relatório registra prompt neutro, versões, comandos, decisões observadas, run id sanitizado, resultado, desvios e veredito comportamental. Não copia autenticação, e-mail, tokens ou caminhos de credenciais.

- [ ] **Step 6: Commit**

```powershell
git add .agents/skills/usar-rlm tests/codex_tool/test_skill.py docs/reviews/2026-08-12-usar-rlm-forward-test.md
git commit -m "feat: teach Codex to use local RLM"
```

### Task 5: Provar RLM local e a CLI ponta a ponta

**Files:**
- Create: `tests/live/test_rlm_codex_local.py`
- Modify: `tests/live/test_rlm_codex_cli.py`
- Modify: `tests/live/fixtures/recursive_context.json`
- Remove: `tests/live/test_rlm_codex_docker.py`

**Interfaces:**
- Consumes: assinatura ChatGPT, `run_rlm`, CLI durável e fixture sintética.
- Produces: prova de iteração raiz, uma `llm_query`, resposta `RLM-CODEX-7391`, persistência, cancelamento, prune, fonte intacta e ausência de worker residual.

- [ ] **Step 1: Converter os smokes para opt-in exclusivamente Codex**

```python
LIVE_ENABLED = os.getenv("RLM_LIVE_CODEX") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE_ENABLED,
    reason="requires RLM_LIVE_CODEX=1",
)
```

No teste direto, nomear o caso `test_live_rlm_uses_llm_query_inside_local_repl` e manter as asserções de uma subconsulta, tokens, custo `None`, fixture intacta e trajetória raiz. No teste CLI, guardar os PIDs retornados por `start` e provar estado terminal com `pid is None` e `process_exists(original_pid) is False`.

- [ ] **Step 2: Confirmar que os smokes são ignorados sem opt-in**

Run: `uv run pytest tests/live/test_rlm_codex_local.py tests/live/test_rlm_codex_cli.py -q`

Expected: `2 skipped`.

- [ ] **Step 3: Executar o RLM local real**

Run: `$env:RLM_LIVE_CODEX='1'; uv run pytest tests/live/test_rlm_codex_local.py -q`

Expected: PASS com `RLM-CODEX-7391`, iteração de profundidade zero e exatamente uma `llm_query`.

- [ ] **Step 4: Executar CLI real, cancelamento e prune**

Run: `$env:RLM_LIVE_CODEX='1'; uv run pytest tests/live/test_rlm_codex_cli.py -q`

Expected: PASS para `start/status/events/result/list/cancel/prune`, sem worker residual nem arquivo extra junto à fixture.

- [ ] **Step 5: Commit**

```powershell
git add tests/live
git commit -m "test: prove local RLM Codex workflow"
```

### Task 6: Instalar e usar o RLM nesta sessão

**Files:**
- Create: `docs/reviews/2026-08-12-rlm-codex-current-session-smoke.md`
- Modify: código ou skill somente se a prova revelar um defeito reproduzível.

**Interfaces:**
- Consumes: instalação editável, skill global e spec local vigente.
- Produces: evidência de que o Codex da sessão atual executou a ferramenta, recebeu a resposta e a aplicou numa auditoria real da implementação.

- [ ] **Step 1: Instalar a CLI editável e sincronizar a skill**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_codex_tool.ps1`

Expected: `rlm-codex` no `PATH`, skill com manifesto válido e `doctor` verde.

- [ ] **Step 2: Verificar fora do checkout**

Run: `Push-Location $env:TEMP; rlm-codex doctor; Pop-Location`

Expected: `ok=true`, conta `chatgpt`, skill sincronizada e `execution_mode` local confiável.

- [ ] **Step 3: Delegar uma auditoria real ao RLM nesta sessão**

Run: `$start = rlm-codex start --question "Compare a spec com código e testes. Liste somente critérios ainda sem evidência direta, citando arquivo e motivo." --context-file "docs/superpowers/specs/2026-08-12-rlm-codex-local-execution-design.md" --context-file "rlm/codex_tool/runner.py" --context-file "rlm/codex_tool/cli.py" --context-file "rlm/codex_tool/jobs.py" --context-file "tests/live/test_rlm_codex_local.py" --context-file "tests/live/test_rlm_codex_cli.py" | ConvertFrom-Json`

Run: `rlm-codex result $start.run.id --wait --wait-timeout 900`

Expected: um único run terminal; a resposta identifica gaps verificáveis ou confirma cada área com evidência.

- [ ] **Step 4: Usar a resposta na implementação e registrar impacto**

Verificar cada afirmação do RLM contra os arquivos. Corrigir por TDD qualquer gap real; no relatório, registrar o que a resposta mudou ou confirmou e separar claramente a saída RLM da avaliação do Codex.

- [ ] **Step 5: Commit**

```powershell
git add docs/reviews/2026-08-12-rlm-codex-current-session-smoke.md
git commit -m "docs: prove RLM use in current Codex session"
```

### Task 7: Provar portabilidade e medir a skill `1 x 1`

**Files:**
- Create: `docs/reviews/2026-08-12-rlm-codex-external-smoke.md`
- Create: `docs/reviews/2026-08-12-usar-rlm-benchmark.md`

**Interfaces:**
- Consumes: dois processos Codex limpos fora do checkout, mesma versão/modelo/ferramentas/fixture/limites e uma rubric congelada.
- Produces: prova explícita com `$usar-rlm` e comparação neutra baseline versus candidato, sem confundir funcionamento com ganho incremental.

- [ ] **Step 1: Congelar tarefa, fonte e rubric antes das execuções**

Tarefa neutra: “Analise o arquivo fornecido com as ferramentas locais adequadas, encontre o código derivado e explique de onde veio.” Rubric cega: resposta correta; decisão explícita de usar ou não RLM; no máximo um `start`; preservação do run id; recuperação do resultado; integração da resposta; relato honesto de confiança. Ganho material significa fechar pelo menos um critério crítico que o baseline não fecha, sem regressão crítica.

- [ ] **Step 2: Provar invocação explícita em processo novo**

Run: `$fixture = (Resolve-Path "tests/live/fixtures/recursive_context.json").Path; codex exec -C "$env:TEMP" --json "`$usar-rlm Analise $fixture, acompanhe até o resultado e use a resposta para explicar o código derivado."`

Expected: o processo encontra a skill e a CLI fora do checkout, cria um único run e retorna a resposta correta.

- [ ] **Step 3: Executar baseline e candidato com a mesma demanda neutra**

Executar uma vez sem a skill candidata disponível e uma vez com ela disponível, mantendo iguais modelo, ferramentas, diretório, fixture e demanda. Preservar as saídas opacas como A e B antes de revelar a atribuição.

- [ ] **Step 4: Avaliar cegamente e registrar o veredito limitado**

O relatório contém: resultado individual e gaps; placar A/B; descobertas exclusivas marcadas `não replicadas`; problemas comuns; limitações de validade; veredito `demonstrado`, `não demonstrado` ou `inválido`; ajuste mínimo; melhor resposta consolidada.

- [ ] **Step 5: Commit**

```powershell
git add docs/reviews/2026-08-12-rlm-codex-external-smoke.md docs/reviews/2026-08-12-usar-rlm-benchmark.md
git commit -m "docs: record RLM portability and skill benchmark"
```

### Task 8: Fechar verificação, segurança e governança

**Files:**
- Modify: `README.md`
- Modify: `docs/INDEX.md`
- Modify: `docs/STRUCTURE.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/ABERTO.md`

**Interfaces:**
- Consumes: implementação e evidências das Tasks 1–7.
- Produces: documentação coerente, treze critérios de aceite ligados a evidência e árvore versionada sem segredo.

- [ ] **Step 1: Atualizar a documentação pelo estado observado**

Marcar etapas como concluídas somente quando o gate correspondente tiver saída recente. INDEX lista o plano e os três relatórios novos; STRUCTURE deixa de chamar o plano local de pendente; README explica instalação e uso local confiável sem apresentar Docker como requisito de `rlm-codex`.

- [ ] **Step 2: Executar estilo, tipos e suíte determinística completos**

Run: `uv run ruff check --fix .`

Run: `uv run ruff format .`

Run: `uv run pre-commit run --all-files`

Run: `uv run ty check`

Run: `uv run pytest`

Expected: todos com código `0`; skips somente os opt-ins documentados.

- [ ] **Step 3: Reexecutar todos os smokes reais**

Run: `$env:RLM_LIVE_CODEX='1'; uv run pytest tests/live -q`

Expected: smoke direto do cliente, RLM local e CLI real verdes; nenhum teste depende de `RLM_LIVE_DOCKER`.

- [ ] **Step 4: Auditar os treze critérios da spec e a coerência documental**

Para cada item de `Critérios de aceite`, apontar comando, artefato ou resultado atual. Rodar a auditoria mecânica de placeholders, caminhos citados, referências a decisões substituídas e aliases terminológicos; registrar qualquer ausência como trabalho não concluído.

- [ ] **Step 5: Sanitizar e conferir o diff**

Run: `git diff --check`

Run: `git grep -n -I -E "(sk-[A-Za-z0-9_-]+|Bearer [A-Za-z0-9._-]+|gouveiamarra@)" -- . ":(exclude)uv.lock"`

Run: `git status --short`

Expected: nenhum segredo ou e-mail privado introduzido e somente arquivos intencionais.

- [ ] **Step 6: Commit final**

```powershell
git add README.md docs rlm tests scripts .agents/skills/usar-rlm
git commit -m "docs: close local RLM Codex acceptance"
```

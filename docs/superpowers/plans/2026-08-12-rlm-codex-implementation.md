# RLM–Codex Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar `rlm-codex` como ferramenta global que o Codex usa para executar,
observar, cancelar e recuperar trabalhos RLM com autenticação ChatGPT e Python isolado
em Docker.

**Architecture:** `CodexClient` adapta o SDK Python oficial ao `BaseLM`. Uma CLI sem
daemon controla workers descartáveis por meio de snapshots JSON atômicos sob
`RLM_CODEX_HOME`; o worker instancia o RLM real com `DockerREPL`, registra eventos e
encerra todos os recursos em estado terminal. A skill `$usar-rlm` ensina um processo
Codex novo a operar essa CLI de qualquer diretório.

**Tech Stack:** Python 3.11, `openai-codex`, `argparse`, JSON/JSON Lines, `pytest`,
`pytest-asyncio`, Docker Desktop/WSL 2, PowerShell e skills Codex.

## Global Constraints

- O backend aceita somente autenticação `chatgpt`; `OPENAI_API_KEY` não vazia falha antes de inferência.
- O código gerado pelo modelo nunca executa em `local` ou `ipython`; o primeiro release fixa `environment="docker"`.
- O primeiro release fixa `max_depth=1`, `max_concurrent_subcalls=1` e esforço `medium`.
- `max_iterations` fica entre `1` e `20`, com padrão `6`.
- `max_timeout` fica entre `30` e `3600` segundos, com padrão `600`.
- O contexto total fica entre `1 byte` e `50 MiB`, com no máximo `200` arquivos.
- Todo comando, exceto `events --follow`, escreve exatamente um objeto JSON em `stdout`.
- Estado operacional vive fora dos projetos e pode ser redirecionado por `RLM_CODEX_HOME`.
- Nenhum arquivo original é montado no container; o worker usa apenas o snapshot protegido.
- Testes reais exigem `RLM_LIVE_CODEX=1`; testes Docker também exigem `RLM_LIVE_DOCKER=1`.
- Nenhum segredo, e-mail ou token aparece em estado, eventos, logs, testes ou documentação.

---

### Task 1: Adaptador `CodexClient` e registro do backend

**Files:**
- Create: `rlm/clients/codex.py`
- Modify: `rlm/clients/__init__.py`
- Modify: `rlm/core/types.py`
- Test: `tests/clients/test_codex.py`
- Test: `tests/test_imports.py`

**Interfaces:**
- Consumes: `BaseLM`, `ModelUsageSummary`, `UsageSummary`, `openai_codex.Codex`, `AsyncCodex`, `Sandbox` e `ApprovalMode`.
- Produces: `CodexClient.completion(prompt, model=None) -> str`, `acompletion(prompt, model=None) -> str`, `get_usage_summary() -> UsageSummary` e `get_last_usage() -> ModelUsageSummary`.
- Produces: `get_client("codex", backend_kwargs) -> CodexClient` com importação preguiçosa.

- [x] **Step 1: Escrever os testes de serialização e autenticação que falham**

```python
def test_completion_rejects_api_key_before_executor(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    executor = FakeCodexExecutor()
    client = CodexClient(model_name="gpt-5.6-terra", executor=executor)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        client.completion("hello")
    assert executor.calls == []


def test_completion_preserves_message_order_and_tracks_usage(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    executor = FakeCodexExecutor(response="next", input_tokens=12, output_tokens=4)
    client = CodexClient(model_name="gpt-5.6-terra", executor=executor)
    assert client.completion([
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "attempt"},
    ]) == "next"
    assert executor.calls[0].messages[-1]["content"] == "attempt"
    assert client.get_last_usage().total_input_tokens == 12
```

- [x] **Step 2: Executar os testes e confirmar RED**

Run: `uv run pytest tests/clients/test_codex.py tests/test_imports.py -q`

Expected: FAIL porque `rlm.clients.codex` e o backend literal ainda não existem.

- [x] **Step 3: Implementar o executor SDK curto e o cliente mínimo**

```python
@dataclass(frozen=True)
class CodexExecution:
    response: str
    input_tokens: int
    output_tokens: int


class CodexClient(BaseLM):
    def completion(
        self,
        prompt: str | list[dict[str, Any]],
        model: str | None = None,
    ) -> str:
        self.validate_environment()
        execution = self.executor.run(
            messages=normalize_messages(prompt),
            model=model or self.model_name,
            timeout=self.timeout,
            reasoning_effort=self.reasoning_effort,
            service_tier=self.service_tier,
        )
        self.track_usage(execution, model or self.model_name)
        return require_response(execution.response)
```

O executor padrão abre `Codex()` em contexto, exige `account.root.type == "chatgpt"`,
cria temporário vazio, inicia thread com `ephemeral=True`, `Sandbox.read_only` e
`ApprovalMode.deny_all`, executa uma única rodada e remove o temporário no `finally`.

- [x] **Step 4: Cobrir async, conta inválida, resposta vazia, timeout e limpeza**

Run: `uv run pytest tests/clients/test_codex.py -q`

Expected: PASS com testes separados para sucesso, erro e cancelamento assíncrono.

- [x] **Step 5: Validar registro e estilo**

Run: `uv run ruff check rlm/clients tests/clients tests/test_imports.py`

Run: `uv run ruff format --check rlm/clients tests/clients tests/test_imports.py`

- [x] **Step 6: Commit**

```bash
git add rlm/clients/codex.py rlm/clients/__init__.py rlm/core/types.py tests/clients/test_codex.py tests/test_imports.py
git commit -m "feat: add Codex subscription client"
```

### Task 2: Smoke direto, exemplo e documentação do backend

**Files:**
- Create: `tests/live/test_codex_subscription.py`
- Create: `tests/live/__init__.py`
- Create: `examples/codex_subscription.py`
- Modify: `docs/src/app/backends/page.tsx`
- Modify: `README.md`

**Interfaces:**
- Consumes: `CodexClient` da Task 1.
- Produces: smoke opt-in que exige `RLM_CODEX_OK` sem aceitar chave da API.

- [x] **Step 1: Escrever o teste opt-in e confirmar skip padrão**

```python
@pytest.mark.skipif(
    os.getenv("RLM_LIVE_CODEX") != "1",
    reason="requires RLM_LIVE_CODEX=1",
)
def test_live_codex_subscription_returns_marker(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = CodexClient(model_name="gpt-5.6-terra", timeout=180)
    assert client.completion("Reply with exactly RLM_CODEX_OK") == "RLM_CODEX_OK"
```

Run: `uv run pytest tests/live/test_codex_subscription.py -q`

Expected: `1 skipped` sem a variável opt-in.

- [x] **Step 2: Documentar instalação e exemplo seguro**

O exemplo deve construir `RLM(backend="codex", environment="docker")`, rejeitar
execução quando `OPENAI_API_KEY` estiver presente e não conter caminhos locais.

- [x] **Step 3: Executar o smoke real por assinatura**

Run: `$env:RLM_LIVE_CODEX='1'; Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue; uv run pytest tests/live/test_codex_subscription.py -q`

Expected: `1 passed` e resposta exata `RLM_CODEX_OK`.

- [x] **Step 4: Commit**

```bash
git add tests/live examples/codex_subscription.py docs/src/app/backends/page.tsx README.md
git commit -m "test: prove Codex subscription backend"
```

### Task 3: Protocolo, caminhos e armazenamento atômico

**Files:**
- Create: `rlm/codex_tool/__init__.py`
- Create: `rlm/codex_tool/protocol.py`
- Create: `rlm/codex_tool/paths.py`
- Create: `rlm/codex_tool/store.py`
- Create: `tests/codex_tool/__init__.py`
- Create: `tests/codex_tool/test_protocol.py`
- Create: `tests/codex_tool/test_store.py`

**Interfaces:**
- Produces: `RunStatus`, `TERMINAL_STATUSES`, `RunState`, `success_envelope()` e `error_envelope()`.
- Produces: `CodexPaths.from_environment()`, `RunStore.create_run()`, `read_state()`, `transition()`, `append_event()` e `write_result()`.

- [ ] **Step 1: Escrever testes de estados e envelopes que falham**

```python
def test_run_state_rejects_invalid_transition():
    state = RunState.new("run-1")
    with pytest.raises(StateConflictError):
        state.transition(RunStatus.SUCCEEDED)


def test_error_envelope_has_stable_schema():
    assert error_envelope("result", "RUN_NOT_FOUND", "missing", False) == {
        "schema_version": "1",
        "ok": False,
        "command": "result",
        "error": {"code": "RUN_NOT_FOUND", "message": "missing", "retryable": False},
    }
```

Run: `uv run pytest tests/codex_tool/test_protocol.py -q`

Expected: FAIL por módulos ausentes.

- [ ] **Step 2: Implementar protocolo e transições permitidas**

```python
ALLOWED_TRANSITIONS = {
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.CANCELLED, RunStatus.ORPHANED},
    RunStatus.RUNNING: {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLING,
        RunStatus.ORPHANED,
    },
    RunStatus.CANCELLING: {RunStatus.CANCELLED, RunStatus.FAILED},
}
```

- [ ] **Step 3: Escrever testes de escrita atômica, concorrência e corrupção**

Run: `uv run pytest tests/codex_tool/test_store.py -q`

Expected: FAIL porque `RunStore` não existe.

- [ ] **Step 4: Implementar store com temporário adjacente, flush e `os.replace`**

```python
def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
```

- [ ] **Step 5: Validar testes e estilo**

Run: `uv run pytest tests/codex_tool/test_protocol.py tests/codex_tool/test_store.py -q`

Run: `uv run ruff check rlm/codex_tool tests/codex_tool`

- [ ] **Step 6: Commit**

```bash
git add rlm/codex_tool tests/codex_tool
git commit -m "feat: add durable RLM job protocol"
```

### Task 4: Validação de contexto, runner seguro e callbacks de iteração

**Files:**
- Create: `rlm/codex_tool/runner.py`
- Modify: `rlm/core/rlm.py`
- Test: `tests/codex_tool/test_runner.py`
- Test: `tests/test_rlm_query.py`

**Interfaces:**
- Consumes: request e `context.json` do `RunStore`.
- Produces: `validate_request()`, `snapshot_context()` e `run_rlm(request, callbacks) -> RLMChatCompletion`.
- Produces: callbacks `on_iteration_start(depth, iteration)` e `on_iteration_complete(depth, iteration, elapsed)` realmente disparados pelo loop RLM.

- [ ] **Step 1: Escrever testes dos limites de entrada e ambiente fixo**

```python
@pytest.mark.parametrize("iterations", [0, 21])
def test_request_rejects_iteration_limit(iterations):
    with pytest.raises(ValueError, match="max_iterations"):
        validate_request(valid_request(max_iterations=iterations))


def test_runner_always_builds_docker_rlm(fake_rlm_factory):
    run_rlm(valid_request(), callbacks=Callbacks(), rlm_factory=fake_rlm_factory)
    assert fake_rlm_factory.kwargs["environment"] == "docker"
    assert fake_rlm_factory.kwargs["max_depth"] == 1
```

Run: `uv run pytest tests/codex_tool/test_runner.py -q`

Expected: FAIL porque `runner.py` não existe.

- [ ] **Step 2: Implementar validação fail-fast e snapshot por nome/hash/conteúdo**

O snapshot usa dicionário com nomes relativos únicos e conteúdo textual; arquivos
binários ou ilegíveis falham antes de criar o worker.

- [ ] **Step 3: Escrever teste RED para callbacks do loop RLM**

Run: `uv run pytest tests/test_rlm_query.py -k iteration_callback -q`

Expected: FAIL porque o construtor armazena callbacks, mas o loop não os dispara.

- [ ] **Step 4: Disparar callbacks sem permitir que erro do observador quebre o RLM**

```python
self.fire_callback(self.on_iteration_start, self.depth, i + 1)
started = time.perf_counter()
iteration = self._completion_turn(
    prompt=message_history,
    lm_handler=lm_handler,
    environment=environment,
)
self.fire_callback(
    self.on_iteration_complete,
    self.depth,
    i + 1,
    time.perf_counter() - started,
)
```

- [ ] **Step 5: Validar testes e commit**

Run: `uv run pytest tests/codex_tool/test_runner.py tests/test_rlm_query.py -q`

```bash
git add rlm/codex_tool/runner.py rlm/core/rlm.py tests/codex_tool/test_runner.py tests/test_rlm_query.py
git commit -m "feat: add safe RLM job runner"
```

### Task 5: Worker, heartbeat e ciclo de vida de processos

**Files:**
- Create: `rlm/codex_tool/worker.py`
- Create: `rlm/codex_tool/jobs.py`
- Test: `tests/codex_tool/fake_worker.py`
- Test: `tests/codex_tool/test_worker.py`
- Test: `tests/codex_tool/test_jobs.py`

**Interfaces:**
- Produces: `worker_main(run_id, home) -> int`.
- Produces: `JobManager.start()`, `status()`, `events()`, `result()`, `cancel()`, `list_runs()` e `prune()`.

- [ ] **Step 1: Escrever testes RED de start, heartbeat, sucesso e falha**

```python
def test_start_returns_queued_run_and_worker_pid(manager):
    run = manager.start(valid_request())
    assert run.status is RunStatus.QUEUED
    assert run.pid > 0


def test_status_marks_expired_dead_pid_orphaned(manager, clock):
    run = manager.seed_running(pid=999999, heartbeat_age=16)
    assert manager.status(run.id).status is RunStatus.ORPHANED
```

Run: `uv run pytest tests/codex_tool/test_jobs.py tests/codex_tool/test_worker.py -q`

Expected: FAIL porque worker e manager não existem.

- [ ] **Step 2: Implementar worker com heartbeat a cada 2 s e `finally` terminal**

O worker registra `started`, callbacks de iteração/subconsulta, `succeeded` ou `failed`,
persiste resultado/erro sanitizado e encerra heartbeat e RLM em `finally`.

- [ ] **Step 3: Implementar start desacoplado e detecção de órfão em 15 s**

No Windows, `subprocess.Popen` usa grupo de processo novo e redireciona stdout/stderr
para os arquivos do trabalho; em POSIX usa sessão nova.

- [ ] **Step 4: Escrever e passar testes de cancelamento, `--force` e prune**

Run: `uv run pytest tests/codex_tool/test_jobs.py -q`

Expected: PASS, incluindo proibição de remover trabalho ativo.

- [ ] **Step 5: Commit**

```bash
git add rlm/codex_tool/worker.py rlm/codex_tool/jobs.py tests/codex_tool
git commit -m "feat: manage durable RLM workers"
```

### Task 6: CLI JSON e diagnóstico operacional

**Files:**
- Create: `rlm/codex_tool/cli.py`
- Modify: `pyproject.toml`
- Test: `tests/codex_tool/test_cli.py`

**Interfaces:**
- Produces: script `rlm-codex = "rlm.codex_tool.cli:main"`.
- Produces: `doctor`, `start`, `status`, `events`, `result`, `cancel`, `list` e `prune`.
- Produces: códigos de saída `0`, `2`, `3`, `4`, `5` e `10` conforme a spec.

- [ ] **Step 1: Escrever teste RED de `doctor` e objeto JSON único**

```python
def test_doctor_reports_missing_docker_as_preflight_error(cli, env):
    result = cli("doctor", env=env.without_docker())
    assert result.returncode == 3
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "PREFLIGHT_FAILED"
```

Run: `uv run pytest tests/codex_tool/test_cli.py -q`

Expected: FAIL porque `cli.py` e o entry point ainda não existem.

- [ ] **Step 2: Implementar parser e despacho sem imprimir logs no stdout**

```python
def main(argv: Sequence[str] | None = None) -> int:
    try:
        command = build_parser().parse_args(argv)
        payload, exit_code = dispatch(command)
    except CliError as error:
        payload, exit_code = error.to_envelope(), error.exit_code
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code
```

- [ ] **Step 3: Cobrir todos os comandos em subprocesso e `events --follow`**

Run: `uv run pytest tests/codex_tool/test_cli.py -q`

Expected: PASS para argumentos, conflitos, timeout, run inexistente e saída JSONL.

- [ ] **Step 4: Verificar o entry point fora do checkout com home temporário**

Run: `uv tool run --from ".[codex]" rlm-codex doctor`

Expected nesta fase: JSON válido e código `3` exclusivamente por Docker/skill ausentes.

- [ ] **Step 5: Commit**

```bash
git add rlm/codex_tool/cli.py pyproject.toml tests/codex_tool/test_cli.py uv.lock
git commit -m "feat: add rlm-codex command surface"
```

### Task 7: Isolamento reforçado do `DockerREPL`

**Files:**
- Modify: `rlm/environments/docker_repl.py`
- Modify: `tests/test_docker_repl_robustness.py`
- Create: `tests/codex_tool/test_docker_isolation.py`

**Interfaces:**
- Consumes: `run_id` e limites opcionais em `environment_kwargs`.
- Produces: container rotulado, usuário sem privilégio, capabilities removidas,
`no-new-privileges`, limites de CPU/memória/PIDs e rede descartável por trabalho.

- [ ] **Step 1: Escrever teste RED para os argumentos Docker obrigatórios**

```python
def test_docker_run_applies_rlm_codex_isolation(fake_subprocess):
    DockerREPL(run_id="run-1", context_payload="x")
    command = fake_subprocess.command_starting_with("docker", "run")
    label_index = command.index("--label")
    assert command[label_index : label_index + 2] == [
        "--label",
        "io.rlm-codex.run-id=run-1",
    ]
    assert "--cap-drop=ALL" in command
    assert "no-new-privileges" in command
    assert "--pids-limit" in command
```

Run: `uv run pytest tests/codex_tool/test_docker_isolation.py -q`

Expected: FAIL porque o comando upstream ainda usa rede padrão e sem limites.

- [ ] **Step 2: Implementar criação/remoção de rede e argumentos de isolamento**

O setup cria rede por `run_id`, conecta somente container e proxy permitido, registra
todos os recursos com o label do trabalho e remove rede/container no `cleanup()`.

- [ ] **Step 3: Cobrir falha parcial e limpeza idempotente**

Run: `uv run pytest tests/test_docker_repl_robustness.py tests/codex_tool/test_docker_isolation.py -q`

Expected: PASS mesmo se criação do container, instalação de dependência ou remoção falhar.

- [ ] **Step 4: Commit**

```bash
git add rlm/environments/docker_repl.py tests/test_docker_repl_robustness.py tests/codex_tool/test_docker_isolation.py
git commit -m "feat: isolate RLM Docker jobs"
```

### Task 8: Skill `$usar-rlm` e instalador reproduzível

**Files:**
- Create: `.agents/skills/usar-rlm/SKILL.md`
- Create: `.agents/skills/usar-rlm/references/protocol.md`
- Create: `scripts/install_codex_tool.ps1`
- Create: `tests/codex_tool/test_skill.py`
- Modify: `rlm/codex_tool/cli.py`

**Interfaces:**
- Consumes: CLI completa da Task 6.
- Produces: skill de repositório e cópia de usuário em `$HOME/.agents/skills/usar-rlm`.
- Produces: manifesto de origem com commit e hashes para o `doctor` detectar drift.

- [ ] **Step 1: Ler integralmente `skill-creator` e `writing-skills` antes do artefato**

Run: validação manual das instruções dessas duas skills no início da task.

- [ ] **Step 2: Escrever teste RED de frontmatter, gatilhos e comandos**

```python
def test_skill_has_portable_commands_and_no_absolute_paths():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "name: usar-rlm" in text
    for command in ("doctor", "start", "status", "events", "result"):
        assert f"rlm-codex {command}" in text
    assert "C:\\Users\\" not in text
```

Run: `uv run pytest tests/codex_tool/test_skill.py -q`

Expected: FAIL porque a skill ainda não existe.

- [ ] **Step 3: Criar skill curta com fluxo obrigatório e limites de disparo**

A descrição dispara para corpus grande, busca em muitos arquivos, decomposição e pedido
explícito; exclui perguntas simples. O corpo exige `doctor`, start único, observação,
resultado, relato de trajetória e cancelamento somente nas condições da spec.

- [ ] **Step 4: Criar instalador idempotente e teste de drift**

Run: `powershell -ExecutionPolicy Bypass -File scripts/install_codex_tool.ps1 -WhatIf`

Run: `uv run pytest tests/codex_tool/test_skill.py -q`

Expected: PASS sem alterar diretórios fora dos temporários de teste.

- [ ] **Step 5: Instalar CLI e skill no perfil real**

Run: `powershell -ExecutionPolicy Bypass -File scripts/install_codex_tool.ps1`

Run: `Push-Location $env:TEMP; rlm-codex doctor; Pop-Location`

Expected: comando resolvido fora do fork e skill sincronizada; Docker é o único preflight
admitido como indisponível antes da Task 9.

- [ ] **Step 6: Commit**

```bash
git add .agents/skills/usar-rlm scripts/install_codex_tool.ps1 tests/codex_tool/test_skill.py rlm/codex_tool/cli.py
git commit -m "feat: install RLM skill for Codex"
```

### Task 9: Smokes Docker e CLI ponta a ponta

**Files:**
- Create: `tests/live/test_rlm_codex_docker.py`
- Create: `tests/live/test_rlm_codex_cli.py`
- Create: `tests/live/fixtures/recursive_context.json`
- Modify: `rlm/codex_tool/runner.py`

**Interfaces:**
- Consumes: sistema completo das Tasks 1–8 e Docker Desktop ativo.
- Produces: prova de iteração raiz, `llm_query`, resposta correta, uso sem custo monetário,
trajetória, limpeza de worker/container/rede e nenhum write no projeto.

- [ ] **Step 1: Escrever smokes opt-in e confirmar skip sem variáveis**

Run: `uv run pytest tests/live/test_rlm_codex_docker.py tests/live/test_rlm_codex_cli.py -q`

Expected: `2 skipped` quando os opt-ins estão ausentes.

- [ ] **Step 2: Instalar e iniciar WSL 2/Docker Desktop por canais oficiais**

Run: `wsl --status`

Run: `docker version`

Expected: engine Linux respondendo. Reinicialização ou onboarding interativo permanece um
gate operacional explícito; após concluí-lo, repetir ambos os comandos.

- [ ] **Step 3: Executar smoke RLM real**

Run: `$env:RLM_LIVE_CODEX='1'; $env:RLM_LIVE_DOCKER='1'; uv run pytest tests/live/test_rlm_codex_docker.py -q`

Expected: PASS com metadados contendo iteração raiz, uma subconsulta e resposta verificável.

- [ ] **Step 4: Executar smoke CLI e cancelamento cooperativo**

Run: `$env:RLM_LIVE_CODEX='1'; $env:RLM_LIVE_DOCKER='1'; uv run pytest tests/live/test_rlm_codex_cli.py -q`

Expected: PASS para start/status/events/result/list/prune e cancelamento sem processos ou
recursos Docker residuais.

- [ ] **Step 5: Commit**

```bash
git add tests/live rlm/codex_tool/runner.py
git commit -m "test: prove isolated RLM Codex workflow"
```

### Task 10: Prova externa, benchmark e fechamento

**Files:**
- Create: `docs/reviews/2026-08-12-rlm-codex-external-smoke.md`
- Create: `docs/reviews/2026-08-12-usar-rlm-benchmark.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/ABERTO.md`
- Modify: `docs/INDEX.md`
- Modify: `docs/STRUCTURE.md`

**Interfaces:**
- Consumes: CLI e skill instaladas.
- Produces: prova de um processo Codex novo fora do fork e comparação `1 x 1` com rubric
congelada, preservando comandos, resultados, uso e veredito.

- [ ] **Step 1: Congelar fixture e rubric antes das duas execuções**

Rubric: diagnóstico, start único, monitoramento, resultado correto, ausência de API key e
relato de trajetória. O relatório identifica a evidência como `não replicada`.

- [ ] **Step 2: Executar baseline e candidato em processos novos**

Run: `$fixture=(Resolve-Path 'tests/live/fixtures/recursive_context.json').Path; codex exec -C $env:TEMP "Use rlm-codex para descobrir qual código secreto é derivado do arquivo '$fixture', acompanhe o trabalho até o resultado e informe trajetória e uso."`

Run: `$fixture=(Resolve-Path 'tests/live/fixtures/recursive_context.json').Path; codex exec -C $env:TEMP "`$usar-rlm descubra qual código secreto é derivado do arquivo '$fixture', acompanhe o trabalho até o resultado e informe trajetória e uso."`

Expected: ambos preservados; o candidato opera a CLI até resultado correto e não inicia
duplicata silenciosa.

- [ ] **Step 3: Registrar o smoke externo e benchmark sem dados privados**

Os relatórios incluem versão, commit, fixture sintética, critérios, veredito e caminhos
relativos dos artefatos; não incluem prompt privado, e-mail, token ou corpus da MUTATIO.

- [ ] **Step 4: Executar verificação completa**

Run: `uv run ruff check --fix .`

Run: `uv run ruff format .`

Run: `uv run pre-commit run --all-files`

Run: `uv run ty check`

Run: `uv run pytest`

Run: `$env:RLM_LIVE_CODEX='1'; $env:RLM_LIVE_DOCKER='1'; uv run pytest tests/live -q`

Expected: todos os checks verdes, sem mudanças automáticas remanescentes.

- [ ] **Step 5: Auditar os treze critérios e governança**

Para cada critério da spec da ferramenta, registrar evidência direta em um dos dois
relatórios. Atualizar roadmap, changelog, índice, estrutura e questões abertas somente
depois que a evidência correspondente existir.

- [ ] **Step 6: Sanitizar diff e commits**

Run: `git diff --check`

Run: `git grep -n -I -E "(sk-[A-Za-z0-9_-]+|Bearer [A-Za-z0-9._-]+|gouveiamarra@)" -- . ":(exclude)uv.lock"`

Expected: nenhuma credencial, token ou e-mail privado introduzido pelo fork.

- [ ] **Step 7: Commit final**

```bash
git add docs README.md
git commit -m "docs: record RLM Codex acceptance evidence"
```

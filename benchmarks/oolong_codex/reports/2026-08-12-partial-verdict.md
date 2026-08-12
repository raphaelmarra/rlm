# OOLONG Codex partial benchmark

This partial result is not conclusive and does not pass the E2E benchmark.

## Verdict

For this measured configuration, **RLM does not compensate as a generic CLI layer over Codex**. The eight successful pairs show a preliminary quality signal (RLM 7/8 exact, direct Codex 6/8; mean delta `+0.125`), but the bootstrap interval is `[-0.25, 0.5]` and includes zero. The operational penalty is decisive: 149 calls versus 8, 13.2× more wall time, 2.7× more input tokens, and 56.6× more output tokens. One additional RLM attempt failed with an empty Codex response.

We stopped the planned 25-case RLM arm after this signal because continuing would consume substantial subscription runtime without a plausible cost/latency case for this CLI use. This is a scoped engineering recommendation, not a claim that RLM is unhelpful for every model or task.

## Coverage

- Planned cases: `25`
- Paired successful cases: `8`
- A: available `25`, succeeded `25`, failed `0`, missing `0`
- B: available `9`, succeeded `8`, failed `1`, missing `16`

## Paired quality

- Verdict: **not_demonstrated** (not conclusive)
- Mean paired delta: `0.125`
- Paired bootstrap 95%: `[-0.25, 0.5]`

## Paired metrics

- A: calls `8`, input tokens `883337`, output tokens `4178`, wall seconds `121.98584629999823`, failures `0`, subcalls `0`
- B: calls `149`, input tokens `2423172`, output tokens `236384`, wall seconds `1608.4929791999966`, failures `0`, subcalls `105`

## Attempt metrics

- A: calls `25`, input tokens `2766906`, output tokens `12223`, wall seconds `367.1852224999893`, failures `0`, subcalls `0`
- B: calls `149`, input tokens `2423172`, output tokens `236384`, wall seconds `1637.1174710999985`, failures `1`, subcalls `105`

## RLM failures

- 17000253: {"message": "Codex returned an empty response", "type": "ValueError"}

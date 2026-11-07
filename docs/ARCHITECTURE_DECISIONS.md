# Architecture Decisions

## ADR-001: Use AWS Price List API for LLM Cost Calculation

**Date**: 2026-05-13
**Status**: Proposed

### Context

The agent evaluation tool calculates per-invocation LLM inference cost by extracting token counts from trace data and multiplying by per-token pricing. The current implementation uses a 3-tier fallback:

1. User-provided overrides
2. LiteLLM built-in cost map (static, third-party dependency)
3. $0 fallback

LiteLLM's pricing data can lag behind actual AWS pricing changes and introduces an external dependency that must be maintained.

### Decision

Replace LiteLLM with the **AWS Price List Query API** (`pricing:GetProducts` with `ServiceCode=AmazonBedrockFoundationModels`) as the primary pricing source for Bedrock-hosted models.

New fallback chain:

1. User-provided overrides (custom/fine-tuned models)
2. AWS Price List API (all Bedrock-hosted models)
3. $0 fallback (truly unknown models)

### Rationale

Amazon Bedrock now hosts models from Anthropic, OpenAI, Meta, Mistral, Cohere, AI21, Stability, and Amazon — covering the vast majority of models invoked through AgentCore. The Price List API provides authoritative, always-current pricing from the same source AWS uses for billing.

### Pros

- **Always up-to-date**: Pricing reflects current AWS rates without manual updates
- **Authoritative source**: Same data AWS uses for billing — no discrepancies
- **Comprehensive coverage**: Bedrock hosts Anthropic, OpenAI, Meta, Mistral, Cohere, AI21, Stability, and Amazon models
- **Removes third-party dependency**: No longer reliant on LiteLLM package staying current
- **Covers new model launches automatically**: No code changes needed when AWS adds models

### Cons

- **Requires AWS credentials**: Valid credentials with `pricing:GetProducts` permission needed
- **Adds API latency**: ~200-500ms per unique model lookup (mitigated by caching)
- **Only covers Bedrock models**: Non-Bedrock providers (e.g., direct OpenAI API calls) would not be priced
- **Network dependency**: Tool cannot calculate cost offline without credentials
- **Price List JSON is verbose**: Requires parsing nested response format to extract per-token rates

### Mitigations

- **Cache pricing per model ID** within a session — prices don't change intra-day
- **Graceful degradation**: If API call fails (no creds, permission denied, network), fall back to LiteLLM as a best-effort static source and log a warning that pricing may be stale
- **Low permission bar**: `pricing:GetProducts` is read-only and non-sensitive; anyone with AgentCore traces likely already has AWS credentials configured

### Scope

This decision applies to the LLM Inference Cost section only. AgentCore Runtime Cost (compute/memory) uses hardcoded rates from published pricing and is unaffected.

---

## ADR-002: Evaluation Reports, Parallel Execution, and Comparison View

**Date**: 2026-05-13
**Status**: Proposed

### Context

The Streamlit dashboard (`agent-eval/ui/app.py`) currently displays one evaluation run at a time, selected via the sidebar. Multiple output directories already exist on disk (e.g., `real_bedrock_output_coding-session/`, `neo_output_neo-email-triage/`), each containing `results.json`, `trace_eval.json`, and `judge_runs.jsonl`. However, there is no way to:

1. Generate a structured, exportable report from a run
2. Execute multiple evaluations in parallel
3. Compare two or more runs side-by-side

### Decision

Add three capabilities to the Streamlit dashboard:

#### 1. Report Generation

A new tab or sidebar action that produces a structured summary from a single evaluation run, exportable as Markdown or PDF.

**Contents:**
- Overall score + rubric pass/fail breakdown
- Cost breakdown (LLM inference + AgentCore runtime)
- Latency percentiles
- Key judge findings (pass/fail with reasoning excerpts)
- Export via `st.download_button`

**Implementation:** Pure rendering layer over existing `results.json` data. No backend changes required.

#### 2. Parallel Execution

Accept a batch of traces and run evaluations concurrently.

**Mechanism:**
- `st.file_uploader(accept_multiple_files=True)` for batch input
- `concurrent.futures.ThreadPoolExecutor` for parallel evaluation
- `st.progress` / `st.status` for progress tracking
- Each run writes to its own output directory

**Implementation:** In-process parallelism — no external task queue needed.

#### 3. Comparison View

A new page where the user selects 2+ completed runs and sees a side-by-side analysis.

**Comparison dimensions:**
- Overall score
- Total cost (LLM + AgentCore)
- Latency (p50, p95)
- Per-rubric pass/fail with regression highlighting
- Cost-vs-quality scatter plot
- Radar chart overlaying quality dimensions

**Implementation:** `st.multiselect` for run selection, `st.columns` for layout, `plotly` for charts.

### Use Cases

| Scenario | How It Works |
|----------|--------------|
| Model comparison | Same trace evaluated with different models → compare cost vs. quality |
| Regression testing | Same agent before/after prompt change → highlight rubric regressions |
| Architecture comparison | Single-agent vs multi-agent on same task → compare all dimensions |
| Cost optimization | Find cheapest model that still passes all rubrics |

### Pros

- **No infrastructure changes** — all features run within the existing Streamlit process
- **Data model already exists** — output directories with `results.json` are the unit of comparison
- **Immediate value** — comparison view works with existing runs, no re-evaluation needed
- **Exportable reports** — enables sharing results with stakeholders who don't run the dashboard
- **Parallel execution scales linearly** — ThreadPoolExecutor bounded by available CPU/memory

### Cons

- **Streamlit session state complexity** — multi-select and comparison state adds UI complexity
- **Memory pressure** — loading multiple `results.json` + `judge_runs.jsonl` simultaneously for large runs
- **No persistence of comparisons** — comparison is ephemeral (lost on page refresh) unless saved to disk
- **Parallel execution limited by single machine** — no distributed execution; bounded by local resources
- **PDF export dependency** — generating PDF requires an additional library (e.g., `weasyprint` or `pdfkit`)

### Implementation Order

1. **Comparison view** — highest user value; data already exists
2. **Report generation** — quick win; reformats existing data
3. **Parallel execution** — enables comparison at scale

### Open Questions

1. Should comparisons be saveable/shareable (persist to disk as a comparison artifact)?
2. Should parallel execution support different judge configs per run, or same config across all?
3. Is PDF export worth the dependency, or is Markdown sufficient?

---

## ADR-003: Optimization Guidance from Trace Analysis

**Date**: 2026-05-13
**Status**: Proposed

### Context

The evaluation tool already analyzes agent traces for quality (rubric scoring), cost (token pricing), and latency (step timing). A natural extension is to use this same trace data to surface actionable optimization recommendations — helping users improve their agentic solutions without manual trace inspection.

The trace data contains step sequences, timing, token counts, model IDs, tool call patterns, error/retry behavior, subagent delegation, and memory operations. This is sufficient to detect many common inefficiency patterns.

### Decision

Implement a two-tier optimization guidance system:

#### Tier 1: Deterministic Optimization Signals (rule-based)

A new "⚡ Optimizations" tab in the Streamlit dashboard that scans the normalized trace and flags patterns using predefined heuristics.

**Cost signals:**
- Model overuse: expensive model used for steps with low output token count → recommend cheaper model
- Prompt repetition: same prompt prefix repeated across N turns → recommend prompt caching
- Over-reasoning: significantly more model invocations than necessary for task complexity

**Latency signals:**
- Parallelizable steps: sequential steps with no data dependency → recommend parallel execution
- Slow tool dominance: single tool call dominates total latency → recommend caching or batching
- Unnecessary waits: agent waits for full response before independent next step → recommend streaming

**Architecture signals:**
- Retry storms: agent retries same tool 3+ times → recommend fallback tool or better error handling
- Context bloat: subagent receives large context but uses minimal portion → recommend summarization
- Monolithic agent: single agent handles many distinct task types → recommend specialization

**Output format per signal:**
- Category (cost / latency / architecture)
- Severity (⚠️ warning / ℹ️ info)
- Detected pattern with evidence from trace
- Concrete recommendation
- Estimated savings where calculable (e.g., "-$0.004" or "-2.1s")

#### Tier 2: LLM-Powered Analysis (future)

Pass the trace + Tier 1 signals to an LLM judge for contextual, architectural recommendations. Provides richer guidance but adds inference cost and non-determinism.

### Available Trace Signals

| Signal | Source | Optimization Category |
|--------|--------|----------------------|
| Step sequence + timing | `steps[].start_time`, `end_time` | Latency (parallelization) |
| Token counts per step | `steps[].attributes.prompt_tokens` | Cost (model selection, caching) |
| Model ID per invocation | `steps[].attributes.model_id` | Cost (right-sizing) |
| Tool call patterns | `steps[].kind == TOOL_CALL` | Latency + Cost (deduplication) |
| Error/retry sequences | `steps[].status == ERROR` | Architecture (fallbacks) |
| Subagent context size | `steps[].attributes.prompt_tokens` on delegation | Cost (context summarization) |
| Memory operations | `steps[].attributes.aws.operation.name` | Cost (batching retrievals) |

### Limitations

- **Trace shows what happened, not what's possible** — cannot recommend tools the agent doesn't know about
- **Cannot infer intent** — sequential calls may be intentional (safety, ordering constraints)
- **No ground truth for "optimal"** — suggestions are heuristic, not provably best
- **Prompt content often absent** — traces may not include full prompt text, limiting prompt-level recommendations

The tool should frame outputs as **signals and suggestions** (like a linter) rather than **optimal implementation** (like an auto-fixer).

### Pros

- **High value, low cost** — Tier 1 is pure pattern matching over existing data, no additional API calls
- **Actionable** — each signal includes a concrete recommendation, not just a diagnosis
- **Quantifiable** — cost and latency savings can be estimated from trace data
- **Complements existing features** — natural extension of cost + latency tabs
- **No new dependencies** — rule engine operates on the normalized run JSON already produced

### Cons

- **False positives** — heuristics may flag intentional patterns as inefficiencies
- **Limited without prompt content** — cannot recommend prompt-level optimizations if prompts aren't in traces
- **Tier 2 adds cost** — LLM-powered analysis requires invoking a model, adding to evaluation cost
- **Maintenance burden** — rules need updating as agent frameworks evolve and new patterns emerge
- **Cannot validate recommendations** — tool suggests changes but cannot verify they maintain correctness

### Implementation

| Component | Role |
|-----------|------|
| `agent_eval/evaluators/optimization_signals.py` | Core module — scans normalized run, returns list of `OptimizationSignal` objects |
| `ui/app.py` (new tab) | Renders signals grouped by category with severity, evidence, and recommendations |
| `agent_eval/evaluators/optimization_rules/` | Directory of rule modules (cost_rules.py, latency_rules.py, architecture_rules.py) |

### Implementation Order

1. **Cost signals** — most directly quantifiable, ties into existing cost insights
2. **Latency signals** — parallelization detection from step dependency analysis
3. **Architecture signals** — retry/error pattern detection
4. **Tier 2 LLM analysis** — future phase, after Tier 1 proves value

### Open Questions

1. Should signals be suppressible (user marks a signal as "intentional, ignore")?
2. Should the tool track whether recommendations were acted on across runs (regression/improvement tracking)?
3. For Tier 2, what's the acceptable cost overhead for LLM-powered analysis per evaluation?

---

## ADR-004: Model Recommendation via Replay and Scope Boundaries

**Date**: 2026-05-13
**Status**: Proposed

### Context

Given the tool's trace-based evaluation capabilities, a natural question arises: can the tool recommend the optimal implementation for an agentic solution? This ADR clarifies what is in scope (model recommendation) and what is out of scope (architecture/platform recommendation), and why.

### The Scope Boundary

The tool's core strength is that it is **evidence-based** — every output is grounded in actual execution data. Features remain in scope when they preserve this property.

```
[In Scope]                                              [Out of Scope]
     │                                                        │
Measure ──── Diagnose ──── Suggest ──── Prescribe ──── Implement
     │           │            │              │              │
"Score: 3.8"  "Slow due   "Parallelize   "Rebuild on    "Here's the
              to serial    steps 2-4"    AgentCore      code"
              tool calls"               with 3 agents"
```

- **In scope**: Measure, Diagnose, Suggest — grounded in trace evidence
- **Out of scope**: Prescribe platform/architecture choices, generate implementation code

### Decision: Model Recommendation Is In Scope

Recommending a specific Bedrock model by replaying trace data against multiple models and comparing results is a valid extension of the tool's evaluation capabilities.

**Workflow:**

1. User uploads a trace (known inputs, known expected outputs)
2. Tool identifies model invocation steps
3. Tool replays those steps against N Bedrock models (e.g., Sonnet, Haiku, Llama, Mistral)
4. Tool evaluates each variant with the same judge/rubrics
5. Dashboard shows comparison: quality scores, cost, latency per model
6. Tool recommends the model with the best cost/quality/latency tradeoff

**Why this stays in scope:**

| Criterion | Model Recommendation | Architecture Recommendation |
|-----------|---------------------|----------------------------|
| Can you test it? | ✅ Replay trace against different models | ❌ Can't run alternative architecture from a trace |
| Is the output measurable? | ✅ Same rubrics, same cost/latency metrics | ❌ No ground truth for "better architecture" |
| Is the input unchanged? | ✅ Same prompts, same tool calls | ❌ Different architecture = different execution path |
| Is it grounded in evidence? | ✅ Actual scores from actual runs | ❌ Heuristic reasoning about hypotheticals |

### Decision: Architecture/Platform Recommendations Are Out of Scope

Recommending whether to use Bedrock Agents vs. AgentCore vs. custom orchestration, or suggesting a different agent topology, is **beyond the tool's design scope** because:

1. **Traces show what happened, not what's possible** — cannot infer what alternative architectures would achieve
2. **No way to validate** — can't confirm a recommendation is better without building and running the alternative
3. **Requires knowledge not in the trace** — platform capabilities, constraints, pricing models, team expertise
4. **Generative, not analytical** — design decisions require reasoning beyond measurement

**Acceptable middle ground:** The tool may surface data that *informs* platform decisions without making the decision:
- "Your agent's latency is 80% tool-wait time → AgentCore's async tool execution could help" (informational)
- "Your agent uses 3 sequential model calls → AgentCore's native multi-agent routing handles this pattern" (pattern match)

This keeps the tool in its lane: **evidence + pointers**, not prescriptions.

### Model Replay: Caveats

Replay assumes model invocations are **substitutable** (same prompt in, judge the output). This works for most cases but breaks when:

- Agent behavior depends on a specific model's output format (e.g., tool-use XML vs JSON)
- Downstream steps depend on exact wording from a previous model response (chain dependency)
- The model is fine-tuned or uses features unavailable on other models

**Mitigation:**
- For independent steps (single-turn, no chain dependency): direct replay is clean
- For multi-turn with chain dependencies: requires full agent re-execution (not just model swap), which is a larger scope and may be deferred

### Pros

- **Evidence-based recommendations** — every model suggestion backed by actual evaluation data
- **Leverages existing capabilities** — combines parallel execution (ADR-002) + cost insights (ADR-001) + rubric scoring
- **Clear scope boundary** — prevents feature creep into speculative design tooling
- **Directly actionable** — user gets a concrete answer: "switch to model X, save Y%, maintain quality"

### AWS Prerequisites and Cost Implications

Unlike the tool's other features (cost calculation, latency analysis, rubric scoring) which operate purely on **existing trace data at zero AWS cost**, model replay crosses the line from **analysis** to **active experimentation**. Every replay is a real, billable model invocation.

**Requirements:**
- AWS account with Amazon Bedrock access
- Model access enabled in the Bedrock console for each target model (some require request approval)
- IAM permissions: `bedrock:InvokeModel` for each model being tested
- On-demand inference billing at standard rates

**Cost example:**
A trace with 8 model calls replayed against 5 models = 40 billable Bedrock API invocations. For a mix of Sonnet and Haiku calls, estimated cost: ~$0.05–$0.15 per replay run.

**UX requirement:**
The tool must display a cost estimate and require explicit user confirmation before triggering replay:

> "⚠️ Model replay will invoke 5 models × 8 steps = 40 Bedrock API calls. Estimated cost: ~$0.12. Proceed?"

This is a fundamental shift from the rest of the tool — users who only want trace analysis should never accidentally incur AWS charges. The replay feature should be clearly separated in the UI and gated behind confirmation.

### Cons

- **Replay incurs real AWS cost** — every variant is a billable Bedrock invocation; users must have an AWS account
- **Chain dependency limitation** — full multi-turn replay requires re-running the agent, not just swapping models
- **Model availability** — not all models support the same features (tool use, vision, etc.)
- **Model access gating** — users must manually enable each model in the Bedrock console before replay can use it
- **Temporal validity** — model performance changes over time; recommendations may become stale

### Implementation

| Component | Role |
|-----------|------|
| `agent_eval/evaluators/model_replay.py` | Extracts model invocation steps, replays against target models via Bedrock API |
| `agent_eval/evaluators/model_comparison.py` | Aggregates results across model variants, computes deltas and recommendation |
| `ui/app.py` (new tab) | Model comparison view with cost/quality/latency tradeoff visualization |

### Relationship to Other ADRs

- **ADR-001** (Bedrock Pricing): Provides accurate cost data for each model variant
- **ADR-002** (Parallel Execution + Comparison): Model replay is parallel execution applied to model variants
- **ADR-003** (Optimization Signals): Model right-sizing signals feed into replay candidates

### Open Questions

1. Should replay be opt-in per evaluation, or a separate "Model Profiling" mode?
2. How many models should be tested by default? All available, or a curated shortlist?
3. Should the tool auto-filter models that don't support required features (e.g., tool use)?
4. For chain-dependent traces, should the tool warn and skip, or attempt full re-execution?

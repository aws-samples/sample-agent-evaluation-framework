# Architecture and Security Design

## System Overview

The Agent Evaluation Framework is a trace-driven, offline evaluation tool for agentic AI systems.
It processes pre-recorded execution traces and produces structured evaluation artifacts without
re-running agent runtimes.

```
┌─────────────────────────────────────────────────────────────┐
│                    User / Developer                          │
│              (CLI invocation or CI pipeline)                 │
├─────────────────────────────────────────────────────────────┤
│                   agent_eval CLI                             │
│          (cli.py → pipeline.py orchestration)               │
├──────────┬──────────┬───────────────┬───────────────────────┤
│Normalizer│Evaluators│    Judges     │    Cost/Latency       │
│(adapters)│(metrics) │(rubric-based) │    Insights           │
├──────────┴──────────┴───────────────┴───────────────────────┤
│              Input: Agent Trace Files                        │
│  (JSON/OTel/CloudWatch/AgentCore observability data)        │
├─────────────────────────────────────────────────────────────┤
│              AWS Services (optional)                         │
│  Amazon Bedrock │ CloudWatch │ Pricing API                   │
└─────────────────────────────────────────────────────────────┘
```

## Component Architecture

### Normalizers / Adapters (`agent_eval/adapters/`)
- Parse raw trace formats (JSON, OpenTelemetry, AgentCore) into a canonical schema
- Input validation via JSON schema and Pydantic models

### Evaluators (`agent_eval/evaluators/`)
- **Deterministic metrics**: token counts, turn counts, tool call success rates
- **Cost insights**: per-turn, per-model, per-agent LLM inference cost calculation
- **Latency insights**: TTFT, per-turn latency breakdown, throughput analysis
- **AgentCore cost**: compute vCPU, memory GB, and AgentCore Memory service costs

### Judges (`agent_eval/judges/`)
- Rubric-based LLM evaluation via configurable judge models
- Provider-agnostic: Amazon Bedrock (native), or any LLM via LiteLLM
- Parallel execution across rubrics

### Providers (`agent_eval/providers/`)
- LLM client abstraction (Bedrock, LiteLLM)
- Credential management via boto3 default credential chain

### Tools (`agent_eval/tools/`)
- AgentCore pipeline integration
- OTel structure validation
- Bedrock pricing data retrieval

## Security Design Considerations

### 1. Authentication and Authorization
- All AWS API calls use IAM roles with temporary credentials via boto3 default credential chain
- No hardcoded credentials in source code
- LiteLLM API keys loaded from environment variables only

### 2. Data Protection
- Trace files processed locally; no data transmitted to external services unless LLM judge is configured
- When using external LLM judges, trace evidence is extracted per rubric selector and
  truncated to a 10,000-character budget (5,000 per value) before transmission
- Best-effort PII redaction (email, SSN, and sensitive field-name patterns) runs on
  evidence before it leaves the process
- Evaluation results stored locally as JSON files

### 3. Input Validation
- Trace files validated against JSON schemas before processing
- CLI arguments validated via argparse with type checking
- YAML configuration validated via Pydantic models with field validators
- File paths validated to prevent directory traversal

### 4. Dependency Security
- Dependencies declared with bounded version ranges in `pyproject.toml` (e.g. `>=1.34.0,<2.0.0`)
- No use of `eval()` or dynamic code execution on trace content
- YAML loaded with `yaml.safe_load()` only

### 5. LLM Judge Security
- Judge prompts use static templates with trace evidence wrapped in explicit
  `<UNTRUSTED_EVIDENCE>` delimiters and preceded by instructions to treat the
  content as data for evaluation only — never as instructions to follow
- Output requirements are placed after the evidence block to reduce injection surface
- Output from judges is parsed as structured data, not executed
- Token limits enforced to prevent excessive API costs
- Per-rubric evidence budget (10,000 chars) with per-value truncation (5,000 chars)

## Threat Model

### Trust Boundaries
1. **User → CLI**: Local execution, file system access controlled by OS permissions
2. **CLI → Trace Files**: Untrusted input — validated against schema before processing
3. **CLI → Amazon Bedrock**: IAM authentication, TLS in transit, model access controlled by IAM policy
4. **CLI → External LLM (LiteLLM)**: API key authentication, TLS in transit, data limited to trace excerpts
5. **CLI → CloudWatch/Pricing API**: IAM authentication, read-only access

### Identified Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Malicious trace file with crafted content | Medium | Schema validation, no eval/exec on trace data |
| Prompt injection via trace content sent to judge | Medium | Evidence wrapped in `<UNTRUSTED_EVIDENCE>` delimiters with explicit instruction not to follow content; output contract placed after evidence; per-rubric evidence budget caps payload size |
| Credential exposure in trace files | Medium | Best-effort PII/credential redaction on evidence before egress; traces are read-only input |
| Excessive LLM API costs from large traces | Low | Per-rubric evidence budget (10,000 chars), configurable max turns for evaluation |
| Dependency vulnerability | Low | Bounded version ranges, regular updates recommended |

## AWS Service Security Guidelines

### Amazon Bedrock
- Use IAM policies to restrict `bedrock:InvokeModel` to specific model ARNs
- Monitor usage with CloudWatch metrics and set billing alarms
- Use inference profiles for multi-tenant model access isolation when applicable

### Amazon CloudWatch (for AgentCore cost insights)
- Read-only access via `cloudwatch:GetMetricData`
- Scope IAM policy to specific namespaces and dimensions

### AWS Pricing API
- Read-only access via `pricing:GetProducts`
- No sensitive data involved; used only for public pricing information

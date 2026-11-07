# Testing

> **Status: no automated test suite ships with this sample yet.**
> This directory is a placeholder for the `agent_eval` test package. The
> validation that exists today is a fixture corpus plus a standalone adapter
> verification script (described below). A `pytest` suite is planned but not
> included — running `pytest agent_eval/tests/` currently collects no tests.

This is reference sample code published to `aws-samples`. It intentionally
ships a small, deterministic validation surface rather than a full test suite.

## What actually ships

```
agent_eval/tests/
├── __init__.py    # Test package marker
└── README.md      # This file
```

Validation assets live under `test-fixtures/` at the repo root:

```
test-fixtures/
├── baseline/                     # Deterministic baseline corpus (3 traces)
│   ├── good_001_direct_answer.json      # Single turn, no tools
│   ├── good_002_tool_grounded.json      # Tool used correctly
│   ├── good_003_two_turn_noise.json     # Multi-turn with noise filtering
│   ├── manifest.yaml                    # Trace catalog
│   ├── expected_outcomes.yaml           # Expected metrics per trace
│   └── verify_adapter_format.py         # Adapter-output verification script
├── expected-results/             # Expected normalized outputs
├── judges.mock.yaml              # Mock judge config
├── judges.real.single.yaml       # Single-judge config
├── judges.real.multi.yaml        # Multi-judge config
├── rubrics.alt.yaml              # Alternate rubric definitions
└── malformed_raw_trace.json      # Edge case for error handling
```

## Verifying the adapter today

The baseline corpus has known expected outcomes. To sanity-check the Generic
JSON adapter against them, run the verification script:

```bash
python test-fixtures/baseline/verify_adapter_format.py
```

It asserts that adapter output for the 3-trace corpus matches
`expected_outcomes.yaml` (deterministic metrics, tool counts, latency fields,
turn counts).

## Adding a pytest suite (planned)

If you extend this sample with a real suite, the recommended setup is:

```bash
pip install -e ".[dev]"        # pytest, pytest-cov, hypothesis
pytest agent_eval/tests/ -v
```

`pyproject.toml` already declares `testpaths = ["agent_eval/tests"]` and the
`unit` / `integration` / `property` / `baseline` markers, so new
`test_*.py` files placed here will be collected automatically.

Suggested first tests, in priority order:
1. Adapter normalization against the baseline corpus (wrap the existing
   `verify_adapter_format.py` checks as `pytest` cases).
2. Deterministic metrics and latency bounds (latency must be `>= 0`).
3. Judge-response validation (malformed responses are rejected, not scored).

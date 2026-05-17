---
name: Bug report
about: Something isn't working correctly
title: "[Bug] "
labels: bug
assignees: ''
---

## Describe the bug

A clear description of what went wrong.

## To reproduce

Steps to reproduce the behaviour:

1. Command run: `python run_pipeline.py --n ...`
2. Error observed at step: Node X / output file / dashboard

## Expected behaviour

What you expected to happen.

## Actual behaviour

What actually happened. Include the full error message and traceback.

```
Paste error here
```

## Environment

| Property | Value |
|----------|-------|
| OS | macOS / Linux / Windows |
| Python version | `python --version` |
| Pipeline version | `git rev-parse --short HEAD` |
| pandas version | `python -c "import pandas; print(pandas.__version__)"` |
| google-genai version | `pip show google-genai \| grep Version` |
| Plotly version | `pip show plotly \| grep Version` |

## Logs

Paste relevant lines from `outputs/pipeline.log`:

```
Paste logs here
```

## Additional context

Any other context — screenshot of the dashboard error, relevant section of `run_manifest_*.json`, etc.

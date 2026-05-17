## Summary

<!-- 1–3 bullet points describing what this PR does and why -->

-
-

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor (no behaviour change)
- [ ] Documentation
- [ ] Dependency update
- [ ] Prompt change

## Changes

<!-- List the files changed and briefly explain what changed in each -->

| File | Change |
|------|--------|
| `pipeline/xxx.py` | |
| `dashboard/app.py` | |

## Test plan

- [ ] `python run_pipeline.py --n 3` completes without errors
- [ ] `python -m py_compile pipeline/*.py *.py` passes
- [ ] Dashboard loads without errors: `streamlit run dashboard/app.py`
- [ ] QA audit passes: `python qa_audit.py` (if pipeline output changed)

## Prompt changes (if applicable)

- [ ] QA score before: ___/100 average
- [ ] QA score after:  ___/100 average
- [ ] Sample transcripts tested: ___

## Breaking changes

<!-- Does this change the output schema, CLI flags, or any public API? -->

None / [Describe what breaks and migration path]

## Related issues

Closes #

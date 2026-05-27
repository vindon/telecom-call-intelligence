---
name: new-agent
description: Scaffold a new pipeline agent — creates the agent file, wires it into graph.py, adds a test file, and reminds about tools.py and ARCHITECTURE.md
---

The user wants to add a new agent to the LangGraph pipeline.

Start by asking the user three questions if not already provided:
1. What is the agent name? (e.g. "validation" → creates `validation_agent.py`)
2. What does it do? (one sentence — used for the class docstring and ARCHITECTURE.md entry)
3. What state keys does it consume from `PipelineState`, and what new keys does it produce?

Then follow the 7-step checklist from CLAUDE.md exactly:

**Step 1** — Create `pipeline/agents/{name}_agent.py`:
- Stateless class with a `run(state: dict) -> dict` method
- Return pattern: `return {**state, "new_key": new_value}` — never mutate state in place
- No instance state between calls

**Step 2** — Export from `pipeline/agents/__init__.py`:
- Add the class to the existing import block

**Step 3** — Wire into `pipeline/graph.py`:
- Add a singleton instance at module level
- Register with `graph.add_node("name", instance.run)`
- Add edges — check whether conditional routing is needed based on existing patterns

**Step 4** — Create `tests/test_agents/test_{name}_agent.py`:
- At minimum: one test for happy path, one for missing/empty state, one for edge case
- Mark any test that makes a real Gemini API call with `@pytest.mark.slow`
- Do NOT mock `BudgetGuard`, `QualityGate`, `PIIScanner`, or `AuditLog` — they are fast pure Python

**Step 5** — Register tools in `pipeline/tools.py` if the agent uses any new formal tools

**Step 6** — Add new state keys to `PipelineState` TypedDict in `pipeline/graph.py`

**Step 7** — Update `ARCHITECTURE.md`:
- Add the new node to the architecture diagram
- Add a one-line description in the node table

After completing all steps, run `make test-fast` and report the result.

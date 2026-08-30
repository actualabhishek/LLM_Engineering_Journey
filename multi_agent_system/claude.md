# Multi-Agent Research System

A three-agent research pipeline built with the **openai-agents-sdk**, chaining specialized agents to turn a topic into a polished, structured research report.

## Pipeline

1. **Researcher** — uses a custom **Tavily** web search tool via tool calling to gather factual information on a topic. Strictly fact-only: no analysis or interpretation. Returns a structured `ResearchOutput` (facts + sources).
2. **Analyst** — no tools. Consumes `ResearchOutput` and extracts key trends, risks, and insights in exactly two paragraphs, returned as `AnalystOutput`.
3. **Writer** — no tools. Turns `AnalystOutput` into a polished, well-organized Markdown research report — the final deliverable.

## Key elements

- **Model:** `gpt-5-mini` powers all three agents.
- **Structured data flow:** Pydantic models (`ResearchOutput`, `AnalystOutput`) define clean contracts between agents.
- **Shared memory:** a `SQLiteSession` (in-memory, unique per run) is shared across all three agents so each has visibility into the full conversation.
- **Secrets:** `OPENAI_API_KEY` and `TAVILY_API_KEY` loaded from `.env`.

## Running it

Everything lives in `multi_agents_workflow.ipynb`. Run the notebook top to bottom, then call:

```python
final_report = await manager_run("your topic here")
```

See `hist.md` for the full build history.

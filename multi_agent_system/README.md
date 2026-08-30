# Multi-Agent Research System

I've spent 16+ years living inside enterprise networks — F5 load balancers, Cisco ISE, Nexus fabrics, Palo Alto firewalls. Lately I've been teaching myself to build with LLMs instead of routing packets between them, and this project is one of the first real things I shipped along the way: a small multi-agent pipeline that takes a topic, researches it on the live web, analyzes what it found, and writes up a polished report — hands-off, end to end.

It's built with OpenAI's `openai-agents-sdk`, and it's deliberately simple: three agents, each with one job, talking to each other through typed contracts instead of loose strings.

## What it does

You give it a topic. It hands that topic to a chain of three specialized agents, each strictly scoped to its own job, and comes back with a finished Markdown research report.

```python
final_report = await manager_run("Recent developments in the OpenAI Agents SDK")
```

## The pipeline

**Researcher → Analyst → Writer**

### 1. Researcher
Takes the user's topic and gathers *facts only* — no opinions, no analysis. It's powered by `gpt-5-mini` and uses a custom **Tavily web search tool**, wired in via the SDK's `@function_tool` decorator, to pull live, current information from the web rather than relying on the model's training data alone. Its instructions explicitly forbid it from analyzing, interpreting, or drawing conclusions — that's not its job. It returns a structured `ResearchOutput`: the topic, a list of concise `key_facts`, and the `sources` (title, URL, snippet) each fact came from.

### 2. Analyst
Has **no tools** — it works purely from what the Researcher handed it. It reads the `ResearchOutput` and extracts the trends, risks, and other notable insights hiding in those facts, writing exactly two paragraphs (one on trends, one on risks/insights). It returns `AnalystOutput`: the topic plus that two-paragraph `analysis`.

### 3. Writer
Also has **no tools**. It takes the Analyst's `AnalystOutput` and turns it into a genuinely polished, well-organized Markdown research report — title, introduction, clearly labeled sections (Overview, Key Trends, Risks & Insights, Conclusion). Since this is the final human-facing deliverable and nothing downstream needs to parse it further, it returns plain text rather than a structured Pydantic type.

## How the agents talk to each other

Two things keep this pipeline from turning into a game of telephone:

- **Pydantic contracts.** Every handoff between agents is a typed model, not a raw string. `ResearchOutput` and `AnalystOutput` define exactly what one agent promises to hand the next, so each agent gets clean, predictable input instead of having to parse free text.
- **Shared memory via `SQLiteSession`.** Each call to `manager_run()` creates one fresh, in-memory `SQLiteSession` and passes it into all three `Runner.run()` calls. That means every agent in the chain has visibility into the full conversation so far — not just the explicit output it was handed — without me having to manually thread history through the pipeline myself.

## Tech stack

- **[openai-agents-sdk](https://github.com/openai/openai-agents-python)** — agent definitions, tool calling, structured output, sessions, orchestration
- **`gpt-5-mini`** — the model behind all three agents
- **[Tavily](https://tavily.com/)** — real-time web search, wrapped as a custom tool
- **Pydantic** — structured data contracts between agents
- **`SQLiteSession`** — shared conversation memory across the pipeline
- **Jupyter + a Python `venv`** — the whole thing lives and runs in one notebook

## Project structure

```
mlti_agent_system/
├── multi_agents_workflow.ipynb   # the whole project — tool, agents, pipeline, all runnable top to bottom
├── .env                          # OPENAI_API_KEY, TAVILY_API_KEY (never committed)
├── .gitignore                    # excludes .env, __pycache__/, *.pyc, venv/, .venv/
├── requirements.txt              # pinned dependencies (pip freeze)
├── claude.md                     # short (<200 word) project overview
├── hist.md                       # running build log — one line per step, as the project was built
├── Prompt.md                     # every prompt used to build this, logged as I went
└── README.md                     # you are here
```

## Setup

1. **Create and activate a virtual environment** inside the project folder:
   ```bash
   python -m venv .venv
   ```
2. **Install dependencies:**
   ```bash
   .venv\Scripts\pip install -r requirements.txt
   ```
3. **Register the venv as a Jupyter kernel** so it's selectable from a notebook:
   ```bash
   .venv\Scripts\python -m ipykernel install --user --name=multi_agent_system --display-name="Python (multi_agent_system)"
   ```
4. **Add your API keys** to `.env` in the project root:
   ```
   OPENAI_API_KEY=your_openai_api_key_here
   TAVILY_API_KEY=your_tavily_api_key_here
   ```

## Running it

Open `multi_agents_workflow.ipynb` in VS Code, select the **"Python (multi_agent_system)"** kernel, and run the cells top to bottom — each tool and agent is demoed individually before the full pipeline is wired together at the end.

To run the whole pipeline yourself, once the notebook's defined everything:

```python
final_report = await manager_run("your topic here")
display(Markdown(final_report))
```

## Build history

This was built incrementally, one deliberate step at a time — environment, tool, then each agent, then the orchestration. The full sequence is tracked in [`hist.md`](hist.md).

---

Part of the `llm-engineering-journey` portfolio — documenting a hands-on transition from 16+ years of enterprise network engineering into AI/ML engineering.

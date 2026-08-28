# Autogen Agent

Two hands-on experiments in this folder, both built with [AutoGen](https://microsoft.github.io/autogen/) — Microsoft's framework for coordinating a team of LLM agents instead of leaning on one big prompt. I wanted to understand multi-agent orchestration from the inside, so I built two different shapes of it: one exploring multi-provider teamwork, one exploring self-checking RAG.

## 1. Multi-Model Team with AutoGen

A demo of a multi-agent "team" where each agent runs on a **different LLM provider** and plays a distinct role in a marketing brainstorm.

The notebook ([`MultiModelTeamWithAutogen.ipynb`](./MultiModelTeamWithAutogen.ipynb)) sets up a group chat for a fictional smart-home cybersecurity brand launch, with three specialist agents and a human-proxy agent working out a go-to-market plan:

- **CISO Agent** (OpenAI GPT-4o-mini) — sets strategy, defines the target audience, opens the discussion.
- **Product Marketer Agent** (Gemini 2.5 Flash Lite, via OpenRouter) — proposes campaign tactics, creative ideas, KPIs.
- **Social Media Manager Agent** (Anthropic Claude) — turns strategy and tactics into platform-specific content plans (channels, formats, cadence).
- **User Proxy Agent** — stands in for the human in the loop and can end the conversation.

AutoGen's `GroupChat` and `GroupChatManager` handle round-robin turn-taking. Each agent stays in character through a dedicated system prompt with explicit boundaries ("this is not your job"), and the whole conversation renders as Markdown right in the notebook.

**Why multi-model?** Instead of running every agent on the same model, I deliberately assigned each role a different provider — OpenAI, Gemini, Claude — to see how AutoGen handles a genuinely heterogeneous team. Useful for comparing how different models play the same role, controlling cost per role, or just not betting the whole pipeline on one vendor.

## 2. NetSOP-RAG + AutoGen

The self-correcting RAG idea from my [LangGraph project](../LangGraph%20Agent) rebuilt as a multi-agent conversation instead of a single graph — same problem, different shape, so I could feel out which pattern actually fits better.

The notebook ([`NetSOP-RAG + AutoGen.ipynb`](./NetSOP-RAG%20+%20AutoGen.ipynb)) answers engineer questions — *"What's the rollback procedure if the F5 BIG-IP upgrade fails?"* — using only the content of my TCS network SOPs (F5 BIG-IP, Cisco Nexus, VLAN/trunk, BGP troubleshooting). Instead of one LLM call, the question runs through a small team where each agent owns one job:

- **Retriever_Agent** — turns the question into a search query and calls a retrieval tool over the vector store. Doesn't answer anything itself.
- **Answer_Agent** — answers strictly from retrieved SOP context: exact command syntax, exact step order, pass/fail criteria, rollback steps. Refuses to guess if the context doesn't cover it.
- **Critic_Agent** — grades that answer against the retrieved context (grounded? right order? citations included?) and only signs off `APPROVED` once every check passes — otherwise it goes back for revision.
- **Tool_Executor** — a `UserProxyAgent` that actually runs the retrieval call and ends the conversation once `Critic_Agent` approves.

These four sit in a round-robin `GroupChat`, so retrieval, drafting, and fact-checking happen as separate turns instead of collapsing into one prompt.

**Why this shape:** SOP content is exactly where a normal RAG chain gets risky — a hallucinated command or a reordered upgrade step isn't a stylistic nitpick, it's an outage. Splitting the job across a Retriever, an Answer writer, and a Critic that has to approve before anything ships adds a self-checking step a single-shot chain doesn't have. A custom `.docx` loader (`docx_markdown_loader.py`) also preserves tables as Markdown, so a command and its expected result don't get split apart during chunking.

**Pipeline:** load `TCS_Network_KB_SOPs.docx` → convert to Markdown (headings and tables intact) → chunk along heading/paragraph boundaries → embed with OpenAI embeddings into a persistent Chroma store → wrap similarity search in a `retrieve_context_tool` → run the question through `Retriever_Agent → Answer_Agent → Critic_Agent → Tool_Executor` and return the approved answer.

## Requirements

- Python packages: `pyautogen`, `openai`, `google-generativeai`, `anthropic`, `langchain-openai`, `langchain-text-splitters`, `langchain-chroma`, `python-docx`, `python-dotenv`, `gradio`
- A `.env` file with:
  - `OPENAI_API_KEY`
  - `OPENROUTER_API_KEY`
  - `ANTHROPIC_API_KEY`
- `TCS_Network_KB_SOPs.docx` in this folder (needed for the NetSOP-RAG notebook)

## Running it

Open either notebook in Jupyter and run the cells top to bottom. The final cells trigger the group conversation and print out each agent's contribution.

---

Part of my [LLM Engineering journey](../) — hands-on exploration of multi-agent orchestration and how to get LLM agents from different providers, or with different jobs, to actually check each other's work instead of just taking turns talking.

Still learning, still building.

# Multi-Model Team with AutoGen

A demo of a multi-agent AI "team" built with [AutoGen](https://microsoft.github.io/autogen/), where each agent is powered by a **different LLM provider** and plays a distinct role in a marketing brainstorm.

## What it does

The notebook (`MultiModelTeamWithAutogen.ipynb`) sets up a group chat for a fictional smart-home cybersecurity brand launch, with three specialist agents and a human-proxy agent collaborating to produce a go-to-market plan:

- **CISO Agent** (OpenAI GPT-4o-mini) — sets strategy, defines the target audience, and opens the discussion.
- **Product Marketer Agent** (Gemini 2.5 Flash Lite, via OpenRouter) — proposes campaign tactics, creative ideas, and KPIs.
- **Social Media Manager Agent** (Anthropic Claude) — turns the strategy and tactics into platform-specific content plans (channels, formats, cadence).
- **User Proxy Agent** — stands in for the human in the loop and can end the conversation.

AutoGen's `GroupChat` and `GroupChatManager` coordinate turn-taking (round-robin) between the agents, each agent stays in character via a dedicated system prompt with explicit boundaries ("this is not your job"), and the resulting conversation is rendered as Markdown in the notebook.

## Why multi-model?

Instead of running every agent on the same model, each role is deliberately assigned a different provider (OpenAI, Google Gemini, Anthropic Claude) to explore how AutoGen can orchestrate a heterogeneous team — useful for comparing model behavior, controlling cost per role, or simply avoiding a single vendor dependency.

## Requirements

- Python packages: `pyautogen`, `openai`, `google-generativeai`, `anthropic`, `python-dotenv`
- A `.env` file with:
  - `OPENAI_API_KEY`
  - `OPENROUTER_API_KEY`
  - `ANTHROPIC_API_KEY`

## Running it

Open `MultiModelTeamWithAutogen.ipynb` in Jupyter and run the cells top to bottom. The final cells trigger the group conversation and print out each agent's contribution.

---

Part of the llm-engineering-journey portfolio — hands-on exploration of multi-agent orchestration frameworks and how to coordinate LLM agents from different providers toward a shared task.

Step 1 : Created a Python virtual environment (venv) in the project folder and registered it as a Jupyter kernel
Step 2 : Installed required packages (openai-agents, python-dotenv, ipykernel, etc.)
Step 3 : Created the multi_agents_workflow.ipynb notebook
Step 4 : Built a custom Tavily web search tool for use with the openai-agents-sdk
Step 5 : Built the "Researcher" agent, powered by gpt-5-mini, using the Tavily tool via tool calling, with Pydantic models defining its input/output for data flow to future agents
Step 6 : Built the "Analyst" agent, powered by gpt-5-mini, with no tools, consuming the Researcher's output and producing a 2-paragraph trends/risks/insights analysis via a new AnalystOutput Pydantic model
Step 7 : Built the "Writer" agent and manager_run(user_query), chaining Researcher -> Analyst -> Writer with a shared SQLiteSession per run; notebook is now runnable end-to-end
Step 8 : Created claude.md with a concise, under-200-word project overview covering the pipeline, tech stack, and how to run it
Step 9 : Created a comprehensive README.md in brand voice, covering the full pipeline, tech stack, data flow, setup, and usage, ending with the llm-engineering-journey portfolio tagline

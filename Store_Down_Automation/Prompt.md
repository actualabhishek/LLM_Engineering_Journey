# Prompt Log (redacted for portfolio — company name, employee names, emails, URLs, and IDs replaced with placeholders)

Context: I'm a network engineer transitioning into AI/LLM engineering. I want to build a phase-wise multi-agent automation system that handles "No ping reply" store-down incidents end-to-end: detecting the incident in the ticketing system, researching the store contact via an internal directory site, emailing the store manager and regional lead through the company's email platform, updating the ticket, and logging the outcome in Airtable.

Instruction: Design and write a complete, phase-wise implementation plan for this multi-agent system, to be built using Claude Code. Specifically:
1. Propose the overall multi-agent architecture (how many agents, what each owns, how they hand off work to each other).
2. Suggest the best trigger mechanism for kicking off the workflow, and justify the choice given all three internal systems are accessed via browser automation only.
3. Suggest whether a coordinator agent is needed to orchestrate hand-offs, and define its responsibilities if so.
4. Suggest a clear, role-appropriate name for each agent.
5. Specify how each agent uses browser automation to interact with the ticketing system, the directory site, and the email platform.
6. Define every inter-agent hand-off as a typed Pydantic model, so each agent validates its input/output against a schema rather than passing free-text.
7. Lay out the plan in build phases, with what to build and validate at each phase before moving to the next.
8. Where a networking analogy would clarify a concept, use one.
Do not start building code yet — produce the plan first.

Input: a detailed description of the four-agent workflow (incident watcher, store lookup, email composer, logger), the exact notification email subject/body template, and the instruction that all inter-agent data must be Pydantic-validated, not raw strings or dicts.

---

Use these agent names: Agent 1 (incident_watcher), Agent 2 (store_lookup), Agent 3 (email_composer), Agent 4 (logger). Also create a PLAN.md in the project root with everything in it, a hist folder with a hist.md file tracking every build iteration with a date/time stamp, and a PROMPT.md logging every prompt I give you, separated by a blank line, a dash line, and a blank line.

---

One thing to note: the directory site will provide the name of the store manager or regional lead, but the agent will have to look those names up separately to find their email IDs.

---

Please note: I don't have admin access to the ticketing system, and I don't have access to any API — so don't suggest something we can't implement. Also, if an incident isn't in New or In Progress state, I think no action is required.

---

You can start the email agent, but do not send any email to any person — not even for testing.

---

Make sure the email platform is using my correct work account for sending/composing email.

---

One thing I want to highlight: the email recipients should always include the store's shared mailbox alongside the store manager and regional lead — and the email subject should include the incident number, store code, and store name.

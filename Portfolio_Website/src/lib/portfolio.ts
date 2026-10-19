export const profile = {
  name: "Abhishek Suman",
  role: "Senior Network Engineer & GenAI/LLM Engineering Specialist",
  location: "Asansol, India",
  email: "abhishek.suman4u@gmail.com",
  linkedin: "https://www.linkedin.com/in/abhishek-suman-8919b338",
  github: "https://github.com/actualabhishek/LLM_Engineering_Journey",
  summary:
    "Senior Network Engineer with 16+ years of enterprise IT experience, building the transition into full-time GenAI/LLM Engineering through production-minded automation, RAG systems, and agentic workflows.",
} as const;

export const facts = [
  { value: "16+", label: "years in enterprise IT" },
  { value: "5", label: "employers, TCS since 2021" },
  { value: "15", label: "projects listed below" },
] as const;

export const capabilities = [
  { label: "GenAI / LLM", value: "Claude, OpenAI, LangChain, LangGraph, MCP" },
  { label: "RAG and agents", value: "Chroma, AutoGen, CrewAI, OpenAI Agents SDK" },
  { label: "Open models", value: "Transformers, PyTorch, LoRA / QLoRA, quantization" },
  { label: "Network systems", value: "BGP, OSPF, SD-WAN, Cisco Nexus, F5 BIG-IP" },
] as const;

export type Category = "Network operations" | "RAG and agents" | "Applications" | "Model work";
export type Method = "Claude Code" | "Independent";

export type Project = {
  name: string;
  category: Category;
  method?: Method;
  summary: string;
  tags: readonly string[];
  question: string;
};

export const categories: readonly Category[] = ["Network operations", "RAG and agents", "Applications", "Model work"];

export const projects: readonly Project[] = [
  {
    name: "Router_Reachability_Monitor",
    category: "Network operations",
    method: "Claude Code",
    summary: "Reachability monitoring for two internet edge routers. A canary check keeps a local outage from being read as a router outage; alerts go out over Telegram, voice, WhatsApp and ntfy.",
    tags: ["ICMP/TCP", "State machine", "Docker", "Tailscale"],
    question: "How does Router_Reachability_Monitor tell a router outage from a local one?",
  },
  {
    name: "Store_Down_Automation",
    category: "Network operations",
    method: "Claude Code",
    summary: "A NOC runbook automated end to end: four scoped subagents and a deterministic coordinator, typed hand-offs, and a supervised send-gate before anything leaves the building.",
    tags: ["Subagents", "Pydantic", "Browser automation", "Airtable"],
    question: "Walk me through Store_Down_Automation and the debugging stories in it.",
  },
  {
    name: "NetOps_Flow_Kanban",
    category: "Network operations",
    method: "Claude Code",
    summary: "A Kanban board for change requests, incidents and CAB windows. The AI sidebar creates, edits and moves cards through a validated JSON action list.",
    tags: ["FastAPI", "Next.js", "SQLite", "Docker"],
    question: "What bugs did you find while building NetOps_Flow_Kanban?",
  },
  {
    name: "CiscoConfigDiffAuditor",
    category: "Network operations",
    method: "Independent",
    summary: "A block-aware diff for Cisco IOS configs that flags security-relevant changes such as ACLs, shutdown, line vty and enable secret.",
    tags: ["Cisco IOS", "Security", "LLM"],
    question: "How does CiscoConfigDiffAuditor work?",
  },
  {
    name: "Network_KB_RAG_Claude",
    category: "RAG and agents",
    method: "Claude Code",
    summary: "The LangGraph retrieval notebook grown into an app: Haiku grades retrieval, Opus answers, Haiku checks groundedness, with a retry loop and streaming UI. Tested on my own network SOPs.",
    tags: ["Claude", "Chroma", "LangGraph", "Gradio"],
    question: "How does Network_KB_RAG_Claude check its own answers?",
  },
  {
    name: "LangGraph Agent",
    category: "RAG and agents",
    method: "Independent",
    summary: "A self-correcting RAG pipeline over network SOPs that grades its own retrieval and retries on weak matches.",
    tags: ["LangGraph", "Chroma", "Evaluation"],
    question: "Explain the self-correcting retrieval agent you built in LangGraph.",
  },
  {
    name: "multi_agent_system",
    category: "RAG and agents",
    method: "Independent",
    summary: "A Researcher, Analyst and Writer pipeline on the OpenAI Agents SDK, with Tavily tool calling, Pydantic contracts between agents and a shared SQLiteSession.",
    tags: ["OpenAI Agents SDK", "Tavily", "Pydantic"],
    question: "How do the agents in multi_agent_system hand work to each other?",
  },
  {
    name: "Autogen Agent",
    category: "RAG and agents",
    method: "Independent",
    summary: "An AutoGen team in which OpenAI, Gemini and Claude each play a distinct role in one group chat.",
    tags: ["AutoGen", "OpenAI", "Gemini", "Claude"],
    question: "What does the AutoGen multi-provider team do?",
  },
  {
    name: "Hotel_Experience_Assistant",
    category: "Applications",
    method: "Claude Code",
    summary: "A bilingual English/Hindi voice concierge. Every data-changing action is proposed first and runs only after the guest confirms; speech runs on a Modal GPU worker.",
    tags: ["Tool calling", "Modal", "FastAPI", "Playwright"],
    question: "Tell me about Hotel_Experience_Assistant and the bugs you found.",
  },
  {
    name: "AI_Forex_Bot",
    category: "Applications",
    method: "Claude Code",
    summary: "An MT5 trading system where deterministic analysis does the work and an LLM is called only on ambiguous signals, with a hard cap on its influence and a multi-layer risk engine.",
    tags: ["MT5", "Risk engine", "Streamlit", "Webhooks"],
    question: "What did the gold backtest in AI_Forex_Bot teach you?",
  },
  {
    name: "LinkedIn_Post_Automation",
    category: "Applications",
    method: "Claude Code",
    summary: "A Claude Code plugin that takes a Telegram message through research, a draft in my voice, an image, an approval step and publishing.",
    tags: ["Claude Code plugin", "Telegram", "Airtable", "Playwright"],
    question: "How does LinkedIn_Post_Automation keep me in control of what gets published?",
  },
  {
    name: "ResumeRocket AI",
    category: "Applications",
    summary: "Resume tailoring from a job description: gap analysis, rewrite, visual diff and cover letter.",
    tags: ["LLM", "Gradio"],
    question: "What does ResumeRocket AI do?",
  },
  {
    name: "Portfolio_Website",
    category: "Applications",
    method: "Claude Code",
    summary: "This site and its Digital Twin: a server-side route grounded in a condensed context file, with a safety pass and rate limiting.",
    tags: ["Next.js", "OpenRouter", "Cerebras"],
    question: "How is this Digital Twin built, and how does it resist prompt injection?",
  },
  {
    name: "Fine_Tuning",
    category: "Model work",
    method: "Independent",
    summary: "QLoRA on TinyLlama and Gemma, compared against the frozen base model using peft's disable_adapter() to see exactly what the fine-tune changed.",
    tags: ["QLoRA", "peft", "trl"],
    question: "What did you learn from the QLoRA fine-tuning experiments?",
  },
  {
    name: "Claude Skills for network operations",
    category: "Network operations",
    summary: "incident-rca-writer turns incident notes into review-ready RCA documents; network-capture-analyst triages packet captures with tshark.",
    tags: ["Claude Skills", "RCA", "tshark"],
    question: "What do your incident-rca-writer and network-capture-analyst skills do?",
  },
];

export const experience = [
  { period: "2021 to now", role: "Senior Network Engineer & AI Automation Lead", company: "Tata Consultancy Services", note: "Network operations automation, enterprise infrastructure, and applied LLM workflows." },
  { period: "2019 to 2021", role: "Senior Consultant", company: "Atos-Syntel", note: "Global Cisco Unified Communications support and complex incident resolution." },
  { period: "2017 to 2019", role: "Technical Lead", company: "Wipro", note: "Enterprise voice platform delivery, migration, and relocation programs." },
  { period: "2010 to 2017", role: "Associate Consultant / Senior Specialist", company: "Atos & HCL Technologies", note: "Cisco unified communications administration, troubleshooting, and operations." },
] as const;

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

export const capabilities = [
  { label: "GenAI / LLM", value: "Claude, OpenAI, LangChain, LangGraph, MCP" },
  { label: "RAG & agents", value: "Chroma, AutoGen, CrewAI, OpenAI Agents SDK" },
  { label: "Open models", value: "Transformers, PyTorch, LoRA / QLoRA, quantization" },
  { label: "Network systems", value: "BGP, OSPF, SD-WAN, Cisco Nexus, F5 BIG-IP" },
] as const;

export const projects = [
  {
    name: "Network operations Claude Skills",
    kind: "Operational automation",
    description:
      "incident-rca-writer converts incident records into review-ready RCA documents; network-capture-analyst automates packet-capture triage, anomaly detection, and stream reconstruction.",
    tags: ["Claude Skills", "RCA", "tshark", "Network ops"],
  },
  {
    name: "Network SOP retrieval assistants",
    kind: "RAG systems",
    description:
      "Built SOP lookup and PDF RAG applications using LangChain, Chroma, AutoGen agents, Claude, and groundedness evaluation.",
    tags: ["RAG", "Chroma", "AutoGen", "Gradio"],
  },
  {
    name: "Self-correcting retrieval agent",
    kind: "Agentic AI",
    description:
      "A LangGraph retrieval workflow with grading and automatic retry logic to recover from low-quality retrieval before answering.",
    tags: ["LangGraph", "RAG", "Evaluation"],
  },
  {
    name: "CiscoConfigDiffAuditor",
    kind: "LLM-assisted auditing",
    description:
      "A block-aware Cisco IOS configuration diff viewer designed to surface security-relevant drift between versions.",
    tags: ["Cisco IOS", "Security", "LLM"],
  },
] as const;

export const experience = [
  { period: "2021 — present", role: "Senior Network Engineer & AI Automation Lead", company: "Tata Consultancy Services", note: "Network operations automation, enterprise infrastructure, and applied LLM workflows." },
  { period: "2019 — 2021", role: "Senior Consultant", company: "Atos-Syntel", note: "Global Cisco Unified Communications support and complex incident resolution." },
  { period: "2017 — 2019", role: "Technical Lead", company: "Wipro", note: "Enterprise voice platform delivery, migration, and relocation programs." },
  { period: "2010 — 2017", role: "Associate Consultant / Senior Specialist", company: "Atos & HCL Technologies", note: "Cisco unified communications administration, troubleshooting, and operations." },
] as const;

# 🚀 ResumeRocket AI

An end-to-end, AI-powered resume tailoring pipeline. Upload a resume and a target job description, and ResumeRocket AI rewrites the resume to fit the role, explains exactly what changed, and drafts a matching cover letter — all through a simple web interface.

Part of the [`llm-engineering-journey`](../) portfolio, documenting a hands-on transition from 16+ years of enterprise network engineering into AI/ML engineering.

## What it does

Given a resume (PDF) and a job description (pasted text), the app runs a four-stage LLM pipeline:

1. **Gap analysis** — compares the resume against the job description and produces a structured breakdown: key requirements, matching experience, gaps/mismatches, and hidden strengths worth highlighting.
2. **Tailored resume rewrite** — rewrites the full resume to close those gaps, add relevant keywords, and quantify achievements, while keeping the original section structure intact.
3. **Change diff** — an HTML diff view showing every addition (green) and removal (red, struck-through), so nothing is a black box.
4. **Cover letter** — a four-paragraph-or-fewer cover letter generated from the tailored resume and job description.

The tailored resume is also exported as a downloadable PDF.

## How it's built

- **UI:** [Gradio](https://www.gradio.dev/) `Blocks` interface with tabs for Gap Analysis, Updated Resume, Diff, and Cover Letter.
- **LLM calls:** OpenAI's API, using [structured outputs via Pydantic](https://platform.openai.com/docs/guides/structured-outputs) (`beta.chat.completions.parse`) so the model returns exactly the fields the app needs — no fragile prompt-and-hope-for-JSON parsing.
- **Resume parsing:** [`pdfplumber`](https://github.com/jsvine/pdfplumber) extracts text from the uploaded PDF.
- **PDF generation:** [`fpdf2`](https://py-pdf.github.io/fpdf2/) renders the tailored resume back out as a clean, downloadable PDF.

### Pipeline at a glance

```
Resume PDF ──▶ extract_text_from_pdf ──┐
                                        ├──▶ analyse_resume_against_job_description ──▶ Gap Analysis
Job Description ────────────────────────┘                    │
                                                               ▼
                                                        resume_generate ──▶ Updated Resume + Diff
                                                               │
                                                               ├──▶ build_resume_pdf ──▶ Downloadable PDF
                                                               └──▶ generate_cover_letter ──▶ Cover Letter
```

## Getting started

```bash
pip install gradio openai pdfplumber fpdf2 python-dotenv pydantic
```

Create a `.env` file in this folder with your OpenAI key:

```
OPENAI_API_KEY=your-key-here
```

Then open `ResumeRocket AI.ipynb` and run all cells. Gradio will launch a local URL where you can upload a resume and paste a job description.

## Engineering notes

A few real bugs surfaced and fixed while building this, worth keeping as a reference:

- **Silent error swallowing:** the low-level `llm_generate` wrapper caught *all* exceptions and returned them as plain strings — fine for free-text calls, but it broke the type contract for structured calls (callers expected a Pydantic object back, e.g. `result.updated_resume`). A failed API call surfaced two functions later as a confusing `AttributeError` instead of the real cause. Fixed by re-raising structured-call failures with the actual error message, and wrapping the pipeline entry point in a try/except that surfaces errors directly in the UI.
- **PDF cursor bug:** `fpdf2`'s `multi_cell(w=0, ...)` defaults to leaving the text cursor at the *right* margin after each call. Since `w=0` means "auto-fill to the right margin," the next line's available width computed to zero — crashing with `Not enough horizontal space to render a single character` on the second line of any resume. Fixed by explicitly resetting the cursor to the left margin after each line.
- **Unicode vs. core fonts:** `fpdf2`'s built-in Helvetica font only supports strict Latin-1, but LLM-generated text routinely includes "smart" punctuation (em dashes, curly quotes, ellipses, bullets) outside that range. Fixed with a sanitize step that maps common smart characters to ASCII equivalents and drops anything else that still wouldn't render, rather than crashing PDF export.

## Roadmap ideas

- Support `.docx` resume uploads in addition to PDF.
- Let users pick between OpenAI and Anthropic models per run (an Anthropic-compatible client is already wired up).
- Multi-page PDF styling (fonts, spacing, optional templates).

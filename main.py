"""
main.py — CLI entrypoint for the RAG pipeline.

Usage:
  # First, ingest your documents:
  python ingest.py path/to/TCS_Network_KB_SOPs.docx

  # Then ask questions:
  python main.py "What is the escalation procedure for P1 network incidents?"
  python main.py --interactive
"""

import argparse
import json
import logging
import sys

from graph import compile_graph
from state import RAGState
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def run_query(question: str, verbose: bool = False) -> dict:
    """Run a single question through the RAG pipeline and return the final state."""
    if not verbose:
        # Suppress INFO from internal nodes for cleaner interactive use
        logging.getLogger("nodes").setLevel(logging.WARNING)
        logging.getLogger("graph").setLevel(logging.WARNING)

    app = compile_graph()

    initial_state: RAGState = {
        "question": question,
        "rewritten_query": "",
        "retrieved_docs": [],
        "graded_docs": [],
        "generation": "",
        "evaluation": None,
        "retry_count": 0,
        "final_answer": "",
        "sources": [],
    }

    log.info("Running pipeline for: %r", question)
    final_state = app.invoke(initial_state)
    return final_state


def print_result(state: dict) -> None:
    print("\n" + "=" * 70)
    print("ANSWER")
    print("=" * 70)
    print(state.get("final_answer", "No answer produced."))

    sources = state.get("sources", [])
    if sources:
        print("\n" + "-" * 70)
        print("SOURCES")
        print("-" * 70)
        for s in sources:
            print(f"  • {s['source']}  |  {s['section_heading']}")

    eval_result = state.get("evaluation")
    if eval_result:
        verdict = eval_result.get("verdict", "N/A")
        retries = state.get("retry_count", 0)
        print(f"\n[Quality check: {verdict}  |  retries: {retries}/{config.MAX_RETRIES}]")
    print("=" * 70 + "\n")


def interactive_mode() -> None:
    print("RAG Pipeline — Interactive Mode")
    print(f"Model: {config.GENERATOR_MODEL}  |  Grader: {config.GRADER_MODEL}  |  top_k: {config.TOP_K}")
    print("Type 'exit' or 'quit' to stop.\n")

    app = compile_graph()

    while True:
        try:
            question = input("Question: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break

        initial_state: RAGState = {
            "question": question,
            "rewritten_query": "",
            "retrieved_docs": [],
            "graded_docs": [],
            "generation": "",
            "evaluation": None,
            "retry_count": 0,
            "final_answer": "",
            "sources": [],
        }

        try:
            state = app.invoke(initial_state)
            print_result(state)
        except Exception as exc:
            print(f"Error: {exc}")
            log.exception("Pipeline error")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RAG Pipeline powered by LangGraph + Claude"
    )
    parser.add_argument("question", nargs="?", help="Question to answer")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive Q&A mode")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show full node logs")
    parser.add_argument("--json", action="store_true", help="Output final state as JSON")
    args = parser.parse_args()

    if args.interactive:
        interactive_mode()
        return

    if not args.question:
        parser.print_help()
        sys.exit(1)

    state = run_query(args.question, verbose=args.verbose)

    if args.json:
        # Documents aren't JSON-serializable; strip them
        out = {k: v for k, v in state.items() if k not in ("retrieved_docs", "graded_docs")}
        print(json.dumps(out, indent=2, default=str))
    else:
        print_result(state)


if __name__ == "__main__":
    main()

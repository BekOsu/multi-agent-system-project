"""Writes generated code artifacts to the output/ directory."""

from pathlib import Path

from state import AgentState
from security.guardrails import human_review_gate, require_human_review, sandbox_file_path

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def write_artifacts(state: AgentState) -> None:
    """Write all generated code and the validation report to output/."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Security: scan for risky patterns before writing
    all_code = {**state.get("fe_code", {}), **state.get("be_code", {})}
    warnings = human_review_gate(all_code)
    if warnings:
        for w in warnings:
            print(w)
        if require_human_review():
            print("\n[security] REQUIRE_HUMAN_REVIEW=true — pausing before write.")
            print(f"  {len(warnings)} warning(s) found. Review above, then press Enter to continue.")
            input("  Press Enter to proceed or Ctrl+C to abort: ")

    # Write frontend code
    fe_dir = OUTPUT_DIR / "frontend"
    for filepath, code in state.get("fe_code", {}).items():
        dest = sandbox_file_path(f"frontend/{filepath}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(code)

    # Write backend code
    be_dir = OUTPUT_DIR / "backend"
    for filepath, code in state.get("be_code", {}).items():
        dest = sandbox_file_path(f"backend/{filepath}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(code)

    # Write spec
    if state.get("spec"):
        sandbox_file_path("SPEC.md").write_text(state["spec"])

    # Write validation report
    report = state.get("validation_report", "No validation run.")
    passed = state.get("validation_passed", False)
    header = "# Validation Report\n\n"
    header += f"**Status:** {'PASSED' if passed else 'FAILED'}\n\n"
    sandbox_file_path("VALIDATION_REPORT.md").write_text(header + report)

    print(f"\n[file_writer] Artifacts written to {OUTPUT_DIR.resolve()}")
    print(f"  Frontend files: {len(state.get('fe_code', {}))}")
    print(f"  Backend files:  {len(state.get('be_code', {}))}")
    print(f"  Validation:     {'PASSED' if passed else 'FAILED'}")
    if warnings:
        print(f"  Security warnings: {len(warnings)}")

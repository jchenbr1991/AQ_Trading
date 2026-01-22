#!/usr/bin/env python3
"""
AQ Decision Council CLI

A structured decision-making tool that consults multiple AI agents
with different perspectives before you make a final verdict.

Usage:
    python aq_decision.py new <decision_id>
    python aq_decision.py council <decision_id>
    python aq_decision.py decide <decision_id>
    python aq_decision.py status <decision_id>
    python aq_decision.py list
"""

import argparse
import asyncio
import subprocess
import sys
import os
import yaml
import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Optional


# Configuration
DECISIONS_DIR = Path(__file__).parent.parent / "decisions"
PROMPTS_DIR = Path(__file__).parent / "prompts"

# Agent configuration: role -> (cli_command, model_hint)
AGENTS = {
    "skeptic": ("codex", "Catastrophic failure analysis"),
    "minimalist": ("codex", "Scope challenge"),
    "operator": ("codex", "Implementation reality"),
    "quant": ("codex", "Statistical risk"),
    "historian": ("codex", "Historical patterns"),
}


@dataclass
class Decision:
    id: str
    title: str
    options: dict[str, str]
    constraints: list[str]
    stop_rule: dict

    @classmethod
    def load(cls, decision_id: str) -> "Decision":
        path = DECISIONS_DIR / decision_id / "decision.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Decision not found: {decision_id}")
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def save(self):
        path = DECISIONS_DIR / self.id / "decision.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump({
                "id": self.id,
                "title": self.title,
                "options": self.options,
                "constraints": self.constraints,
                "stop_rule": self.stop_rule,
            }, f, allow_unicode=True, default_flow_style=False)


def cmd_new(args):
    """Create a new decision."""
    decision_id = args.decision_id
    decision_dir = DECISIONS_DIR / decision_id

    if decision_dir.exists():
        print(f"Error: Decision '{decision_id}' already exists.")
        sys.exit(1)

    print(f"Creating new decision: {decision_id}\n")

    # Interactive input
    title = input("Decision title: ").strip()
    if not title:
        print("Error: Title is required.")
        sys.exit(1)

    print("\nOption A (current/default approach):")
    option_a = input("> ").strip()

    print("\nOption B (alternative approach):")
    option_b = input("> ").strip()

    print("\nConstraints (one per line, empty line to finish):")
    constraints = []
    while True:
        constraint = input("> ").strip()
        if not constraint:
            break
        constraints.append(constraint)

    # Create decision
    decision = Decision(
        id=decision_id,
        title=title,
        options={"A": option_a, "B": option_b},
        constraints=constraints,
        stop_rule={
            "max_agents": 5,
            "stop_when": ["failure_modes_repeat", "no_new_risk"]
        }
    )

    decision.save()

    # Create council directory
    (decision_dir / "council").mkdir(parents=True, exist_ok=True)

    print(f"\nDecision created: {decision_dir}")
    print(f"  - decision.yaml")
    print(f"  - council/")
    print(f"\nNext: Run 'python aq_decision.py council {decision_id}'")


def build_agent_prompt(role: str, decision: Decision) -> str:
    """Build the full prompt for an agent."""
    base_prompt = (PROMPTS_DIR / "base_decision.md").read_text()
    role_prompt = (PROMPTS_DIR / f"{role}.md").read_text()

    context = f"""
## Decision Context

**Title**: {decision.title}

**Options**:
- Option A: {decision.options.get('A', 'Not specified')}
- Option B: {decision.options.get('B', 'Not specified')}

**Constraints**:
{chr(10).join(f'- {c}' for c in decision.constraints)}
"""

    return f"{base_prompt}\n\n{role_prompt}\n\n{context}"


async def run_agent(role: str, cli: str, decision: Decision) -> tuple[str, bool, str]:
    """Run a single agent and return (role, success, output)."""
    prompt = build_agent_prompt(role, decision)
    output_file = DECISIONS_DIR / decision.id / "council" / f"{role}.md"

    print(f"  - {role.capitalize():12} ({cli})... ", end="", flush=True)

    try:
        # Build command based on CLI type
        if cli == "codex":
            cmd = [
                "codex",
                "-p", prompt,
            ]
        elif cli == "claude":
            cmd = [
                "claude",
                "-p", prompt,
                "--output-format", "text"
            ]
        else:
            # Generic fallback
            cmd = [cli, "-p", prompt]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=300  # 5 minute timeout
        )

        if proc.returncode == 0:
            output = stdout.decode()
            output_file.write_text(f"# {role.capitalize()} Analysis\n\n{output}")
            print("Done")
            return (role, True, output)
        else:
            error = stderr.decode()
            print(f"Failed: {error[:50]}")
            return (role, False, error)

    except asyncio.TimeoutError:
        print("Timeout")
        return (role, False, "Agent timed out after 5 minutes")
    except FileNotFoundError:
        print(f"CLI not found: {cli}")
        return (role, False, f"CLI '{cli}' not installed")
    except Exception as e:
        print(f"Error: {e}")
        return (role, False, str(e))


async def run_council(decision: Decision) -> list[tuple[str, bool, str]]:
    """Run all agents in parallel."""
    tasks = [
        run_agent(role, cli, decision)
        for role, (cli, _) in AGENTS.items()
    ]
    return await asyncio.gather(*tasks)


def check_saturation(decision: Decision) -> tuple[bool, str]:
    """Check if council has reached saturation (no new information)."""
    council_dir = DECISIONS_DIR / decision.id / "council"
    failure_modes = []

    for md_file in council_dir.glob("*.md"):
        content = md_file.read_text().lower()
        # Extract failure modes (simple heuristic)
        if "failure" in content:
            # Count unique failure-related sentences
            for line in content.split("\n"):
                if "failure" in line or "risk" in line or "break" in line:
                    failure_modes.append(line.strip()[:100])

    # Check for repetition
    unique_modes = set(failure_modes)
    if len(failure_modes) > 5 and len(unique_modes) < len(failure_modes) * 0.5:
        return True, "Failure modes are repeating across agents"

    return False, ""


def cmd_council(args):
    """Run the decision council."""
    decision_id = args.decision_id

    try:
        decision = Decision.load(decision_id)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"Invoking Decision Council for: {decision.title}\n")
    print("Agents:")
    for role, (cli, desc) in AGENTS.items():
        print(f"  - {role.capitalize():12} ({cli}) - {desc}")
    print()

    print("Running agents in parallel...\n")
    results = asyncio.run(run_council(decision))

    # Summary
    print("\nResults:")
    success_count = sum(1 for _, success, _ in results if success)
    print(f"  {success_count}/{len(results)} agents completed successfully")

    council_dir = DECISIONS_DIR / decision.id / "council"
    for md_file in sorted(council_dir.glob("*.md")):
        print(f"  - {md_file.name}")

    # Check saturation
    saturated, reason = check_saturation(decision)
    if saturated:
        print(f"\n*** Council saturation reached: {reason}")
        print("    Further queries unlikely to add new information.")

    print(f"\nNext: Run 'python aq_decision.py decide {decision_id}'")


def cmd_decide(args):
    """Open verdict template for human decision."""
    decision_id = args.decision_id

    try:
        decision = Decision.load(decision_id)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    verdict_file = DECISIONS_DIR / decision_id / "verdict.md"

    if not verdict_file.exists():
        # Create template
        template = f"""# Decision Verdict

**Decision**: {decision.title}

**Options**:
- A: {decision.options.get('A', '')}
- B: {decision.options.get('B', '')}

---

## Chosen Option: [A/B]

## Known Risks I Accept
- [Risk 1 from council analysis]
- [Risk 2 from council analysis]

## Risks I Explicitly Reject
- [Risk that influenced my choice]
- [Risk that influenced my choice]

## Why This Is Acceptable Now
- [Reasoning based on constraints]
- [Reasoning based on current phase]

## Mitigations Required
- [ ] [Action to reduce accepted risk]
- [ ] [Action to reduce accepted risk]

---

Decision Date: {datetime.now().strftime('%Y-%m-%d')}
Revisit After: [1 month / 3 months / 6 months]
"""
        verdict_file.write_text(template)
        print(f"Created verdict template: {verdict_file}")

    # Try to open in editor
    editor = os.environ.get("EDITOR", "vim")
    try:
        subprocess.run([editor, str(verdict_file)])
    except FileNotFoundError:
        print(f"\nEdit the verdict file manually: {verdict_file}")


def cmd_status(args):
    """Show status of a decision."""
    decision_id = args.decision_id

    try:
        decision = Decision.load(decision_id)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    decision_dir = DECISIONS_DIR / decision_id
    council_dir = decision_dir / "council"
    verdict_file = decision_dir / "verdict.md"

    print(f"Decision: {decision.title}")
    print(f"ID: {decision.id}")
    print()

    print("Options:")
    for opt, desc in decision.options.items():
        print(f"  {opt}: {desc}")
    print()

    print("Constraints:")
    for c in decision.constraints:
        print(f"  - {c}")
    print()

    print("Council Status:")
    for role in AGENTS:
        md_file = council_dir / f"{role}.md"
        status = "Done" if md_file.exists() else "Pending"
        print(f"  - {role.capitalize():12} [{status}]")
    print()

    if verdict_file.exists():
        print(f"Verdict: Written ({verdict_file})")
        # Extract chosen option
        content = verdict_file.read_text()
        if "Chosen Option:" in content:
            for line in content.split("\n"):
                if "Chosen Option:" in line:
                    print(f"  {line.strip()}")
                    break
    else:
        print("Verdict: Not yet decided")


def cmd_list(args):
    """List all decisions."""
    if not DECISIONS_DIR.exists():
        print("No decisions yet.")
        return

    decisions = sorted(DECISIONS_DIR.iterdir())
    if not decisions:
        print("No decisions yet.")
        return

    print("Decisions:\n")
    for decision_dir in decisions:
        if not decision_dir.is_dir():
            continue

        yaml_file = decision_dir / "decision.yaml"
        verdict_file = decision_dir / "verdict.md"
        council_dir = decision_dir / "council"

        if not yaml_file.exists():
            continue

        decision = Decision.load(decision_dir.name)
        council_count = len(list(council_dir.glob("*.md"))) if council_dir.exists() else 0
        status = "Decided" if verdict_file.exists() else f"Council: {council_count}/5"

        print(f"  {decision.id}")
        print(f"    Title: {decision.title}")
        print(f"    Status: {status}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="AQ Decision Council CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python aq_decision.py new options_lifecycle_v1
    python aq_decision.py council options_lifecycle_v1
    python aq_decision.py decide options_lifecycle_v1
    python aq_decision.py status options_lifecycle_v1
    python aq_decision.py list
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # new
    new_parser = subparsers.add_parser("new", help="Create a new decision")
    new_parser.add_argument("decision_id", help="Unique ID for the decision")

    # council
    council_parser = subparsers.add_parser("council", help="Run the decision council")
    council_parser.add_argument("decision_id", help="Decision ID to analyze")

    # decide
    decide_parser = subparsers.add_parser("decide", help="Make the final verdict")
    decide_parser.add_argument("decision_id", help="Decision ID to decide on")

    # status
    status_parser = subparsers.add_parser("status", help="Show decision status")
    status_parser.add_argument("decision_id", help="Decision ID to check")

    # list
    list_parser = subparsers.add_parser("list", help="List all decisions")

    args = parser.parse_args()

    if args.command == "new":
        cmd_new(args)
    elif args.command == "council":
        cmd_council(args)
    elif args.command == "decide":
        cmd_decide(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "list":
        cmd_list(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

"""Live demo tool: prompts the audience's mad-lib answers and writes the resulting
mandate to mandate_live.yaml, which scoring_agent.py reads.

Usage:
    python collect_madlib.py
    python collect_madlib.py --output mandate_live.yaml
"""

import argparse
from pathlib import Path

import yaml

TEMPLATE_PATH = Path(__file__).parent / "madlib_template.yaml"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=str(Path(__file__).parent / "mandate_live.yaml"),
        help="Where to write the generated mandate (default: mandate_live.yaml next to this script)",
    )
    args = parser.parse_args()

    template = yaml.safe_load(TEMPLATE_PATH.read_text())

    print("Domain Huntress — A24 mandate mad-lib. Type the audience's answer for each blank.\n")

    answers = {}
    for blank in template["blanks"]:
        answer = input(f"{blank['prompt']} ").strip()
        while not answer:
            answer = input("  (can't be blank) " + blank["prompt"] + " ").strip()
        answers[blank["key"]] = answer

    sentence = template["sentence"].format(**answers)

    print(f"\nGenerated mandate: {sentence}\n")

    out = {
        "sentence": sentence,
        "blanks": answers,
        "source": "madlib",
    }
    Path(args.output).write_text(yaml.safe_dump(out, sort_keys=False))
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()

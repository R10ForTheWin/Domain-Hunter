"""Alternate live-demo intake: instead of collecting the mad-lib's 5 separate blanks, let someone
just type or say what they're looking for in their own words (e.g. "something dark and twisty
about betrayal in a small town"), and use Claude to map that onto the same 5 mad-lib slots.

Writes the same mandate_live.yaml shape as collect_madlib.py, so scoring_agent.py needs no changes
and can't tell which intake method produced a given mandate (the 'source' field records which,
for the record/demo narration only).

Requires ANTHROPIC_API_KEY in the environment.

Usage:
    python collect_mandate_freeform.py
    python collect_mandate_freeform.py --text "something dark and twisty about betrayal in a small town"
"""

import argparse
import os
import sys
from pathlib import Path

import yaml
from anthropic import Anthropic

TEMPLATE_PATH = Path(__file__).parent / "madlib_template.yaml"
BLANK_KEYS = ["GENRE", "ADJECTIVE", "CHARACTER", "VERB", "SETTING"]

EXTRACT_TOOL = {
    "name": "extract_mandate",
    "description": "Map free-form text describing a desired movie pitch onto 5 mad-lib-style slots.",
    "input_schema": {
        "type": "object",
        "properties": {
            "GENRE": {"type": "string", "description": "A genre noun/phrase, e.g. 'heist', "
                                                         "'coming-of-age', 'horror'."},
            "ADJECTIVE": {"type": "string", "description": "A mood/tone adjective, e.g. "
                                                             "'unsettling', 'surreal', 'tender'."},
            "CHARACTER": {"type": "string", "description": "A type of protagonist, e.g. "
                                                             "'outsider', 'con artist', 'final girl'."},
            "VERB": {"type": "string", "description": "An action the protagonist does, already "
                                                        "conjugated present tense, e.g. 'escapes', "
                                                        "'haunts', 'survives'."},
            "SETTING": {"type": "string", "description": "A place/setting, e.g. 'boarding "
                                                           "school', 'space station', 'small town'."},
        },
        "required": BLANK_KEYS,
    },
}


def extract_blanks(client: Anthropic, model: str, text: str) -> dict:
    prompt = f"""Someone described what they want in a movie pitch, in their own free-form words
rather than the structured mad-lib format (which asks separately for a genre, a mood adjective, a
character type, a verb, and a setting).

Map their description onto those 5 slots. If something is explicitly stated, use it directly. If
something isn't explicitly stated, infer a specific, sensible value consistent with the overall
vibe of what they described — never leave a slot generic or empty.

THEIR DESCRIPTION: "{text}"

Call extract_mandate with all 5 slots filled in."""

    response = client.messages.create(
        model=model,
        max_tokens=512,
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "extract_mandate"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("No tool_use block in extraction response")


def validate_blanks(blanks: dict) -> dict:
    for key in BLANK_KEYS:
        value = blanks.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"missing or empty '{key}' in extracted mandate: {blanks!r}")
    return blanks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default=None,
                         help="the free-form description (skips the interactive prompt if given)")
    parser.add_argument("--output", default=str(Path(__file__).parent / "mandate_live.yaml"))
    parser.add_argument("--model", default="claude-haiku-4-5-20251001")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Export it before running this script.")

    text = args.text
    if not text:
        print("Domain Huntress — free-form mandate intake.")
        text = input("Describe what you're looking for, in your own words: ").strip()
        while not text:
            text = input("  (can't be blank) Describe what you're looking for: ").strip()

    client = Anthropic()
    blanks = validate_blanks(extract_blanks(client, args.model, text))

    template = yaml.safe_load(TEMPLATE_PATH.read_text())
    sentence = template["sentence"].format(**blanks)

    print(f"\nMapped to mandate: {sentence}\n")
    for key in BLANK_KEYS:
        print(f"  {key} = {blanks[key]}")

    out = {
        "sentence": sentence,
        "blanks": blanks,
        "source": "freeform",
        "raw_input": text,
    }
    Path(args.output).write_text(yaml.safe_dump(out, sort_keys=False))
    print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()

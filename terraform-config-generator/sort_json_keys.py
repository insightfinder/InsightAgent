#!/usr/bin/env python3
"""Sort json_key_settings blocks alphabetically by json_key in all .tf files."""

import re
import sys
from pathlib import Path

TERRAFORM_DIR = Path(__file__).parent / "TerraformFiles"


def sort_json_key_settings_in_file(path: Path) -> bool:
    text = path.read_text()

    if "json_key_settings" not in text:
        return False

    # Match the full json_key_settings = [ ... ] block (non-greedy, handles nested braces)
    # Each entry is a { ... } block inside the list
    def sort_block(match):
        block_text = match.group(0)
        list_content_match = re.search(r'json_key_settings\s*=\s*\[(.*)\]', block_text, re.DOTALL)
        if not list_content_match:
            return block_text

        list_content = list_content_match.group(1)

        # Split into individual { ... } entries
        entries = re.findall(r'\{[^{}]*\}', list_content, re.DOTALL)
        if not entries:
            return block_text

        def get_json_key(entry):
            m = re.search(r'json_key\s*=\s*"([^"]*)"', entry)
            return m.group(1) if m else ""

        sorted_entries = sorted(entries, key=get_json_key)

        # Rebuild list content preserving trailing comma style
        new_list_content = ""
        for i, entry in enumerate(sorted_entries):
            new_list_content += entry
            if i < len(sorted_entries) - 1:
                new_list_content += ","
        new_list_content += "\n  "

        new_block = block_text[:list_content_match.start(1)] + new_list_content + block_text[list_content_match.end(1):]
        return new_block

    # Match the entire json_key_settings = [ ... ] block
    new_text = re.sub(
        r'json_key_settings\s*=\s*\[.*?\]',
        sort_block,
        text,
        flags=re.DOTALL
    )

    if new_text == text:
        return False

    path.write_text(new_text)
    return True


def main():
    tf_files = sorted(TERRAFORM_DIR.rglob("*.tf"))
    changed = 0
    skipped = 0

    for tf_file in tf_files:
        try:
            if sort_json_key_settings_in_file(tf_file):
                print(f"  sorted: {tf_file.relative_to(TERRAFORM_DIR)}")
                changed += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  ERROR {tf_file}: {e}", file=sys.stderr)

    print(f"\nDone: {changed} files updated, {skipped} files skipped (no json_key_settings).")


if __name__ == "__main__":
    main()

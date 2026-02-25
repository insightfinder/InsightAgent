#!/usr/bin/env python3
"""
Script to convert newline-delimited JSON logs to a valid JSON array.
This allows the entire log file content to be copied as valid JSON.
"""

import json
import argparse
from pathlib import Path


def convert_ndjson_to_json(input_file, output_file=None, indent=2, compact=False):
    """
    Convert newline-delimited JSON (NDJSON) to a valid JSON array.
    
    Args:
        input_file: Path to the input NDJSON file
        output_file: Path to the output JSON file (if None, prints to stdout)
        indent: Number of spaces for indentation (default: 2, None for compact)
        compact: If True, output compact JSON without indentation
    """
    json_objects = []
    
    # Read the NDJSON file
    with open(input_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:  # Skip empty lines
                continue
            try:
                json_obj = json.loads(line)
                json_objects.append(json_obj)
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON on line {line_num}: {e}")
                continue
    
    # Convert to valid JSON array
    indent_value = None if compact else indent
    json_output = json.dumps(json_objects, indent=indent_value)
    
    # Write to file or print to stdout
    if output_file:
        with open(output_file, 'w') as f:
            f.write(json_output)
        print(f"Successfully converted {len(json_objects)} records from {input_file} to {output_file}")
    else:
        print(json_output)
    
    return len(json_objects)


def main():
    parser = argparse.ArgumentParser(
        description='Convert newline-delimited JSON logs to valid JSON array',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert and save to a new file
  python convert_logs_to_json.py generated_unique.log -o output.json
  
  # Print to stdout (can be redirected)
  python convert_logs_to_json.py generated_unique.log
  
  # Create compact JSON (no indentation)
  python convert_logs_to_json.py generated_unique.log -o output.json --compact
  
  # Custom indentation
  python convert_logs_to_json.py generated_unique.log -o output.json --indent 4
        """
    )
    
    parser.add_argument('input_file', type=str, help='Input NDJSON log file')
    parser.add_argument('-o', '--output', type=str, help='Output JSON file (optional, prints to stdout if not provided)')
    parser.add_argument('--indent', type=int, default=2, help='Number of spaces for indentation (default: 2)')
    parser.add_argument('--compact', action='store_true', help='Output compact JSON without indentation')
    
    args = parser.parse_args()
    
    # Check if input file exists
    if not Path(args.input_file).exists():
        print(f"Error: Input file '{args.input_file}' not found")
        return 1
    
    try:
        convert_ndjson_to_json(
            args.input_file,
            args.output,
            indent=args.indent,
            compact=args.compact
        )
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())

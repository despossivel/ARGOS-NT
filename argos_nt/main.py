from __future__ import annotations

import argparse
import json

from argos_nt.agents.pipeline import InvestigationPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ARGOS-NT investigation runner")
    parser.add_argument("file", help="Path to .txt or .md target file")
    parser.add_argument("--full-scan", action="store_true", help="Enable full tool scan")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    pipeline = InvestigationPipeline()
    try:
        result = pipeline.ingest_file(args.file, full_scan=args.full_scan)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()

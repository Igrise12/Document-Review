from argparse import ArgumentParser
from time import perf_counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "samples/generated/01-en-happy-classic.pdf"
SUPPORTED_SUFFIXES = {".jpeg", ".jpg", ".pdf", ".png"}


def parse_args():
    parser = ArgumentParser(description="Run PP-StructureV3 against one fictional document.")
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"PDF or image to analyze (default: {DEFAULT_INPUT.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="Paddle device, for example cpu, gpu, or gpu:0 (default: cpu)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/paddleocr-output"),
        help="Directory for PaddleOCR JSON and Markdown output.",
    )
    parser.add_argument(
        "--print-results",
        action="store_true",
        help="Print each structured PaddleOCR result as well as saving it.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input.resolve()

    if not input_path.is_file():
        raise SystemExit(f"Input document does not exist: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        allowed = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise SystemExit(f"Unsupported input type {input_path.suffix!r}; use {allowed}")

    try:
        from paddleocr import PPStructureV3
    except ImportError as exc:
        raise SystemExit(
            "PaddleOCR is not installed. Run the isolated setup from docs/build-along.md first."
        ) from exc

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Input: {input_path}")
    print(f"Device: {args.device}")
    print(f"Output directory: {args.output_dir.resolve()}")
    print("Loading PP-StructureV3; the first run may download model weights...")

    started = perf_counter()
    pipeline = PPStructureV3(device=args.device)
    results = list(pipeline.predict(input=str(input_path)))
    elapsed = perf_counter() - started

    for page_number, result in enumerate(results, start=1):
        print(f"Saving page {page_number} result")
        result.save_to_json(save_path=str(args.output_dir))
        result.save_to_markdown(save_path=str(args.output_dir))
        if args.print_results:
            result.print()

    print(f"Pages processed: {len(results)}")
    print(f"Elapsed seconds: {elapsed:.2f}")
    print("Inspect the generated JSON and Markdown files in the output directory.")


if __name__ == "__main__":
    main()

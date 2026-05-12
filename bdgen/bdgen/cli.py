"""CLI entry point: orchestrates the pipeline steps."""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from . import compose as compose_module
from . import references as references_module
from . import script as script_module
from . import upscale as upscale_module
from . import wizard as wizard_module
from .feedback import FeedbackStore, feedback_path_for
from .models import BdGenInput, BdGenScript, GenerationOptions
from .progress import StdoutReporter


def _project_dir(bd_script: BdGenScript, script_path: Path) -> Path:
    """Project dir = parent of the script file, by convention."""
    return bd_script.project_dir(fallback_script_path=script_path)


def _default_pages_dir(bd_script: BdGenScript, script_path: Path) -> Path:
    return _project_dir(bd_script, script_path) / "pages"


def cmd_script(args: argparse.Namespace) -> None:
    config = BdGenInput.load(args.input)
    out = Path(args.output) if args.output else config.generation_options.script_path
    if out is None:
        raise SystemExit(
            "Cannot determine where to write the script. "
            "Set 'project' in the input or pass -o/--output."
        )
    feedback_store = FeedbackStore.load_or_empty(feedback_path_for(out))
    feedback = feedback_store.get_for("script")
    bd_script = script_module.generate_script(
        config,
        input_path=Path(args.input),
        feedback=feedback,
        preview_pages=args.preview,
        script_path=out,
        reporter=StdoutReporter(),
        stats_project_dir=out.parent,
    )
    bd_script.save(out)
    print(f"Script written to {out}")


def cmd_references(args: argparse.Namespace) -> None:
    bd_script = BdGenScript.load(args.script)
    opts = _resolve_options(bd_script, args.input)
    feedback_store = FeedbackStore.load_or_empty(feedback_path_for(args.script))
    references_module.generate_references(
        bd_script, opts.references, opts.reference_image_model(),
        script_path=args.script,
        feedback_store=feedback_store,
        force=args.force,
        reporter=StdoutReporter(),
        stats_project_dir=_project_dir(bd_script, args.script),
    )
    bd_script.save(args.script)
    print(f"References written under {opts.references.output_dir}")


def cmd_compose(args: argparse.Namespace) -> None:
    bd_script = BdGenScript.load(args.script)
    opts = _resolve_options(bd_script, args.input)
    pages_dir = (
        Path(args.pages_dir)
        if args.pages_dir
        else _default_pages_dir(bd_script, args.script)
    )
    feedback_store = FeedbackStore.load_or_empty(feedback_path_for(args.script))
    out = compose_module.compose_output(
        bd_script, opts, pages_dir,
        feedback_store=feedback_store,
        force=args.force,
        reporter=StdoutReporter(),
        stats_project_dir=_project_dir(bd_script, args.script),
    )
    print(f"Done: {out}")


def cmd_run(args: argparse.Namespace) -> None:
    config = BdGenInput.load(args.input)
    opts = config.generation_options
    if opts.script_path is None:
        raise SystemExit("Cannot determine script_path. Set 'project' in the input.")
    feedback_store = FeedbackStore.load_or_empty(feedback_path_for(opts.script_path))
    feedback = feedback_store.get_for("script")
    reporter = StdoutReporter()
    bd_script = script_module.generate_script(
        config,
        input_path=Path(args.input),
        feedback=feedback,
        preview_pages=args.preview,
        script_path=opts.script_path,
        reporter=reporter,
        stats_project_dir=opts.script_path.parent,
    )
    bd_script.save(opts.script_path)
    references_module.generate_references(
        bd_script, opts.references, opts.reference_image_model(),
        script_path=opts.script_path,
        feedback_store=feedback_store,
        reporter=reporter,
        stats_project_dir=opts.script_path.parent,
    )
    bd_script.save(opts.script_path)
    project_dir = opts.script_path.parent
    out = compose_module.compose_output(
        bd_script, opts, project_dir / "pages",
        feedback_store=feedback_store,
        reporter=reporter,
        stats_project_dir=project_dir,
    )
    if opts.upscale.enabled:
        upscale_module.upscale_pages(
            bd_script,
            project_dir,
            opts.upscale,
            reporter=reporter,
            stats_project_dir=project_dir,
        )
    print(f"Done: {out}")


def cmd_upscale(args: argparse.Namespace) -> None:
    bd_script = BdGenScript.load(args.script)
    opts = _resolve_options(bd_script, args.input)
    project_dir = _project_dir(bd_script, args.script)
    out = upscale_module.upscale_pages(
        bd_script,
        project_dir,
        opts.upscale,
        reporter=StdoutReporter(),
        force=args.force,
        stats_project_dir=project_dir,
    )
    print(f"Upscaled pages written under {out}")


def cmd_wizard(args: argparse.Namespace) -> None:
    config = BdGenInput.load(args.input)
    opts = config.generation_options
    if opts.script_path is None:
        raise SystemExit("Cannot determine script_path. Set 'project' in the input.")
    project_dir = opts.script_path.parent
    pages_dir = Path(args.pages_dir) if args.pages_dir else project_dir / "pages"
    wizard_module.run_wizard(
        Path(args.input), pages_dir, preview_pages=args.preview
    )


def _resolve_options(script: BdGenScript, input_override: Path | None) -> GenerationOptions:
    """Use --input as override if provided, else fall back to script's embedded options."""
    if input_override is not None:
        return BdGenInput.load(input_override).generation_options
    if script.generation_options is not None:
        return script.generation_options
    raise SystemExit(
        "No generation_options found in the script. "
        "Either pass --input pointing to your bdgen.json, "
        "or re-run 'script' to regenerate a script that embeds the options."
    )


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="bdgen",
        description="Generate a comic book from a JSON definition using generative AI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    preview_help = (
        "Workflow test mode: write only the first N pages of the intended story "
        "(cover and back cover still generated)"
    )

    p = sub.add_parser("script", help="Expand bdgen.json into bdgen-script.json (LLM call)")
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, default=None)
    p.add_argument("--preview", type=int, default=None, help=preview_help)
    p.set_defaults(func=cmd_script)

    input_help = "Optional bdgen.json to override options embedded in the script"
    force_help = "Regenerate even if the target file already exists on disk"

    p = sub.add_parser("references", help="Generate character and location reference sheets")
    p.add_argument("script", type=Path)
    p.add_argument("--input", type=Path, default=None, help=input_help)
    p.add_argument("--force", action="store_true", help=force_help)
    p.set_defaults(func=cmd_references)

    p = sub.add_parser(
        "compose",
        help="Generate one image per page (page-level) and assemble the final output.",
    )
    p.add_argument("script", type=Path)
    p.add_argument("--input", type=Path, default=None, help=input_help)
    p.add_argument("--pages-dir", type=Path, default=None)
    p.add_argument("--force", action="store_true", help=force_help)
    p.set_defaults(func=cmd_compose)

    p = sub.add_parser("run", help="Full pipeline: script -> references -> compose")
    p.add_argument("input", type=Path)
    p.add_argument("--preview", type=int, default=None, help=preview_help)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser(
        "upscale",
        help="Optional local CPU-only upscale step applied to composed pages.",
    )
    p.add_argument("script", type=Path)
    p.add_argument("--input", type=Path, default=None, help=input_help)
    p.add_argument("--force", action="store_true", help=force_help)
    p.set_defaults(func=cmd_upscale)

    p = sub.add_parser(
        "wizard",
        help="Interactive walkthrough of the full pipeline with feedback support",
    )
    p.add_argument("input", type=Path)
    p.add_argument("--pages-dir", type=Path, default=None)
    p.add_argument("--preview", type=int, default=None, help=preview_help)
    p.set_defaults(func=cmd_wizard)

    args = parser.parse_args(argv)
    args.func(args)

"""Interactive wizard walking the user through the BD generation pipeline.

Each step lets the user accept the result, view it, or provide feedback that is
saved to bdgen-feedback.json and re-injected into the next regeneration.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import compose as compose_module
from . import references as references_module
from . import script as script_module
from . import upscale as upscale_module
from .feedback import FeedbackStore, feedback_path_for
from .models import BdGenInput, BdGenScript, GenerationOptions, ReferencesOptions
from .progress import StdoutReporter


def run_wizard(
    input_path: Path,
    pages_dir: Path,
    preview_pages: int | None = None,
) -> None:
    """Walk the user through script -> references -> compose -> optional upscale."""
    config = BdGenInput.load(input_path)
    opts = config.generation_options
    script_path = opts.script_path
    feedback_store = FeedbackStore.load_or_empty(feedback_path_for(script_path))
    feedback_path = feedback_path_for(script_path)

    bd_script = _step_script(
        input_path, opts, script_path, feedback_store, feedback_path, preview_pages
    )
    bd_script = _step_references(bd_script, opts, script_path, feedback_store, feedback_path)
    _step_compose(bd_script, opts, pages_dir, script_path, feedback_store, feedback_path)
    if opts.upscale.enabled and _prompt_yes_no("Lancer l'upscale local CPU ?", default=True):
        _step_upscale(bd_script, opts, script_path)

    print(f"\n== Pipeline terminé ==\nBD : {opts.output_path}")


def _step_script(
    input_path: Path,
    opts: GenerationOptions,
    script_path: Path,
    feedback_store: FeedbackStore,
    feedback_path: Path,
    preview_pages: int | None = None,
) -> BdGenScript:
    print("\n== Étape 1/3 : Script ==")
    if preview_pages is not None:
        print(f"(mode preview : seules les {preview_pages} premières pages seront générées)")

    # generate_script() handles all three cases internally:
    #   - no script on disk          → fresh generation
    #   - partial script on disk     → resume from where it stopped
    #   - complete script on disk    → return as-is (no API call)
    bd_script = _resume_script(input_path, script_path, feedback_store, preview_pages)

    while True:
        _print_script_summary(bd_script)
        choice = _prompt_choice(
            "Que faire ?",
            {"c": "ontinuer", "r": "elire le script", "m": "odifier (feedback)", "q": "uitter"},
        )
        if choice == "c":
            return bd_script
        if choice == "q":
            sys.exit(0)
        if choice == "r":
            _open_file(script_path)
            continue
        if choice == "m":
            text = _prompt_multiline("Feedback pour le script")
            if not text:
                continue
            feedback_store.add("script", None, text)
            feedback_store.save(feedback_path)
            if _prompt_yes_no("Relancer la génération depuis zéro ?", default=True):
                bd_script = _regen_script_fresh(
                    input_path, script_path, feedback_store, preview_pages
                )


def _resume_script(
    input_path: Path,
    script_path: Path,
    feedback_store: FeedbackStore,
    preview_pages: int | None = None,
) -> BdGenScript:
    """Load existing script as-is, or resume partial generation, or generate fresh."""
    config = BdGenInput.load(input_path)
    feedback = feedback_store.get_for("script")
    return script_module.generate_script(
        config,
        input_path,
        feedback=feedback,
        preview_pages=preview_pages,
        script_path=script_path,
        reporter=StdoutReporter(),
        stats_project_dir=script_path.parent,
    )


def _regen_script_fresh(
    input_path: Path,
    script_path: Path,
    feedback_store: FeedbackStore,
    preview_pages: int | None = None,
) -> BdGenScript:
    """Force a full regeneration: delete the current script first."""
    if script_path.exists():
        script_path.unlink()
    return _resume_script(input_path, script_path, feedback_store, preview_pages)


def _step_references(
    bd_script: BdGenScript,
    opts: GenerationOptions,
    script_path: Path,
    feedback_store: FeedbackStore,
    feedback_path: Path,
) -> BdGenScript:
    print("\n== Étape 2/3 : Références ==")
    references_module.generate_references(
        bd_script, opts.references, opts.reference_image_model(),
        script_path=script_path, feedback_store=feedback_store,
        reporter=StdoutReporter(),
        stats_project_dir=script_path.parent,
    )
    bd_script.save(script_path)

    while True:
        _print_refs_summary(bd_script)
        choice = _prompt_choice(
            "Que faire ?",
            {"c": "ontinuer", "v": "oir une image", "m": "odifier une réf", "q": "uitter"},
        )
        if choice == "c":
            return bd_script
        if choice == "q":
            sys.exit(0)
        ids = _all_ref_ids(bd_script)
        if choice == "v":
            target = _prompt_target("Quelle référence ?", ids)
            if target:
                ref_path = _path_for_ref(bd_script, opts.references, target)
                if ref_path:
                    _open_file(ref_path)
            continue
        if choice == "m":
            target = _prompt_target("Laquelle régénérer ?", ids)
            if not target:
                continue
            text = _prompt_multiline(f"Feedback pour {target}")
            if not text:
                continue
            feedback_store.add("references", target, text)
            feedback_store.save(feedback_path)
            if _prompt_yes_no(f"Régénérer {target} ?", default=True):
                ref_path = _path_for_ref(bd_script, opts.references, target)
                if ref_path and ref_path.exists():
                    ref_path.unlink()
                references_module.generate_references(
                    bd_script, opts.references, opts.reference_image_model(),
                    script_path=script_path, feedback_store=feedback_store,
                    reporter=StdoutReporter(),
                    stats_project_dir=script_path.parent,
                )
                bd_script.save(script_path)


def _step_compose(
    bd_script: BdGenScript,
    opts: GenerationOptions,
    pages_dir: Path,
    script_path: Path,
    feedback_store: FeedbackStore,
    feedback_path: Path,
) -> None:
    print("\n== Étape 3/3 : Composition ==")
    compose_module.compose_output(
        bd_script, opts, pages_dir, feedback_store=feedback_store,
        reporter=StdoutReporter(),
        stats_project_dir=script_path.parent,
    )

    while True:
        targets = _page_targets(bd_script)
        choice = _prompt_choice(
            "Que faire ?",
            {
                "c": "ontinuer",
                "v": "oir une page (ou 'pdf')",
                "m": "odifier une page",
                "q": "uitter",
            },
        )
        if choice == "c":
            return
        if choice == "q":
            sys.exit(0)
        if choice == "v":
            target = _prompt_target("Quelle page ?", targets + ["pdf"])
            if target == "pdf":
                _open_file(opts.output_path)
            elif target:
                _open_file(_page_path(pages_dir, target))
            continue
        if choice == "m":
            target = _prompt_target("Laquelle régénérer ?", targets)
            if not target:
                continue
            text = _prompt_multiline(f"Feedback pour {target}")
            if not text:
                continue
            feedback_store.add("compose", target, text)
            feedback_store.save(feedback_path)
            if _prompt_yes_no(f"Régénérer {target} ?", default=True):
                pp = _page_path(pages_dir, target)
                if pp.exists():
                    pp.unlink()
                compose_module.compose_output(
                    bd_script, opts, pages_dir, feedback_store=feedback_store,
                    reporter=StdoutReporter(),
                    stats_project_dir=script_path.parent,
                )


def _step_upscale(
    bd_script: BdGenScript,
    opts: GenerationOptions,
    script_path: Path,
) -> None:
    print("\n== Étape 4/4 : Upscale local (optionnel) ==")
    project_dir = script_path.parent
    upscale_module.upscale_pages(
        bd_script,
        project_dir=project_dir,
        options=opts.upscale,
        reporter=StdoutReporter(),
        stats_project_dir=project_dir,
    )
    output_dir = opts.upscale.output_dir or (project_dir / "pages_upscaled")
    print(f"  Images upscalées : {output_dir}")


# --- Helpers ---


def _prompt_choice(prompt: str, choices: dict[str, str]) -> str:
    options = "  ".join(f"[{k}]{label}" for k, label in choices.items())
    print(prompt)
    print(f"  {options}")
    while True:
        ans = input("> ").strip().lower()
        if ans in choices:
            return ans
        print(f"  Choisir parmi : {', '.join(choices.keys())}")


def _prompt_multiline(label: str) -> str:
    print(f"{label} (ligne vide pour terminer) :")
    lines: list[str] = []
    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            return ""
        if not line:
            break
        lines.append(line)
    return "\n".join(lines)


def _prompt_yes_no(question: str, default: bool = False) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    while True:
        ans = input(question + suffix).strip().lower()
        if not ans:
            return default
        if ans in ("y", "yes", "o", "oui"):
            return True
        if ans in ("n", "no", "non"):
            return False


def _prompt_target(question: str, options: list[str]) -> str | None:
    print(f"{question}")
    print(f"  Options : {', '.join(options)}")
    ans = input("> ").strip()
    if ans not in options:
        print(f"  Inconnu : {ans}")
        return None
    return ans


def _open_file(path: Path) -> None:
    if not path.exists():
        print(f"  Fichier absent : {path}")
        return
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)])
    else:
        subprocess.run(["xdg-open", str(path)])


def _print_script_summary(bd_script: BdGenScript) -> None:
    print(
        f"  {len(bd_script.characters)} personnages, "
        f"{len(bd_script.locations)} décors, "
        f"{len(bd_script.pages)} pages, "
        f"{sum(len(p.panels) for p in bd_script.pages)} cases"
    )


def _print_refs_summary(bd_script: BdGenScript) -> None:
    chars = ", ".join(c.id for c in bd_script.characters)
    locs = ", ".join(l.id for l in bd_script.locations)
    print(f"  Personnages : {chars}")
    print(f"  Décors      : {locs}")


def _all_ref_ids(bd_script: BdGenScript) -> list[str]:
    return [c.id for c in bd_script.characters] + [l.id for l in bd_script.locations]


def _path_for_ref(
    bd_script: BdGenScript, refs_options: ReferencesOptions, target_id: str
) -> Path | None:
    if bd_script.character_by_id(target_id):
        return refs_options.output_dir / "characters" / f"{target_id}.png"
    if bd_script.location_by_id(target_id):
        return refs_options.output_dir / "locations" / f"{target_id}.png"
    return None


def _page_targets(bd_script: BdGenScript) -> list[str]:
    targets: list[str] = []
    if bd_script.cover is not None:
        targets.append("cover")
    targets.extend(f"page_{p.page_number}" for p in bd_script.pages)
    if bd_script.back_cover is not None:
        targets.append("back")
    return targets


def _page_path(pages_dir: Path, target: str) -> Path:
    if target == "cover":
        return pages_dir / "cover.png"
    if target == "back":
        return pages_dir / "back.png"
    num = int(target.split("_")[1])
    return pages_dir / f"page_{num:02d}.png"

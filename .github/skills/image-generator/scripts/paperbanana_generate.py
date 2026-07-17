#!/usr/bin/env python3
"""Wrapper around the real PaperBanana package (llmsresearch/paperbanana).

Uses the PaperBanana multi-agent pipeline with OpenAI as the provider:
  Phase 0 (Optimization): Context Enricher + Caption Sharpener
  Phase 1 (Linear Planning): Retriever → Planner → Stylist
  Phase 2 (Iterative Refinement): Visualizer ↔ Critic

Requires:
  pip install "git+https://github.com/llmsresearch/paperbanana[openai]"
  OPENAI_API_KEY in .env

Usage:
  python paperbanana_generate.py "description" "output.png" --context "methodology text"
"""

import argparse
import asyncio
import logging
import os
import shutil
import sys

from dotenv import load_dotenv
from pathlib import Path

logger = logging.getLogger(__name__)

# Walk up from this script to find .env at the workspace root
# Script lives at .github/skills/image-generator/scripts/paperbanana_generate.py
_SCRIPT_DIR = Path(__file__).resolve().parent
_WORKSPACE_ROOT = _SCRIPT_DIR.parents[3]  # scripts → image-generator → skills → .github → repo root
_ENV_FILE = _WORKSPACE_ROOT / ".env"

# Environment variable priority: .env file takes precedence over existing env vars (override=True)
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=True)
    logger.info("Loaded .env from %s", _ENV_FILE)
else:
    # Fallback: let find_dotenv search from CWD upward
    load_dotenv(override=True)
    logger.warning("No .env at %s — falling back to find_dotenv()", _ENV_FILE)


def _build_settings(iterations: int = 3, optimize: bool = True, auto_refine: bool = False) -> "Settings":
    """Build PaperBanana Settings configured for OpenAI provider.

    Package defaults: gpt-5.2 (VLM), gpt-image-2 (image gen).
    Override via TEXT_MODEL / IMAGE_MODEL env vars if needed.
    """
    from paperbanana.core.config import Settings

    vlm_model = os.environ.get("TEXT_MODEL", "gpt-5.2")
    image_model = os.environ.get("IMAGE_MODEL", "gpt-image-2")

    kwargs: dict = {
        "vlm_provider": "openai",
        "image_provider": "openai_imagen",
        "vlm_model": vlm_model,
        "image_model": image_model,
        "openai_vlm_model": vlm_model,
        "openai_image_model": image_model,
        "refinement_iterations": iterations,
        "auto_refine": auto_refine,
        "optimize_inputs": optimize,
        "output_format": "png",
        "save_iterations": True,
    }

    return Settings(**kwargs)


async def run_pipeline(
    description: str,
    output_path: str,
    context: str = "",
    max_critic_rounds: int = 3,
    optimize: bool = True,
    auto_refine: bool = False,
) -> str:
    """Run the full PaperBanana pipeline via the real package.

    Returns the output image path.
    """
    from paperbanana import PaperBananaPipeline, GenerationInput, DiagramType

    # Defensive cleanup for shell-composed commands on Windows. A leading space
    # before a drive letter (" C:\\...") makes os.makedirs() fail after the
    # expensive generation has completed.
    output_path = output_path.strip().strip('"').strip("'")

    settings = _build_settings(iterations=max_critic_rounds, optimize=optimize, auto_refine=auto_refine)
    pipeline = PaperBananaPipeline(settings=settings)

    gen_input = GenerationInput(
        source_context=context or description,
        communicative_intent=description,
        diagram_type=DiagramType.METHODOLOGY,
    )

    logger.info("Starting pipeline (provider=openai, iterations=%d, optimize=%s, auto_refine=%s)…", max_critic_rounds, optimize, auto_refine)
    result = await pipeline.generate(gen_input)

    # Copy the final image to the requested output path
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(result.image_path, output)

    logger.info("Pipeline complete: %d iteration(s), saved to %s", len(result.iterations), output)
    return str(output)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="PaperBanana academic illustration generator (llmsresearch/paperbanana)"
    )
    parser.add_argument("description", help="Illustration description / communicative intent")
    parser.add_argument("output", help="Output PNG path")
    parser.add_argument(
        "--context", default="",
        help="Methodology context text for the Planner agent"
    )
    parser.add_argument(
        "--critic-rounds", type=int, default=None,
        help="Visualizer-Critic refinement iterations (default: MAX_CRITIC_ROUNDS env or 2)"
    )
    parser.add_argument(
        "--no-optimize", dest="optimize", action="store_false",
        help="Disable Phase 0 optimization (Context Enricher + Caption Sharpener). Enabled by default."
    )
    parser.add_argument(
        "--auto", action="store_true",
        help="Auto-refine until critic is satisfied (uses --max-iterations as cap, default 5)"
    )
    parser.add_argument(
        "--max-iterations", type=int, default=5,
        help="Max refinement iterations when --auto is used (default: 5)"
    )
    parser.set_defaults(optimize=True)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if not os.environ.get("OPENAI_API_KEY"):
        logger.error(
            "OPENAI_API_KEY not found in environment. "
            "Ensure .env exists at workspace root (%s) with OPENAI_API_KEY=sk-...",
            _WORKSPACE_ROOT,
        )
        sys.exit(1)

    max_rounds = args.critic_rounds or int(os.environ.get("MAX_CRITIC_ROUNDS", "3"))
    iterations = args.max_iterations if args.auto else max_rounds

    asyncio.run(run_pipeline(
        description=args.description,
        output_path=args.output,
        context=args.context,
        max_critic_rounds=iterations,
        optimize=args.optimize,
        auto_refine=args.auto,
    ))


if __name__ == "__main__":
    main()

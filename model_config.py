"""Shared model routing for spectra runners.

Single source of truth: `models.yaml` at the repo root.

Resolution priority (highest → lowest):
  requirements_runner:
    plan/params.yaml `models:` (per-run) → CLI --model → models.yaml `agents:`
    → models.yaml `default_model` → FALLBACK_MODEL
  solution_design_runner:
    CLI --models → models.yaml `solution_design.designer_models` → [default_model]
    selector/critic ← models.yaml `solution_design.<role>_model` → default_model
"""
from pathlib import Path

FALLBACK_MODEL = "kimi/kimi-k3"
CONFIG_NAME = "models.yaml"


def load_model_config(repo_root: Path) -> dict:
    """Load models.yaml; missing or invalid file → empty config (all defaults)."""
    path = Path(repo_root) / CONFIG_NAME
    if not path.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def default_model(cfg: dict) -> str:
    return cfg.get("default_model") or FALLBACK_MODEL


def agent_model(agent_name: str, cfg: dict) -> str:
    """models.yaml agents[agent] → default_model."""
    return (cfg.get("agents") or {}).get(agent_name) or default_model(cfg)


def designer_models(cfg: dict, cli_models: list[str] | None = None) -> list[str]:
    """CLI --models → solution_design.designer_models → [default_model]."""
    if cli_models:
        return list(cli_models)
    models = (cfg.get("solution_design") or {}).get("designer_models")
    if models:
        return [str(m) for m in models]
    return [default_model(cfg)]


def sd_role_model(role: str, cfg: dict) -> str:
    """role: 'selector' | 'critic' → solution_design.<role>_model → default_model."""
    return (cfg.get("solution_design") or {}).get(f"{role}_model") or default_model(cfg)

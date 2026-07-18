"""Shared model routing for spectra runners.

Single source of truth: `models.yaml` at the repo root.

Resolution priority (highest → lowest):
  requirements_runner:
    plan/params.yaml `models:` (per-run) → CLI --model → models.yaml `agents:`
    → models.yaml `default_model`
  solution_design_runner:
    CLI --models → models.yaml `solution_design.designer_models` → [default_model]
    selector/critic ← models.yaml `solution_design.<role>_model` → default_model

`default_model` is REQUIRED: runners refuse to start `run`/`resume` without it.
There is no hardcoded fallback — create models.yaml from models.yaml.example.
"""
from pathlib import Path

CONFIG_NAME = "models.yaml"


class ModelConfigError(Exception):
    """Raised when models.yaml is missing or default_model is not set."""


def load_model_config(repo_root: Path) -> dict:
    """Load models.yaml; missing or invalid file → empty config."""
    path = Path(repo_root) / CONFIG_NAME
    if not path.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def default_model(cfg: dict) -> str:
    """models.yaml default_model — required, no fallback."""
    m = cfg.get("default_model")
    if not m:
        raise ModelConfigError(
            "default_model is not set in models.yaml. "
            "Set it (e.g. 'default_model: kimi/kimi-k3') — see models.yaml.example."
        )
    return m


def require_model_config(repo_root: Path, cfg: dict) -> str:
    """Startup gate for run/resume: config file must exist and set default_model.

    Returns the default model. Exits the process with a clear message otherwise.
    """
    if not cfg:
        raise ModelConfigError(
            f"{Path(repo_root) / CONFIG_NAME} not found or empty. "
            f"Run: cp models.yaml.example {CONFIG_NAME}"
        )
    return default_model(cfg)


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

#!/usr/bin/env python3
"""Generate OpenAPI specification from FastAPI app.

This script extracts the OpenAPI schema from the FastAPI application
and saves it to the specs directory.

Usage:
    python -m scripts.generate_openapi
    # or from backend directory:
    python scripts/generate_openapi.py
"""

import json
import sys
from pathlib import Path

# Add src to path for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from src.main import app  # noqa: E402


def generate_openapi() -> None:
    """Generate OpenAPI spec and save to specs directory."""
    # Get OpenAPI schema from FastAPI
    openapi_schema = app.openapi()

    # Output paths
    specs_dir = backend_dir.parent / "specs" / "001-product-overview" / "contracts"
    specs_dir.mkdir(parents=True, exist_ok=True)

    # Save as JSON
    json_path = specs_dir / "openapi.json"
    with open(json_path, "w") as f:
        json.dump(openapi_schema, f, indent=2)
    print(f"Generated: {json_path}")

    # Also save as YAML if pyyaml is available
    try:
        import yaml

        yaml_path = specs_dir / "openapi.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(openapi_schema, f, default_flow_style=False, sort_keys=False)
        print(f"Generated: {yaml_path}")
    except ImportError:
        print("Note: Install pyyaml to also generate openapi.yaml")

    # Print summary
    paths = openapi_schema.get("paths", {})
    print(f"\nOpenAPI spec generated with {len(paths)} endpoints:")
    for path in sorted(paths.keys()):
        methods = list(paths[path].keys())
        print(f"  {path}: {', '.join(m.upper() for m in methods)}")


if __name__ == "__main__":
    generate_openapi()

#!/bin/bash
# Generate TypeScript types from OpenAPI specification
#
# Usage:
#   ./scripts/generate-types.sh
#
# Prerequisites:
#   npm install -D openapi-typescript

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$FRONTEND_DIR")"

# Paths
OPENAPI_JSON="$PROJECT_ROOT/specs/001-product-overview/contracts/openapi.json"
OUTPUT_DIR="$FRONTEND_DIR/src/api/generated"

echo "Generating TypeScript types from OpenAPI spec..."

# Check if OpenAPI spec exists
if [ ! -f "$OPENAPI_JSON" ]; then
    echo "Error: OpenAPI spec not found at $OPENAPI_JSON"
    echo "Run 'python -m scripts.generate_openapi' from backend/ first"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Check if openapi-typescript is installed
if ! npx openapi-typescript --version &> /dev/null; then
    echo "Installing openapi-typescript..."
    npm install -D openapi-typescript
fi

# Generate types
npx openapi-typescript "$OPENAPI_JSON" -o "$OUTPUT_DIR/api-types.ts"

echo "Generated: $OUTPUT_DIR/api-types.ts"

# Count generated types
TYPE_COUNT=$(grep -c "export type\|export interface" "$OUTPUT_DIR/api-types.ts" 2>/dev/null || echo "0")
echo "Total types generated: $TYPE_COUNT"

#!/bin/bash

# Air-Gapped RAG Packaging Script
# Creates clean distribution packages excluding development artifacts

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PACKAGE_NAME="ai-inference"
VERSION=$(grep -E '^__version__' "$PROJECT_ROOT/src/ai_inference/__init__.py" | cut -d'"' -f2)
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

# Usage function
usage() {
    cat << EOF
Usage: $0 [OPTIONS] [PACKAGE_TYPE]

Create distribution packages for Air-Gapped RAG system.

PACKAGE_TYPES:
    source      - Source code package (default)
    deployment  - Deployment-ready package
    production  - Production package (minimal)
    full        - Full package with documentation

OPTIONS:
    -v, --version VERSION    Override version number
    -o, --output DIR        Output directory (default: ./dist)
    -n, --name NAME         Override package name
    --include-tests         Include test files in package
    --include-docs          Include documentation
    --dry-run              Show what would be packaged without creating
    -h, --help             Show this help message

Examples:
    $0 source                    # Create source package
    $0 deployment -o /tmp        # Create deployment package in /tmp
    $0 production --dry-run      # Preview production package contents

EOF
}

# Parse command line arguments
PACKAGE_TYPE="source"
OUTPUT_DIR="$PROJECT_ROOT/dist"
INCLUDE_TESTS=false
INCLUDE_DOCS=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--version)
            VERSION="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -n|--name)
            PACKAGE_NAME="$2"
            shift 2
            ;;
        --include-tests)
            INCLUDE_TESTS=true
            shift
            ;;
        --include-docs)
            INCLUDE_DOCS=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        source|deployment|production|full)
            PACKAGE_TYPE="$1"
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Set package-specific configurations
case "$PACKAGE_TYPE" in
    "source")
        PACKAGE_SUFFIX="src"
        INCLUDE_TESTS=true
        INCLUDE_DOCS=true
        ;;
    "deployment")
        PACKAGE_SUFFIX="deploy"
        INCLUDE_DOCS=true
        ;;
    "production")
        PACKAGE_SUFFIX="prod"
        ;;
    "full")
        PACKAGE_SUFFIX="full"
        INCLUDE_TESTS=true
        INCLUDE_DOCS=true
        ;;
esac

# Generate package filename
PACKAGE_FILENAME="${PACKAGE_NAME}-${VERSION}-${PACKAGE_SUFFIX}-${TIMESTAMP}.zip"
PACKAGE_PATH="$OUTPUT_DIR/$PACKAGE_FILENAME"

log_info "Creating $PACKAGE_TYPE package: $PACKAGE_FILENAME"
log_info "Version: $VERSION"
log_info "Output: $PACKAGE_PATH"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Read .zipignore file and create exclusion patterns
EXCLUDE_PATTERNS=()
if [[ -f "$PROJECT_ROOT/.zipignore" ]]; then
    while IFS= read -r line; do
        # Skip empty lines and comments
        if [[ -n "$line" && ! "$line" =~ ^[[:space:]]*# ]]; then
            EXCLUDE_PATTERNS+=("--exclude=$line")
        fi
    done < "$PROJECT_ROOT/.zipignore"
fi

# Add package-type specific exclusions
case "$PACKAGE_TYPE" in
    "production")
        EXCLUDE_PATTERNS+=(
            "--exclude=tests/"
            "--exclude=docs/"
            "--exclude=scripts/mock_*"
            "--exclude=scripts/performance_*"
            "--exclude=*.md"
            "--exclude=mise.toml"
            "--exclude=pyproject.toml"
        )
        ;;
    "deployment")
        EXCLUDE_PATTERNS+=(
            "--exclude=tests/"
            "--exclude=scripts/mock_*"
        )
        ;;
esac

# Override exclusions based on flags
if [[ "$INCLUDE_TESTS" == "false" ]]; then
    EXCLUDE_PATTERNS+=("--exclude=tests/")
fi

if [[ "$INCLUDE_DOCS" == "false" ]]; then
    EXCLUDE_PATTERNS+=("--exclude=docs/")
fi

# Function to create file list
create_file_list() {
    cd "$PROJECT_ROOT"
    
    # Use find with exclusion patterns converted to find syntax
    local find_excludes=""
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
        # Convert zip exclude pattern to find exclude pattern
        local exclude_path="${pattern#--exclude=}"
        find_excludes="$find_excludes -not -path \"./$exclude_path\""
    done
    
    # Create comprehensive file list
    eval "find . -type f $find_excludes" | sort
}

# Function to show package contents
show_package_contents() {
    log_info "Package contents preview:"
    echo "----------------------------------------"
    create_file_list | head -20
    local total_files=$(create_file_list | wc -l)
    if [[ $total_files -gt 20 ]]; then
        echo "... and $((total_files - 20)) more files"
    fi
    echo "----------------------------------------"
    echo "Total files: $total_files"
}

# Dry run mode
if [[ "$DRY_RUN" == "true" ]]; then
    log_info "DRY RUN MODE - No files will be created"
    show_package_contents
    exit 0
fi

# Create the package
log_info "Creating package..."

cd "$PROJECT_ROOT"

# Create zip file with exclusions
zip -r "$PACKAGE_PATH" . "${EXCLUDE_PATTERNS[@]}" -q

# Verify package was created
if [[ -f "$PACKAGE_PATH" ]]; then
    PACKAGE_SIZE=$(du -h "$PACKAGE_PATH" | cut -f1)
    log_success "Package created successfully!"
    log_info "File: $PACKAGE_PATH"
    log_info "Size: $PACKAGE_SIZE"
    
    # Show package contents summary
    log_info "Package contains $(unzip -l "$PACKAGE_PATH" | tail -1 | awk '{print $2}') files"
    
    # Create checksum
    CHECKSUM=$(sha256sum "$PACKAGE_PATH" | cut -d' ' -f1)
    echo "$CHECKSUM  $PACKAGE_FILENAME" > "$OUTPUT_DIR/${PACKAGE_FILENAME}.sha256"
    log_info "Checksum: $CHECKSUM"
    
    # Create package manifest
    cat > "$OUTPUT_DIR/${PACKAGE_FILENAME}.manifest" << EOF
Package: $PACKAGE_NAME
Version: $VERSION
Type: $PACKAGE_TYPE
Created: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
Size: $PACKAGE_SIZE
SHA256: $CHECKSUM
Files: $(unzip -l "$PACKAGE_PATH" | tail -1 | awk '{print $2}')

Contents:
$(unzip -l "$PACKAGE_PATH" | head -20)
EOF
    
    log_success "Package manifest created: ${PACKAGE_FILENAME}.manifest"
    
else
    log_error "Failed to create package"
    exit 1
fi

# Optional: Create additional formats
if command -v tar &> /dev/null; then
    TAR_FILENAME="${PACKAGE_NAME}-${VERSION}-${PACKAGE_SUFFIX}-${TIMESTAMP}.tar.gz"
    TAR_PATH="$OUTPUT_DIR/$TAR_FILENAME"
    
    log_info "Creating tar.gz version..."
    
    # Create tar with same exclusions
    tar_excludes=""
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
        exclude_path="${pattern#--exclude=}"
        tar_excludes="$tar_excludes --exclude=$exclude_path"
    done
    
    eval "tar -czf '$TAR_PATH' $tar_excludes ."
    
    if [[ -f "$TAR_PATH" ]]; then
        TAR_SIZE=$(du -h "$TAR_PATH" | cut -f1)
        TAR_CHECKSUM=$(sha256sum "$TAR_PATH" | cut -d' ' -f1)
        echo "$TAR_CHECKSUM  $TAR_FILENAME" > "$OUTPUT_DIR/${TAR_FILENAME}.sha256"
        log_success "Tar package created: $TAR_FILENAME ($TAR_SIZE)"
    fi
fi

log_success "Packaging complete!"
log_info "Output directory: $OUTPUT_DIR"
log_info "Available packages:"
ls -la "$OUTPUT_DIR"/*"$VERSION"*"$TIMESTAMP"* 2>/dev/null || true
# Packaging Utilities

This directory contains utilities for creating clean distribution packages of the Air-Gapped RAG system.

## Files

### `.zipignore`
Defines patterns for files and directories to exclude when creating packages. Similar to `.gitignore` but specifically for distribution packages.

**Key exclusions:**
- Development artifacts (`__pycache__/`, `.pytest_cache/`, etc.)
- Build outputs (`cdk.out/`, `dist/`, etc.)
- Local configuration (`*.local.env`, `config/local.env`)
- Security files (`*.pem`, `*.key`, `*.crt`)
- Development tools (`.vscode/`, `.idea/`)
- Test files and documentation (configurable)

### `scripts/package.sh`
Advanced packaging script with multiple package types and options.

**Usage:**
```bash
# Create different package types
./scripts/package.sh source          # Full source package with tests and docs
./scripts/package.sh deployment      # Deployment-ready package
./scripts/package.sh production      # Minimal production package
./scripts/package.sh full           # Complete package with everything

# Options
./scripts/package.sh production --dry-run    # Preview contents
./scripts/package.sh deployment -o /tmp     # Custom output directory
./scripts/package.sh source --include-tests # Force include tests
```

**Package Types:**
- **source**: Complete source code with tests and documentation
- **deployment**: Ready-to-deploy package with documentation
- **production**: Minimal package for production deployment
- **full**: Everything included

### `scripts/zip_project.py`
Simple Python utility for quick packaging.

**Usage:**
```bash
# Quick package with timestamp
python scripts/zip_project.py

# Custom package name
python scripts/zip_project.py my-package-name

# Via main entry point
python main.py zip my-package
```

## Integration with Main Entry Point

The packaging utilities are integrated into the main entry point:

```bash
# Create packages via main.py
python main.py package production --dry-run
python main.py zip release-v1.0.0
```

## Package Contents

### What's Included (by default):
- Source code (`src/ai_inference/`)
- Configuration templates (`config/*.env`)
- Deployment scripts (`scripts/deploy.sh`, `scripts/setup_vpn.sh`)
- Service definitions (`systemd/`)
- Documentation (`docs/`)
- CDK infrastructure code
- Main entry points (`main.py`, `app.py`)

### What's Excluded:
- Development artifacts and caches
- Local configuration and secrets
- Build outputs and temporary files
- IDE and editor files
- Version control files
- Test outputs and reports
- Development-only scripts

### Package-Specific Exclusions:

**Production Package:**
- Tests and test directories
- Development documentation
- Mock and testing scripts
- Development configuration files

**Deployment Package:**
- Test directories
- Mock scripts only

**Source Package:**
- Includes everything for development

## Security Considerations

The `.zipignore` file ensures that sensitive information is never included in packages:

- **Secrets**: `*.pem`, `*.key`, `*.crt` files excluded
- **Local Config**: `*.local.env` files excluded
- **Development Data**: Test files and mock data excluded
- **Build Artifacts**: Temporary and cache files excluded

## Automation

These utilities can be integrated into CI/CD pipelines:

```yaml
# GitHub Actions example
- name: Create Production Package
  run: |
    ./scripts/package.sh production -o ./dist
    
- name: Upload Package
  uses: actions/upload-artifact@v3
  with:
    name: ai-inference-production
    path: ./dist/*.zip
```

## Verification

Each package includes:
- **SHA256 checksum** for integrity verification
- **Manifest file** with package contents and metadata
- **Size and file count** information

Example verification:
```bash
# Verify package integrity
sha256sum -c ai-inference-1.0.0-prod-20241201-143022.zip.sha256

# View package contents
unzip -l ai-inference-1.0.0-prod-20241201-143022.zip
```
#!/usr/bin/env python3
"""
Simple zip utility that respects .zipignore file
Usage: python zip_project.py [output_name]
"""

import os
import sys
import zipfile
import fnmatch
from pathlib import Path
from datetime import datetime

def read_zipignore(project_root):
    """Read .zipignore file and return list of patterns to exclude."""
    zipignore_path = project_root / '.zipignore'
    patterns = []
    
    if zipignore_path.exists():
        with open(zipignore_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith('#'):
                    patterns.append(line)
    
    return patterns

def should_exclude(file_path, exclude_patterns, project_root):
    """Check if file should be excluded based on patterns."""
    # Convert to relative path from project root
    try:
        rel_path = file_path.relative_to(project_root)
        rel_path_str = str(rel_path)
        
        # Check against each pattern
        for pattern in exclude_patterns:
            # Handle directory patterns
            if pattern.endswith('/'):
                if rel_path_str.startswith(pattern) or fnmatch.fnmatch(rel_path_str + '/', pattern):
                    return True
            # Handle file patterns
            elif fnmatch.fnmatch(rel_path_str, pattern):
                return True
            # Handle path patterns
            elif pattern in rel_path_str:
                return True
        
        return False
    except ValueError:
        # File is not under project root
        return True

def create_zip_package(project_root, output_name=None):
    """Create zip package excluding files listed in .zipignore."""
    
    if output_name is None:
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        output_name = f"ai-inference-{timestamp}.zip"
    
    if not output_name.endswith('.zip'):
        output_name += '.zip'
    
    # Read exclusion patterns
    exclude_patterns = read_zipignore(project_root)
    
    print(f"Creating package: {output_name}")
    print(f"Excluding {len(exclude_patterns)} patterns from .zipignore")
    
    # Create zip file
    with zipfile.ZipFile(output_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        files_added = 0
        files_excluded = 0
        
        for root, dirs, files in os.walk(project_root):
            root_path = Path(root)
            
            # Filter directories
            dirs[:] = [d for d in dirs if not should_exclude(root_path / d, exclude_patterns, project_root)]
            
            for file in files:
                file_path = root_path / file
                
                if should_exclude(file_path, exclude_patterns, project_root):
                    files_excluded += 1
                    continue
                
                # Add file to zip
                arcname = file_path.relative_to(project_root)
                zipf.write(file_path, arcname)
                files_added += 1
        
        print(f"✅ Package created successfully!")
        print(f"   Files included: {files_added}")
        print(f"   Files excluded: {files_excluded}")
        print(f"   Package size: {os.path.getsize(output_name) / 1024 / 1024:.1f} MB")
        
        # Create checksum
        import hashlib
        with open(output_name, 'rb') as f:
            checksum = hashlib.sha256(f.read()).hexdigest()
        
        checksum_file = output_name + '.sha256'
        with open(checksum_file, 'w') as f:
            f.write(f"{checksum}  {output_name}\\n")
        
        print(f"   Checksum file: {checksum_file}")
        print(f"   SHA256: {checksum[:16]}...")

def main():
    """Main entry point."""
    project_root = Path(__file__).parent.parent
    
    output_name = None
    if len(sys.argv) > 1:
        output_name = sys.argv[1]
    
    try:
        create_zip_package(project_root, output_name)
    except Exception as e:
        print(f"❌ Error creating package: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
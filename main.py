#!/usr/bin/env python3
"""
Air-Gapped RAG System Entry Point

Provides unified entry point for all system components.
"""

import sys
import os
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

def main():
    """Main entry point with command routing."""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
    
    command = sys.argv[1]
    args = sys.argv[2:]
    
    if command == "worker":
        from air_gapped_rag.core.worker import main as worker_main
        sys.argv = ["worker"] + args
        worker_main()
    elif command == "dashboard":
        from air_gapped_rag.dashboard import main as dashboard_main
        dashboard_main()
    elif command == "health":
        from scripts.health_monitor import main as health_main
        sys.argv = ["health"] + args
        health_main()
    elif command == "performance":
        from scripts.performance_monitor import main as perf_main
        sys.argv = ["performance"] + args
        perf_main()
    elif command == "deploy":
        import subprocess
        subprocess.run(["./scripts/deploy.sh"] + args)
    elif command == "package":
        import subprocess
        subprocess.run(["./scripts/package.sh"] + args)
    elif command == "zip":
        from scripts.zip_project import main as zip_main
        sys.argv = ["zip"] + args
        zip_main()
    else:
        print(f"Unknown command: {command}")
        print_usage()
        sys.exit(1)

def print_usage():
    """Print usage information."""
    print("""
Air-Gapped RAG System

Usage: python main.py <command> [args...]

Commands:
  worker [environment]     - Start the RAG worker process
  dashboard               - Start the Streamlit dashboard
  health [environment]    - Run health monitoring
  performance [env]       - Run performance monitoring
  deploy <env> <action>   - Deploy infrastructure
  package [type] [opts]   - Create distribution package
  zip [name]              - Create zip package

Examples:
  python main.py worker prod
  python main.py dashboard
  python main.py health dev --once
  python main.py deploy prod deploy
  python main.py package production
  python main.py zip my-package
""")

if __name__ == "__main__":
    main()
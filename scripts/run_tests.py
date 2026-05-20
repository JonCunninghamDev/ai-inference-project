#!/usr/bin/env python3
"""
Test runner for Air-Gapped RAG system.
Runs Priority 1 tests covering critical functionality.
"""
import sys
import subprocess
from pathlib import Path


def run_tests():
    """Run the test suite with appropriate configuration."""
    
    # Change to project directory
    project_root = Path(__file__).parent.parent
    
    # Test command with coverage
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/unit/test_config.py",
        "tests/unit/test_worker.py", 
        "tests/integration/test_health_monitoring.py",
        "-v",
        "--tb=short",
        "--no-header",
        "--disable-warnings"
    ]
    
    print("🧪 Running Priority 1 Tests for Air-Gapped RAG System")
    print("=" * 60)
    print("Testing critical paths:")
    print("  ✓ Configuration management and validation")
    print("  ✓ RAG worker core functionality")
    print("  ✓ Health monitoring endpoints")
    print("=" * 60)
    
    try:
        result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        if result.returncode == 0:
            print("\n✅ All Priority 1 tests passed!")
            print("\nNext steps:")
            print("  • Deploy to staging environment")
            print("  • Run integration tests with real AWS services")
            print("  • Monitor health endpoints in production")
        else:
            print(f"\n❌ Tests failed with exit code {result.returncode}")
            return False
            
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
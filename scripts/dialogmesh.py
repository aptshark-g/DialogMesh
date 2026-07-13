#!/usr/bin/env python
"""DialogMesh v4 CLI entry point."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent.v4.cli.main import main

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""DialogMesh v4 TUI launcher."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent.v4.tui.app import main
main()

import os
import sys

# Add the current directory to the Python module search path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from backend.app import app

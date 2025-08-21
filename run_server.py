#!/usr/bin/env python3
"""
Startup script for the Xero Payroll Automation API server.
This ensures the Python path is set correctly.
"""

import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Now import and run uvicorn
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "src.api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
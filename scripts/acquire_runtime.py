"""Job-owned trusted runtime controller entry point, no HTTP command endpoint."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.runtime import acquire
if __name__=='__main__':acquire(Path(sys.argv[1]),Path(sys.argv[2]))

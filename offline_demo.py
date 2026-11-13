"""Print a synthetic avatar message without opening sockets or calling providers."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent/'fastapi'))
from protocol import avatar_payload
if __name__ == '__main__':
    print(json.dumps(avatar_payload('Demo', 1.2, 'Happy'), indent=2))

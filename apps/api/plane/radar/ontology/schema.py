import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(Path(__file__).with_name("core-3.2.0.json").read_text())

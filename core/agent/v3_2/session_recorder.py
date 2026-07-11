"""Session recorder - structured turn data to JSONL files"""
import json, time, os

class SessionRecorder:
    """Writes structured per-turn data to JSONL for post-hoc analysis"""

    def __init__(self, log_dir="v32_logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.session_id = "session_" + str(int(time.time()))
        self.path = os.path.join(log_dir, self.session_id + ".jsonl")
        self.file = open(self.path, "w", encoding="utf-8")

    def record_turn(self, turn_data):
        self.file.write(json.dumps(turn_data, ensure_ascii=False) + "\n")
        self.file.flush()

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def get_path(self):
        return self.path
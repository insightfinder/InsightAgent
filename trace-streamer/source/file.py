import json
import os

from model import Span


class FileSource:
    def __init__(self, folder):
        self.folder = folder

    def get_spans(self):
        for filename in sorted(os.listdir(self.folder)):
            if not filename.endswith(".json"):
                continue

            path = os.path.join(self.folder, filename)
            with open(path, "r") as f:
                raw_spans = json.load(f)

            for raw_span in raw_spans:
                yield Span.from_dict(raw_span)

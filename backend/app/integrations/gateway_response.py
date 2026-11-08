"""Incrementally validate JSON without materializing discarded transport archives."""

import math
from decimal import Decimal

import ijson

READ_CHUNK_BYTES = 64 * 1024


def redacted_key(key):
    name = str(key).lower()
    return any(part in name for part in ("api_key", "apikey", "authorization", "password", "token")) or name in {
        "image", "images", "input_img", "output_img", "image_base64", "image_data",
        "base64", "input_image", "database_url",
    }


class EnvelopeParser:
    """Retain data/meta/error, validating even ignored JSON subtrees.

    A skip depth prevents numeric image tensors/extra transport fields becoming
    Python lists. Scalar strings can still allocate up to the response limit;
    this is a bounded transport, not a general heap-size guarantee.
    """

    def __init__(self, clean_string):
        self.value = None
        self.stack = []
        self.keys = []
        self.skip = 0
        self.clean_string = clean_string
        self.target = self._events()
        next(self.target)
        self.parser = ijson.basic_parse_coro(self.target)

    def _attach(self, value):
        if not self.stack:
            self.value = value
        elif isinstance(self.stack[-1], list):
            self.stack[-1].append(value)
        else:
            self.stack[-1][self.keys[-1]] = value

    def _events(self):
        while True:
            event, value = yield
            if self.skip:
                if event in {"start_map", "start_array"}:
                    self.skip += 1
                elif event in {"end_map", "end_array"}:
                    self.skip -= 1
                continue
            if event == "map_key":
                self.keys[-1] = value
                continue
            if event in {"end_map", "end_array"}:
                self.stack.pop()
                self.keys.pop()
                continue
            key = self.keys[-1] if self.stack and isinstance(self.stack[-1], dict) else None
            discard = len(self.stack) == 1 and key not in {"data", "meta", "error"}
            redact = key is not None and redacted_key(key)
            if discard or redact:
                if redact and not discard:
                    self._attach("[redacted]")
                if event in {"start_map", "start_array"}:
                    self.skip = 1
                continue
            if event in {"start_map", "start_array"}:
                container = {} if event == "start_map" else []
                self._attach(container)
                self.stack.append(container)
                self.keys.append(None)
            else:
                if isinstance(value, Decimal):
                    value = float(value)
                if isinstance(value, float) and not math.isfinite(value):
                    value = None
                if isinstance(value, str):
                    value = self.clean_string(value)
                self._attach(value)

    def feed(self, chunk):
        self.parser.send(chunk)

    def finish(self):
        self.parser.close()  # Reject incomplete/trailing JSON, including skipped fields.
        return self.value

    def close(self):
        self.target.close()
        self.parser = None
        self.stack.clear()
        self.value = None

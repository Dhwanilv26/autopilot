from collections import deque
from typing import Any, Optional, Tuple
import hashlib  # like bcrpyt
import json
import difflib


class LoopDetector:
    def __init__(self):

        self.max_exact_repeats = 3  # for A->A->A
        self.max_cycle_length = 3  # for A->B->C->A->B->C
        self.similarity_threshold = 0.9  # isse jyaada similar to sab same hi ginenge

        # Store (hash, semantic_text)
        self._history: deque[Tuple[str, str]] = deque(maxlen=20)

        # Store last tool result to pair with next call
        self._last_tool_result: Optional[str] = None

    def _normalize(self, text: str) -> str:
        return text.strip().lower()

    def _normalize_args(self, args: dict) -> str:
        normalized = {}

        for k in sorted(args.keys()):
            v = args[k]

            if isinstance(v, str):
                v = self._normalize(v)

            normalized[k] = v

        # json.dumps() -> returns str, loads() returns in dict/str
        return json.dumps(normalized, sort_keys=True)

    def _hash(self, text: str) -> str:
        # hexdigest returns in human readable format (in str) unlike digest which returns in bytes
        return hashlib.sha256(text.encode()).hexdigest()

    def _is_similar(self, a: str, b: str) -> bool:
        return difflib.SequenceMatcher(None, a, b).ratio() >= self.similarity_threshold

    def record_action(self, action_type: str, **details: Any):
        parts = [action_type]

        if action_type == "tool_call":
            tool_name = details.get("tool_name", "")
            args = details.get("args", {})

            parts.append(tool_name)

            if isinstance(args, dict):
                parts.append(self._normalize_args(args))

            # Include previous result (pairing) to detect ineffective and repeating actions giving "no results" or something like that
            if self._last_tool_result:
                parts.append(f"prev_result={self._last_tool_result}")

        elif action_type == "tool_result":
            result = details.get("result", "")
            normalized_result = self._normalize(str(result))

            # Store separately for next tool call
            self._last_tool_result = normalized_result

            parts.append(normalized_result)

        elif action_type == "response":
            text = details.get("text", "")
            normalized_text = self._normalize(text)
            parts.append(normalized_text)

        # Create signature
        semantic_text = "|".join(parts)
        signature_hash = self._hash(semantic_text)

        self._history.append((signature_hash, semantic_text))

    def check_for_loop(self) -> Optional[str]:

        if len(self._history) < 2:
            return None

        history = list(self._history)

        # -----------------------------
        # 1. Exact repetition (hash-based) to mtlb semantic text bhi same hi hoga
        # -----------------------------
        if len(history) >= self.max_exact_repeats:
            recent = history[-self.max_exact_repeats:]
            hashes = [h[0] for h in recent]

            # h[0] -> hash value, h[1] -> semantic text

            if len(set(hashes)) == 1:
                return f"exact same action repeated {self.max_exact_repeats} times"

        # -----------------------------
        # 2. Semantic repetition
        # -----------------------------
        if len(history) >= self.max_exact_repeats:
            recent = history[-self.max_exact_repeats:]
            # texts is derived from (hash,semantic text) ka semantic text
            texts = [h[1] for h in recent]
            # just comparing texts[0] with everyother text
            if all(self._is_similar(texts[0], t) for t in texts[1:]):
                return f"semantically similar action repeated {self.max_exact_repeats} times"

            # "AI"->"AI"->"AI" same aa gaya ki nai (recent history mai)

        # -----------------------------
        # 3. Cycle detection (hash-based)
        # -----------------------------
        for cycle_len in range(2, min(self.max_cycle_length + 1, len(history) // 2 + 1)):
            recent = history[-cycle_len * 2:]

            first_half = [h[0] for h in recent[:cycle_len]]
            second_half = [h[0] for h in recent[cycle_len:]]

            if first_half == second_half:
                return f"detected repeating cycle of length {cycle_len}"

        # -----------------------------
        # 4. Semantic cycle detection
        # -----------------------------
        for cycle_len in range(2, min(self.max_cycle_length + 1, len(history) // 2 + 1)):
            recent = history[-cycle_len * 2:]

            first_half = [h[1] for h in recent[:cycle_len]]
            second_half = [h[1] for h in recent[cycle_len:]]

            if all(self._is_similar(a, b) for a, b in zip(first_half, second_half)):
                return f"detected semantically similar cycle of length {cycle_len}"

        return None

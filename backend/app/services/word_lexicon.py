"""Read-only newmm dictionary: identical prefixes without a node per character."""
from bisect import bisect_left
from functools import lru_cache

from pythainlp.corpus import thai_words


class SortedLexicon:
    """Implement newmm's prefix lookup over the same stripped dictionary words.

    PyThaiNLP5.3.4's newmm consumes only len() and prefixes(text,start). Its
    default Trie retains hundreds of thousands of Python nodes/dicts. A sorted
    tuple retains the corpus strings and uses binary search, preserving ascending
    prefix length and every tokenization decision. No dictionary words are removed.
    """

    def __init__(self, words):
        self.words = tuple(sorted({word.strip() for word in words}))
        self.max_length = max(map(len, self.words), default=0)

    def __len__(self):
        return len(self.words)

    def prefixes(self, text, start=0):
        matches = []
        lower = 0
        for end in range(start + 1, min(len(text), start + self.max_length) + 1):
            prefix = text[start:end]
            lower = bisect_left(self.words, prefix, lo=lower)
            if lower == len(self.words) or not self.words[lower].startswith(prefix):
                break
            if self.words[lower] == prefix:
                matches.append(prefix)
        return matches


@lru_cache(maxsize=1)
def thai_lexicon():
    return SortedLexicon(thai_words())

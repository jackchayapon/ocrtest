import random
from concurrent.futures import ThreadPoolExecutor

import pytest
from pythainlp.corpus import thai_words
from pythainlp.tokenize import word_tokenize
from pythainlp.util import Trie

from app.services.metrics_service import calculate_wer, normalize_text, tokenize_words
from app.services.word_lexicon import SortedLexicon, thai_lexicon


def test_every_corpus_word_prefix_matches_original_trie():
    words = thai_words()
    reference = Trie(words)
    compact = thai_lexicon()
    assert len(compact) == len(reference)
    # Every word exercises all shorter dictionary prefixes too. Non-zero starts
    # cover newmm's indexed lookup rather than only whole-string tokenization.
    for word in words:
        assert compact.prefixes(word) == reference.prefixes(word)
        assert compact.prefixes("123" + word + "!", 3) == reference.prefixes("123" + word + "!", 3)


def test_unicode_prefix_edges_and_immutable_concurrent_reads():
    words = ["", " a ", "abc", "ab", "ก", "ก่", "กำ", "\U0010ffff", "\U0010ffffx", "a"]
    compact, reference = SortedLexicon(words), Trie(words)
    texts = ["", "a", "abcd", "ก่ำ", "กำก", "?", "\U0010ffffx!", " ก"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        actual = list(pool.map(compact.prefixes, texts * 10))
    assert actual == [reference.prefixes(text) for text in texts * 10]
    for text in texts:
        for start in range(len(text) + 1):
            assert compact.prefixes(text, start) == reference.prefixes(text, start)


@pytest.mark.parametrize("text", [
    "บริษัท ซีดีจี จำกัด เลขที่ 2026/4587 วันที่ 12 เมษายน 2567 ยอดรวม 12,450 บาท",
    "ก ก่ ก้ ก๊ ก๋ กำ เก้า กิ กี กึ กื กุ กู ก์",
    "ภาษาไทยไม่มีช่องว่างระหว่างคำและคำที่ไม่อยู่ในพจนานุกรมกขฃคฅฆ",
    "OCR English ABC123 12.50 foo-bar\n\tทดสอบ🙂中文",
    "", "ก" * 1000,
])
def test_newmm_tokens_and_wer_counts_unchanged(text):
    normalized = normalize_text(text)
    expected = [word for word in word_tokenize(normalized, engine="newmm") if word.strip()]
    assert tokenize_words(text) == expected
    assert calculate_wer(text, text, return_counts=True) == (0.0, 0, len(expected))


def test_random_corpus_joinings_preserve_token_order():
    rng = random.Random(20261110)
    words = sorted(thai_words())
    for _ in range(200):
        text = "".join(rng.sample(words, 8)) + " OCR123 ๙๘๗"
        assert word_tokenize(text, engine="newmm", custom_dict=thai_lexicon()) == word_tokenize(text, engine="newmm")

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from enrich_master import derive_section_part, parse_gemini_enrichment

def test_derive_section_part():
    assert derive_section_part(1)    == (1, 1)
    assert derive_section_part(100)  == (1, 1)
    assert derive_section_part(101)  == (2, 1)
    assert derive_section_part(800)  == (8, 1)
    assert derive_section_part(801)  == (9, 2)
    assert derive_section_part(1500) == (15, 2)
    assert derive_section_part(1501) == (16, 3)
    assert derive_section_part(1900) == (19, 3)

def test_parse_gemini_enrichment_valid():
    raw = '{"pos": "verb", "sentence": "I create art.", "sentence_ja": "私は芸術を創ります。"}'
    result = parse_gemini_enrichment(raw)
    assert result["pos"] == "verb"
    assert "create" in result["sentence"]

def test_parse_gemini_enrichment_with_markdown():
    raw = '```json\n{"pos": "noun", "sentence": "The store is open.", "sentence_ja": "店は開いています。"}\n```'
    result = parse_gemini_enrichment(raw)
    assert result["pos"] == "noun"

def test_parse_gemini_enrichment_invalid_returns_none():
    assert parse_gemini_enrichment("broken {{{") is None

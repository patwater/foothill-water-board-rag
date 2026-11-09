from wbrag import chunk


def test_headings_split_only_when_chunk_is_big_enough():
    text = "INTRODUCTION OF ADDITIONAL AGENDA ITEMS\nNone requested.\n\nBWP OPERATIONS AND FINANCIAL REPORTS\nRetail load was lower."
    chunks, section = chunk.page_chunks(text, "")
    assert len(chunks) == 1  # both sections are tiny, so they stay together
    assert chunks[0][0] == "INTRODUCTION OF ADDITIONAL AGENDA ITEMS"
    assert "Retail load" in chunks[0][1]


def test_long_page_is_packed_under_max_and_never_loses_text():
    para = " ".join(f"Sentence number {i} about water rates." for i in range(400))
    chunks, _ = chunk.page_chunks(para, "")
    assert len(chunks) > 1
    assert all(chunk.ntok(t) <= chunk.MAX for _, t in chunks)
    assert sum(t.count("Sentence number") for _, t in chunks) == 400


def test_section_carries_across_pages():
    _, sec = chunk.page_chunks("ATTACHMENT A\n" + "word " * 300, "")
    chunks, _ = chunk.page_chunks("continued text on the next page", sec)
    assert chunks[0][0] == "ATTACHMENT A"


def test_authority_tiers():
    assert chunk.tier("minutes_adopted", "live") == 1
    assert chunk.tier("staff_report", "live") == 2
    assert chunk.tier("agenda", "live") == 3
    assert chunk.tier("minutes_adopted", "wayback") == 5

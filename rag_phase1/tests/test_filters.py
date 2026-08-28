from app.retrieval import matches_filters


ITEM = {
    "document_type": "legal",
    "source_file": "PflBG.html",
    "content_type": "checklist_item",
    "structure": {"section": "§ 4"},
}


def test_matches_top_level_and_nested_fields() -> None:
    assert matches_filters(ITEM, {"document_type": "LEGAL", "structure.section": "§ 4"})


def test_requires_all_filters_to_match() -> None:
    assert not matches_filters(ITEM, {"document_type": "legal", "source_file": "PflAPrV.html"})

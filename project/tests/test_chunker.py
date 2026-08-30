from ingestion.chunker import HeadingAwareChunker
from ingestion.models import DocumentUnit, ParsedDocument


class ChunkSettings:
    parent_chunk_size = 40
    child_chunk_size = 20
    child_chunk_overlap = 5


def test_heading_and_locator_are_preserved():
    document = ParsedDocument(
        doc_id="doc-1",
        source="policy.docx",
        file_type=".docx",
        units=[DocumentUnit(text="第一条规定。" * 10, heading="报销 > 住宿", locator="page:2")],
    )
    chunks = HeadingAwareChunker(ChunkSettings()).split(document)
    assert len(chunks) > 1
    assert all(chunk.heading == "报销 > 住宿" for chunk in chunks)
    assert all(chunk.locator == "page:2" for chunk in chunks)
    assert len({chunk.id for chunk in chunks}) == len(chunks)


def test_children_map_to_complete_parents():
    document = ParsedDocument(
        doc_id="a" * 24,
        source="policy.txt",
        file_type=".txt",
        units=[DocumentUnit(text="甲乙丙丁戊己庚辛壬癸" * 8, heading="制度")],
    )
    parents, children = HeadingAwareChunker(ChunkSettings()).split_parent_child(document)
    by_id = {parent.parent_id: parent for parent in parents}

    assert parents
    assert children
    assert all(child.parent_id in by_id for child in children)
    assert all(child.text in by_id[child.parent_id].text for child in children)


def test_sliding_window_has_overlap():
    windows = HeadingAwareChunker._windows("0123456789ABCDEFGHIJ", size=10, overlap=2)
    assert windows == ["0123456789", "89ABCDEFGH", "GHIJ"]

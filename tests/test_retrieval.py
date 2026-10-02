import pytest

from hello_support.retrieval import KB_DIR, chunk_markdown, load_chunks


def test_chunks_are_split_by_section_with_doc_title():
    chunks = chunk_markdown(KB_DIR / "postgres_connection.md")
    assert [c.section for c in chunks] == ["Symptoms", "Checks", "Service status", "Limits"]
    assert chunks[2].chunk_id == "postgres_connection.md#Service status"
    assert chunks[2].text.startswith("PostgreSQL: application cannot connect - Service status\n")
    assert "## " not in chunks[0].text


def test_knowledge_base_has_three_sheets_with_unique_ids():
    chunks = load_chunks()
    assert {c.doc_id for c in chunks} == {
        "postgres_connection.md", "nginx_unavailable.md", "redis_unreachable.md"}
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids)) == 12


@pytest.mark.models
def test_search_end_to_end(tmp_path):
    from hello_support.retrieval import Retriever

    r = Retriever(chroma_dir=tmp_path)
    hits = r.search("connexion refusée postgres")
    assert len(hits) == 2
    assert all(h.doc_id == "postgres_connection.md" and h.relevant for h in hits)
    assert hits[0].rerank_score >= hits[1].rerank_score
    assert not any(h.relevant for h in r.search("Kafka consumer lag is growing"))
    with pytest.raises(ValueError):
        r.search("   ")

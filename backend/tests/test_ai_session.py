from backend.app.ai.schemas import ConversationTurn
from backend.app.ai.session import InMemoryConversationStore


def test_conversation_store_keeps_only_bounded_small_turns():
    store = InMemoryConversationStore(max_turns=3, max_sessions=2)
    session_id = store.create_session()
    for index in range(5):
        store.append(
            session_id,
            ConversationTurn(
                query=f"question {index}",
                tool="get_overview",
                arguments={},
                result_summary={"total_records": index},
            ),
        )
    history = store.history(session_id)
    assert len(history) == 3
    assert history[0].query == "question 2"
    assert history[-1].result_summary == {"total_records": 4}

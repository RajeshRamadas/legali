def _chat(client, message):
    response = client.post("/api/v1/chat", json={"message": message})
    assert response.status_code == 200
    return response.json()

def test_chat_suggests_a_service(client):
    body = _chat(client, "Is this property safe to buy?")
    assert body["action"] == "request"
    assert body["service"]["slug"] == "title-verification"

def test_chat_prefers_most_specific_topic(client):
    assert _chat(client, "We need bulk registration for 80 units")["service"]["slug"] == "bulk-registration-operations"
    assert _chat(client, "How much does the Pro package cost?")["service"]["slug"] == "legal-due-diligence"

def test_chat_tracking_extracts_ticket_number(client):
    body = _chat(client, "what is the status of hx-261018-abc123")
    assert body["action"] == "track"
    assert body["ticket_number"] == "HX-261018-ABC123"

def test_chat_fallback_offers_callback(client):
    body = _chat(client, "qwerty")
    assert body["service"]["slug"] == "general-guidance"

"""GET /flights through the real AmadeusProvider; only the gateway is mocked."""

from tests.amadeus_fixtures import AIRLINES, SEARCH, TEST_API_KEY, standard_gateway

PARAMS = {"origin": "TLV", "destination": "MAD", "date": "2099-01-01"}


def test_search_resolves_names_and_returns_deep_links(client, use_provider):
    gw = standard_gateway()
    use_provider(gw.provider())

    response = client.get("/flights/", params=PARAMS)

    assert response.status_code == 200
    results = response.json()["results"]
    assert [r["price"] for r in results] == [199.0, 250.5, 410.0]
    assert results[1]["primary_airline"] == "El Al Israel Airlines"
    assert results[1]["deep_link"] == "https://example.test/LY/book"
    assert results[0]["deep_link"] is None
    assert TEST_API_KEY not in response.text


def test_repeated_search_costs_one_search_and_one_airline_lookup(client, use_provider):
    gw = standard_gateway()
    use_provider(gw.provider())
    for _ in range(3):
        client.get("/flights/", params=PARAMS)
    assert len(gw.calls(SEARCH)) == 1
    assert len(gw.calls(AIRLINES)) == 1


def test_searched_offer_can_be_booked(client, use_provider):
    use_provider(standard_gateway().provider())
    offer = client.get("/flights/", params=PARAMS).json()["results"][1]

    response = client.post(
        "/bookings/",
        json={
            "offer_id": offer["offer_id"],
            "passenger": {"first_name": "Jane", "last_name": "Doe", "date_of_birth": "1990-01-01"},
            "contact_email": "jane@example.com",
        },
    )
    assert response.status_code == 201
    assert response.json()["snapshot"]["deep_link"] == offer["deep_link"]

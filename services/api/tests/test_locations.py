"""GET /locations: the typeahead endpoint, end to end with a mocked gateway."""

from shared.providers import ProviderRateLimitedError
from tests.amadeus_fixtures import LOCATIONS, TEST_API_KEY, standard_gateway
from tests.test_flights import StubProvider


def test_returns_airports_and_cities_with_search_codes(client, use_provider):
    gw = standard_gateway()
    use_provider(gw.provider())

    response = client.get("/locations", params={"keyword": "madrid"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert [(r["sub_type"], r["search_code"]) for r in results] == [
        ("CITY", "MAD"),
        ("AIRPORT", "MAD+"),
    ]
    # The key is sent to the gateway, never back to the browser.
    assert gw.calls(LOCATIONS)[0].headers["X-API-Key"] == TEST_API_KEY
    assert TEST_API_KEY not in response.text


def test_repeated_keyword_hits_the_cache(client, use_provider):
    gw = standard_gateway()
    use_provider(gw.provider())
    client.get("/locations", params={"keyword": "Madrid"})
    client.get("/locations", params={"keyword": "madrid "})
    assert len(gw.calls(LOCATIONS)) == 1


def test_one_character_returns_empty_without_calling(client, use_provider):
    gw = standard_gateway()
    use_provider(gw.provider())
    response = client.get("/locations", params={"keyword": "m"})
    assert response.json() == {"results": []}
    assert gw.calls(LOCATIONS) == []


def test_missing_keyword_is_422(client, use_provider):
    use_provider(StubProvider())
    assert client.get("/locations").status_code == 422


def test_rate_limit_maps_to_503(client, use_provider):
    use_provider(StubProvider(error=ProviderRateLimitedError("quota", retry_after=5)))
    response = client.get("/locations", params={"keyword": "mad"})
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"

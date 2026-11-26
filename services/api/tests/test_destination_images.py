"""Destination photos: the Pixabay provider, and GET /destination-image[/file].

No test talks to Pixabay: every request goes through httpx.MockTransport.
"""

import logging

import httpx
import pytest
import redis

from app.main import app
from shared import cache
from shared.images import ImageProviderError, get_image_provider
from shared.images.pixabay import MAX_IMAGE_BYTES, PixabayProvider

# Distinctive on purpose: the tests search every log line and response for it.
SECRET = "pixabay-secret-key-9f8e7d"
JPEG = b"\xff\xd8\xff\xe0" + b"x" * 1000
PAGE_URL = "https://pixabay.com/photos/hanoi-lake-1234/"
IMAGE_URL = "https://pixabay.com/get/abc_1280.jpg"


def hit(**extra) -> dict:
    return {
        "id": 1234,
        "pageURL": PAGE_URL,
        "user": "Jane",
        "largeImageURL": IMAGE_URL,
        **extra,
    }


def search_body(*hits) -> dict:
    return {"total": len(hits), "totalHits": len(hits), "hits": list(hits)}


class FakePixabay:
    """An httpx.MockTransport: `searches` are answered in order, images by URL."""

    def __init__(self, searches=(), image=None):
        self.searches = list(searches)
        self.image = image if image is not None else httpx.Response(
            200, content=JPEG, headers={"content-type": "image/jpeg"}
        )
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/api/":
            item = self.searches.pop(0)
            if isinstance(item, Exception):
                raise item
            return item if isinstance(item, httpx.Response) else httpx.Response(200, json=item)
        return self.image

    @property
    def search_requests(self):
        return [r for r in self.requests if r.url.path == "/api/"]

    def provider(self) -> PixabayProvider:
        return PixabayProvider(SECRET, transport=httpx.MockTransport(self))


@pytest.fixture
def use_images():
    def _use(provider):
        app.dependency_overrides[get_image_provider] = lambda: provider
        return provider

    yield _use
    app.dependency_overrides.pop(get_image_provider, None)


def get_image(client, city="Hanoi", country="Vietnam"):
    return client.get("/destination-image", params={"city": city, "country": country})


# --- Provider ----------------------------------------------------------------


def test_search_uses_the_documented_parameters():
    fake = FakePixabay([search_body(hit())])
    image = fake.provider().find_destination_image("Hanoi", "Vietnam")

    assert image.data == JPEG and image.content_type == "image/jpeg"
    assert image.credit_user == "Jane" and image.credit_url == PAGE_URL
    params = dict(fake.search_requests[0].url.params)
    assert params == {
        "key": SECRET,
        "q": "Hanoi Vietnam",
        "image_type": "photo",
        "orientation": "horizontal",
        "category": "travel",
        "order": "popular",
        "safesearch": "true",
        "min_width": "1200",
        "per_page": "5",
    }


def test_the_image_download_does_not_carry_the_key():
    fake = FakePixabay([search_body(hit())])
    fake.provider().find_destination_image("Hanoi", "Vietnam")
    download = fake.requests[-1]
    assert str(download.url) == IMAGE_URL
    assert SECRET not in str(download.url) and SECRET not in str(download.headers)


def test_empty_category_retries_with_places():
    fake = FakePixabay([search_body(), search_body(hit())])
    assert fake.provider().find_destination_image("Hanoi", "Vietnam") is not None
    assert [r.url.params["category"] for r in fake.search_requests] == ["travel", "places"]
    assert fake.search_requests[1].url.params["q"] == "Hanoi Vietnam"


def test_no_city_result_falls_back_to_the_country():
    fake = FakePixabay([search_body(), search_body(), search_body(hit())])
    assert fake.provider().find_destination_image("Smalltown", "Vietnam") is not None
    queries = [r.url.params["q"] for r in fake.search_requests]
    assert queries == ["Smalltown Vietnam", "Smalltown Vietnam", "Vietnam"]


def test_nothing_found_returns_none():
    fake = FakePixabay([search_body()] * 4)
    assert fake.provider().find_destination_image("Nowhere", "Nowhereland") is None
    assert len(fake.search_requests) == 4


def test_country_only_is_not_searched_twice():
    fake = FakePixabay([search_body()] * 2)
    assert fake.provider().find_destination_image("Vietnam", "") is None
    assert len(fake.search_requests) == 2


def test_first_result_is_the_one_used():
    first = hit(user="First", pageURL="https://pixabay.com/photos/first-1/")
    second = hit(user="Second")
    image = FakePixabay([search_body(first, second)]).provider().find_destination_image("a", "b")
    assert image.credit_user == "First"


def test_oversize_image_is_rejected_by_declared_length():
    fake = FakePixabay(
        [search_body(hit())],
        httpx.Response(
            200,
            content=b"x",
            headers={"content-type": "image/jpeg", "content-length": str(MAX_IMAGE_BYTES + 1)},
        ),
    )
    assert fake.provider().find_destination_image("Hanoi", "Vietnam") is None


def test_oversize_image_is_rejected_while_streaming():
    big = httpx.Response(
        200, content=b"x" * (MAX_IMAGE_BYTES + 1), headers={"content-type": "image/jpeg"}
    )
    fake = FakePixabay([search_body(hit())], big)
    assert fake.provider().find_destination_image("Hanoi", "Vietnam") is None


@pytest.mark.parametrize("content_type", ["text/html", "image/svg+xml", ""])
def test_non_raster_content_type_is_rejected(content_type):
    page = httpx.Response(200, content=b"<html>", headers={"content-type": content_type})
    fake = FakePixabay([search_body(hit())], page)
    assert fake.provider().find_destination_image("Hanoi", "Vietnam") is None


def test_urls_outside_pixabay_are_refused():
    evil = hit(largeImageURL="https://evil.example/x.jpg")
    with pytest.raises(ImageProviderError):
        FakePixabay([search_body(evil)]).provider().find_destination_image("a", "b")
    evil = hit(pageURL="javascript:alert(1)")
    with pytest.raises(ImageProviderError):
        FakePixabay([search_body(evil)]).provider().find_destination_image("a", "b")


def test_429_raises_a_provider_error():
    fake = FakePixabay([httpx.Response(429, text="API rate limit exceeded")])
    with pytest.raises(ImageProviderError, match="rate limit"):
        fake.provider().find_destination_image("Hanoi", "Vietnam")


def test_timeout_error_does_not_contain_the_key():
    fake = FakePixabay([httpx.ReadTimeout("boom", request=httpx.Request("GET", "https://x/?key=" + SECRET))])
    with pytest.raises(ImageProviderError) as raised:
        fake.provider().find_destination_image("Hanoi", "Vietnam")
    assert SECRET not in str(raised.value)
    assert raised.value.__cause__ is None and raised.value.__suppress_context__


def test_network_error_does_not_contain_the_key():
    error = httpx.ConnectError("failed for https://pixabay.com/api/?key=" + SECRET)
    with pytest.raises(ImageProviderError) as raised:
        FakePixabay([error]).provider().find_destination_image("Hanoi", "Vietnam")
    assert SECRET not in str(raised.value)
    assert raised.value.__cause__ is None and raised.value.__suppress_context__


def test_key_never_reaches_any_log_record(caplog):
    caplog.set_level(logging.DEBUG)
    for logger in ("httpx", "httpcore"):
        logging.getLogger(logger).setLevel(logging.DEBUG)
    fake = FakePixabay([search_body(hit()), httpx.Response(429), search_body(hit())])
    provider = fake.provider()
    provider.find_destination_image("Hanoi", "Vietnam")
    with pytest.raises(ImageProviderError):
        provider.find_destination_image("Delhi", "India")

    # httpx did log the requests (so the test would catch a leak) ...
    assert any("HTTP Request" in r.getMessage() for r in caplog.records)
    # ... but not the key.
    assert all(SECRET not in r.getMessage() for r in caplog.records)
    assert SECRET not in caplog.text


# --- GET /destination-image ---------------------------------------------------


def test_found_photo_is_cached_and_served(client, use_images, fake_redis):
    fake = FakePixabay([search_body(hit())])
    use_images(fake.provider())

    body = get_image(client).json()
    assert body == {
        "available": True,
        "url": "/destination-image/file/hanoi_vietnam",
        "credit_user": "Jane",
        "credit_url": PAGE_URL,
    }

    file = client.get(body["url"])
    assert file.status_code == 200
    assert file.content == JPEG
    assert file.headers["content-type"] == "image/jpeg"
    assert file.headers["cache-control"] == "public, max-age=86400"

    # Second request: Redis only, no new Pixabay traffic.
    assert get_image(client).json()["available"] is True
    assert len(fake.requests) == 2  # one search + one download


def test_key_is_normalized(client, use_images):
    fake = FakePixabay([search_body(hit())])
    use_images(fake.provider())
    first = get_image(client, "  Bogotá ", "Colombia").json()
    second = get_image(client, "bogota", "COLOMBIA").json()
    assert first["url"] == second["url"] == "/destination-image/file/bogota_colombia"
    assert len(fake.search_requests) == 1


def test_found_via_country_fallback(client, use_images):
    fake = FakePixabay([search_body(), search_body(), search_body(hit())])
    use_images(fake.provider())
    assert get_image(client, "Smalltown", "Vietnam").json()["available"] is True


def test_not_found_is_cached(client, use_images, fake_redis):
    fake = FakePixabay([search_body()] * 4)
    use_images(fake.provider())

    assert get_image(client, "Nowhere", "Nowhereland").json() == {
        "available": False,
        "url": None,
        "credit_user": None,
        "credit_url": None,
    }
    assert len(fake.search_requests) == 4
    assert get_image(client, "Nowhere", "Nowhereland").json()["available"] is False
    assert len(fake.search_requests) == 4  # answered from Redis
    assert client.get("/destination-image/file/nowhere_nowhereland").status_code == 404


def test_ttls(client, use_images, monkeypatch):
    ttls = {}
    real = cache.set_json
    monkeypatch.setattr(cache, "set_json", lambda k, v, ttl: (ttls.update({k: ttl}), real(k, v, ttl)))
    use_images(FakePixabay([search_body(hit())] + [search_body()] * 4).provider())

    get_image(client, "Hanoi", "Vietnam")
    get_image(client, "Nowhere", "Nowhereland")
    assert ttls["destination-image:hanoi_vietnam"] == 30 * 86400
    assert ttls["destination-image:nowhere_nowhereland"] == 7 * 86400


def test_rate_limit_answers_no_photo_and_is_not_cached(client, use_images, fake_redis):
    fake = FakePixabay([httpx.Response(429), search_body(hit())])
    use_images(fake.provider())

    assert get_image(client).json()["available"] is False
    assert fake_redis.store == {}
    assert get_image(client).json()["available"] is True  # tried again, now works


def test_timeout_answers_no_photo_and_is_not_cached(client, use_images, fake_redis):
    use_images(FakePixabay([httpx.ReadTimeout("slow")]).provider())
    response = get_image(client)
    assert response.status_code == 200 and response.json()["available"] is False
    assert fake_redis.store == {}


def test_oversize_image_answers_no_photo(client, use_images):
    big = httpx.Response(200, content=b"x" * (MAX_IMAGE_BYTES + 1), headers={"content-type": "image/jpeg"})
    use_images(FakePixabay([search_body(hit())], big).provider())
    assert get_image(client).json()["available"] is False


def test_without_an_api_key_there_are_no_photos(client, use_images):
    use_images(None)
    response = get_image(client)
    assert response.status_code == 200 and response.json()["available"] is False


def test_redis_down_answers_no_photo_without_calling_pixabay(client, use_images, monkeypatch):
    class DownRedis:
        def get(self, *a, **k):
            raise redis.ConnectionError("down")

        set = get

    monkeypatch.setattr(cache, "redis_client", DownRedis())
    fake = FakePixabay([search_body(hit())])
    use_images(fake.provider())

    response = get_image(client)
    assert response.status_code == 200 and response.json()["available"] is False
    assert fake.requests == []
    assert client.get("/destination-image/file/hanoi_vietnam").status_code == 404


def test_redis_write_failure_answers_no_photo(client, use_images, fake_redis, monkeypatch):
    def fail(*a, **k):
        raise redis.ConnectionError("down")

    monkeypatch.setattr(fake_redis, "set", fail)
    use_images(FakePixabay([search_body(hit())]).provider())
    assert get_image(client).json()["available"] is False


def test_key_is_in_no_response_and_no_log(client, use_images, caplog):
    caplog.set_level(logging.DEBUG)
    logging.getLogger("httpx").setLevel(logging.DEBUG)
    use_images(FakePixabay([search_body(hit()), httpx.Response(429)]).provider())

    responses = [get_image(client), get_image(client, "Delhi", "India")]
    responses.append(client.get("/destination-image/file/hanoi_vietnam"))
    for response in responses:
        assert SECRET not in response.text and SECRET not in str(response.headers)
    assert SECRET not in caplog.text


def test_city_is_required_and_blank_is_rejected(client, use_images):
    use_images(None)
    assert client.get("/destination-image").status_code == 422
    assert client.get("/destination-image", params={"city": "   "}).json() == {
        "error": "invalid_destination"
    }


def test_non_latin_names_get_a_stable_key(client, use_images):
    use_images(FakePixabay([search_body(hit())]).provider())
    url = get_image(client, "東京", "日本").json()["url"]
    assert url.startswith("/destination-image/file/x") and client.get(url).status_code == 200


# --- GET /destination-image/file/{key} -------------------------------------------


def test_file_404_when_not_cached(client):
    response = client.get("/destination-image/file/hanoi_vietnam")
    assert response.status_code == 404 and response.json() == {"error": "image_not_found"}


@pytest.mark.parametrize("key", ["Hanoi", "a%20b", "x" * 101])
def test_file_rejects_keys_that_are_not_ours(client, key):
    assert client.get(f"/destination-image/file/{key}").status_code == 422

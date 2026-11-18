from __future__ import annotations

import datetime as dt
import io
import json
import urllib.error

import pytest

from app.integrations import store_api
from app.integrations.store_api import StoreApiClient, StoreApiError, resolve_api_host


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_invalid_host_is_rejected():
    for host in ("", "servidor.com", "ftp://x.com"):
        with pytest.raises(StoreApiError):
            StoreApiClient(host)


def test_resolve_api_host_prefers_setting_then_env(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_API_HOST", "https://env.example")
    assert resolve_api_host("") == "https://env.example"
    assert resolve_api_host("https://cfg.example") == "https://cfg.example"
    monkeypatch.delenv("NEXT_PUBLIC_API_HOST")
    assert resolve_api_host("") == ""


def test_uber_request_shape_and_response(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = json.loads(request.data)
        return _FakeResponse(json.dumps({"data": [], "totalGeneral": "0.00"}).encode())

    monkeypatch.setattr(store_api.urllib.request, "urlopen", fake_urlopen)
    client = StoreApiClient("https://api.example/")
    result = client.get_uber_sales(dt.date(2026, 11, 1), dt.date(2026, 11, 13))

    assert result["totalGeneral"] == "0.00"
    assert captured["url"] == "https://api.example/getVentasDeDIDIByFechasConDetalleDeVentas"
    assert captured["method"] == "POST"
    assert captured["body"] == {
        "startDate": "2026-11-01T00:00:00.229Z",
        "endDate": "2026-11-13T23:59:59.229Z",
    }


def test_http_and_network_errors_become_store_api_error(monkeypatch):
    def http_error(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 500, "Server Error", {}, None)

    monkeypatch.setattr(store_api.urllib.request, "urlopen", http_error)
    with pytest.raises(StoreApiError, match="500"):
        StoreApiClient("https://api.example").get_transfer_payments(
            dt.date(2026, 11, 1), dt.date(2026, 11, 1)
        )

    def url_error(request, timeout):
        raise urllib.error.URLError("sin red")

    monkeypatch.setattr(store_api.urllib.request, "urlopen", url_error)
    with pytest.raises(StoreApiError, match="conectar"):
        StoreApiClient("https://api.example").get_transfer_payments(
            dt.date(2026, 11, 1), dt.date(2026, 11, 1)
        )


def test_non_json_response_is_an_error(monkeypatch):
    monkeypatch.setattr(
        store_api.urllib.request, "urlopen", lambda request, timeout: _FakeResponse(b"<html>")
    )
    with pytest.raises(StoreApiError, match="JSON"):
        StoreApiClient("https://api.example").get_uber_sales(
            dt.date(2026, 11, 1), dt.date(2026, 11, 1)
        )

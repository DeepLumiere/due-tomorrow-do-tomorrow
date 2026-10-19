import urllib.request
import pytest

def test_hf_connectivity():
    try:
        response = urllib.request.urlopen("https://huggingface.co", timeout=5)
        print("HF status:", response.status)
        assert response.status == 200
    except Exception as e:
        print("HF connection failed:", type(e), e)
        pytest.skip(f"Offline: {e}")

from src.browser_keys import mask_api_key


def test_mask_api_key_hides_the_middle():
    assert mask_api_key("AIzaSyDummyKeyValue123456") == "AIza…3456"
    assert mask_api_key("short") == "••••••••"
    assert mask_api_key("") == "••••••••"

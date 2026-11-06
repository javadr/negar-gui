import pytest

from negar_gui import llm_providers


class TestPrompts:
    def test_prompts_defined(self):
        assert len(llm_providers.PROMPTS) > 0

    def test_prompt_structure(self):
        for key, prompt in llm_providers.PROMPTS.items():
            assert "name" in prompt
            assert "system_prompt" in prompt
            assert "prefix" in prompt
            assert isinstance(prompt["name"], str) and prompt["name"]
            assert isinstance(prompt["system_prompt"], str) and prompt["system_prompt"]
            assert isinstance(prompt["prefix"], str) and prompt["prefix"]


class TestFixTextEdgeCases:
    def test_empty_text(self):
        assert llm_providers.fix_text("") == ""
        assert llm_providers.fix_text("   ") == "   "

    def test_bad_prompt_key(self):
        result = llm_providers.fix_text("hello", prompt_key="nonexistent")
        assert result == "hello"

    def test_no_prompt_key(self):
        assert llm_providers.fix_text("hello") is not None


class TestFixTextApiSuccess:
    def test_returns_corrected_text(self, mocker):
        fake = mocker.Mock()
        fake.json.return_value = {"choices": [{"message": {"content": " corrected text "}}]}
        mocker.patch.object(llm_providers.requests, "post", return_value=fake)

        result = llm_providers.fix_text("some text")

        assert result == "corrected text"

    def test_sends_correct_payload(self, mocker):
        fake = mocker.Mock()
        fake.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        post_spy = mocker.patch.object(llm_providers.requests, "post", return_value=fake)

        llm_providers.fix_text("hello world")

        post_spy.assert_called_once()
        _, kwargs = post_spy.call_args
        assert kwargs["json"]["model"] == "openai"
        assert kwargs["json"]["messages"][0]["role"] == "system"
        assert kwargs["json"]["messages"][1]["role"] == "user"
        assert kwargs["json"]["messages"][1]["content"] == "متن زیر را ویرایش کن: hello world"
        assert kwargs["json"]["temperature"] == 0.0
        assert len(kwargs["json"]["messages"]) == 2


class TestProviders:
    def test_every_provider_is_complete(self):
        assert llm_providers.DEFAULT_PROVIDER in llm_providers.PROVIDERS
        for prov in llm_providers.PROVIDERS.values():
            assert prov["name"] and prov["url"].startswith("https://") and prov["model"]

    def test_key_and_model_are_sent(self, mocker):
        fake = mocker.Mock()
        fake.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        post_spy = mocker.patch.object(llm_providers.requests, "post", return_value=fake)

        llm_providers.fix_text("hello", provider="gemini", api_key="k123")

        args, kwargs = post_spy.call_args
        assert args[0] == llm_providers.PROVIDERS["gemini"]["url"]
        assert kwargs["headers"]["Authorization"] == "Bearer k123"
        assert kwargs["json"]["model"] == llm_providers.PROVIDERS["gemini"]["model"]

    def test_custom_model_overrides_default(self):
        _, _, payload = llm_providers.build_request("hi", provider="groq", model="qwen/qwen3")
        assert payload["model"] == "qwen/qwen3"

    def test_no_key_means_no_auth_header(self):
        _, headers, _ = llm_providers.build_request("hi")
        assert "Authorization" not in headers

    def test_unknown_provider_falls_back_to_default(self):
        url, _, _ = llm_providers.build_request("hi", provider="gone")
        assert url == llm_providers.POLLINATIONS_URL


class TestParseReply:
    def test_reasoning_fallback_and_tag_extraction(self):
        data = {"choices": [{"message": {"content": "", "reasoning": "x <corrected text> fixed </corrected text>"}}]}
        assert llm_providers.parse_reply(data) == "fixed"

    def test_empty_reply_raises(self):
        with pytest.raises(KeyError):
            llm_providers.parse_reply({"choices": [{"message": {"content": "  "}}]})


class TestFixTextErrors:
    def test_request_exception(self, mocker):
        mocker.patch.object(
            llm_providers.requests,
            "post",
            side_effect=llm_providers.requests.RequestException("network error"),
        )

        with pytest.raises(RuntimeError, match="LLM request failed"):
            llm_providers.fix_text("hello")

    def test_http_error(self, mocker):
        fake = mocker.Mock()
        fake.raise_for_status.side_effect = llm_providers.requests.HTTPError("403 Client Error")
        mocker.patch.object(llm_providers.requests, "post", return_value=fake)

        with pytest.raises(RuntimeError, match="LLM request failed"):
            llm_providers.fix_text("hello")


class TestIntegration:
    def test_real_api_call(self):
        try:
            result = llm_providers.fix_text("This has a speling error")
            assert isinstance(result, str) and len(result) > 0
        except RuntimeError as e:
            if "502" in str(e) or "429" in str(e):
                pytest.skip("API temporarily unavailable")
            raise

    def test_real_api_persian(self):
        try:
            result = llm_providers.fix_text("سلام. چطوری؟")
            assert isinstance(result, str) and len(result) > 0
        except RuntimeError as e:
            if "502" in str(e) or "429" in str(e):
                pytest.skip("API temporarily unavailable")
            raise

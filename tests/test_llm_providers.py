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
        assert kwargs["json"]["max_tokens"] == max(256, len("متن زیر را ویرایش کن: hello world") * 2)
        assert len(kwargs["json"]["messages"]) == 2


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

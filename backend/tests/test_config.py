import pytest

from app.config import (
    DEFAULT_MAX_NEW_TOKENS,
    DEFAULT_MODEL_ID,
    ConfigError,
    Settings,
)


def test_defaults_require_cuda_and_fp16():
    settings = Settings.from_env({})

    assert settings.model_id == DEFAULT_MODEL_ID
    assert settings.device == "cuda"
    assert settings.dtype == "float16"
    assert settings.max_new_tokens == DEFAULT_MAX_NEW_TOKENS
    assert settings.hf_home is None


def test_env_overrides_are_applied():
    settings = Settings.from_env(
        {
            "LOCAL_AI_CAD_MODEL_ID": "Qwen/Qwen2.5-0.5B-Instruct",
            "LOCAL_AI_CAD_DEVICE": "CPU",
            "LOCAL_AI_CAD_DTYPE": "float32",
            "LOCAL_AI_CAD_MAX_NEW_TOKENS": "32",
            "LOCAL_AI_CAD_HF_HOME": " D:/hf-cache ",
            "LOCAL_AI_CAD_LOG_LEVEL": "debug",
        }
    )

    assert settings.model_id == "Qwen/Qwen2.5-0.5B-Instruct"
    assert settings.device == "cpu"
    assert settings.dtype == "float32"
    assert settings.max_new_tokens == 32
    assert settings.hf_home == "D:/hf-cache"
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize(
    "env",
    [
        {"LOCAL_AI_CAD_MODEL_ID": "qwen2.5"},
        {"LOCAL_AI_CAD_MODEL_ID": "owner/name/extra"},
        {"LOCAL_AI_CAD_DEVICE": "mps"},
        {"LOCAL_AI_CAD_DTYPE": "int4"},
        {"LOCAL_AI_CAD_MAX_NEW_TOKENS": "0"},
        {"LOCAL_AI_CAD_MAX_NEW_TOKENS": "many"},
        {"LOCAL_AI_CAD_LOG_LEVEL": "LOUD"},
    ],
)
def test_invalid_values_fail_as_config_errors(env):
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_empty_hf_home_is_none_not_empty_string():
    # 빈 문자열을 그대로 두면 HF_HOME 을 ""로 덮어써 캐시 경로가 깨진다.
    assert Settings.from_env({"LOCAL_AI_CAD_HF_HOME": "   "}).hf_home is None

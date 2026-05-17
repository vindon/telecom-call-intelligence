"""
Tests for pipeline/config.py — verifies all expected constants are present,
typed correctly, and within sane production ranges.
"""

from pathlib import Path

from pipeline import config


class TestModelConfig:
    def test_extraction_model_is_string(self):
        assert isinstance(config.EXTRACTION_MODEL, str)
        assert len(config.EXTRACTION_MODEL) > 5

    def test_insights_model_is_string(self):
        assert isinstance(config.INSIGHTS_MODEL, str)

    def test_max_output_tokens_reasonable(self):
        assert 1024 <= config.MAX_OUTPUT_TOKENS <= 65536

    def test_extraction_temperature_in_range(self):
        assert 0.0 <= config.EXTRACTION_TEMPERATURE <= 1.0

    def test_insights_temperature_in_range(self):
        assert 0.0 <= config.INSIGHTS_TEMPERATURE <= 1.0

    def test_insights_temperature_higher_than_extraction(self):
        # Insights should be more creative than deterministic extraction
        assert config.INSIGHTS_TEMPERATURE > config.EXTRACTION_TEMPERATURE


class TestApiConfig:
    def test_max_retries_per_call_positive(self):
        assert config.MAX_RETRIES_PER_CALL >= 1

    def test_retry_delays_ascending(self):
        delays = config.RETRY_DELAYS_S
        assert len(delays) >= 2
        assert all(delays[i] < delays[i + 1] for i in range(len(delays) - 1))


class TestBatchingConfig:
    def test_default_n_calls_positive(self):
        assert config.DEFAULT_N_CALLS > 0

    def test_default_batch_size_positive(self):
        assert config.DEFAULT_BATCH_SIZE > 0

    def test_default_delay_non_negative(self):
        assert config.DEFAULT_DELAY_S >= 0

    def test_default_rate_limit_rpm_positive(self):
        assert config.DEFAULT_RATE_LIMIT_RPM > 0


class TestPathConfig:
    def test_output_dir_is_path(self):
        assert isinstance(config.OUTPUT_DIR, Path)

    def test_memory_path_is_path(self):
        assert isinstance(config.MEMORY_PATH, Path)

    def test_memory_path_inside_output_dir(self):
        assert config.MEMORY_PATH.parent == config.OUTPUT_DIR

    def test_prompt_path_is_path(self):
        assert isinstance(config.PROMPT_PATH, Path)

    def test_hf_dataset_is_string(self):
        assert isinstance(config.HF_DATASET, str)
        assert "/" in config.HF_DATASET  # HuggingFace datasets are "owner/dataset"


class TestGovernanceConfig:
    def test_budget_usd_positive(self):
        assert config.BUDGET_USD > 0

    def test_min_pass_rate_fraction(self):
        assert 0.0 < config.MIN_PASS_RATE < 1.0


class TestValidationConfig:
    def test_min_transcript_chars_positive(self):
        assert config.MIN_TRANSCRIPT_CHARS > 0

    def test_min_turn_count_positive(self):
        assert config.MIN_TURN_COUNT > 0


class TestQAConfig:
    def test_high_threshold_above_pass(self):
        assert config.QA_HIGH_THRESHOLD > config.QA_PASS_THRESHOLD

    def test_qa_thresholds_in_range(self):
        assert 0 <= config.QA_PASS_THRESHOLD <= 100
        assert 0 <= config.QA_HIGH_THRESHOLD <= 100

    def test_run_history_limit_reasonable(self):
        assert 10 <= config.RUN_HISTORY_LIMIT <= 500

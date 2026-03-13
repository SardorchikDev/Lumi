"""Tests for src.agents.council — task classification and confidence extraction."""

from src.agents.council import (
    AGENTS,
    LEAD_AGENTS,
    SPECIALIST_PROMPTS,
    TASK_ANALYSIS,
    TASK_CODE,
    TASK_CREATIVE,
    TASK_DEBUG,
    TASK_DESIGN,
    TASK_FACTUAL,
    TASK_GENERAL,
    _extract_confidence,
    classify_task,
)


class TestClassifyTask:
    def test_code_task(self):
        result = classify_task("write a Python function to sort a list and implement the class")
        assert result == TASK_CODE

    def test_debug_task(self):
        # Debug needs score >= 2
        result = classify_task("there's an error, the bug crashes the app")
        assert result == TASK_DEBUG

    def test_analysis_task(self):
        result = classify_task("analyze and compare the tradeoffs between these approaches")
        assert result == TASK_ANALYSIS

    def test_creative_task(self):
        result = classify_task("write a creative story with engaging dialogue")
        assert result == TASK_CREATIVE

    def test_design_task(self):
        result = classify_task("design the database schema and architecture for this system")
        assert result == TASK_DESIGN

    def test_factual_with_question_mark(self):
        result = classify_task("what is the meaning of life?")
        assert result == TASK_FACTUAL

    def test_general_task(self):
        result = classify_task("hello there")
        assert result == TASK_GENERAL

    def test_debug_priority_over_code(self):
        """Debug should win when there are enough debug keywords."""
        result = classify_task("error crash not working fix this broken bug")
        assert result == TASK_DEBUG


class TestExtractConfidence:
    def test_extract_valid_confidence(self):
        text = "Here is my answer.\n\nCONFIDENCE: 8/10"
        clean, score = _extract_confidence(text)
        assert score == 8
        assert "CONFIDENCE" not in clean

    def test_extract_confidence_caps(self):
        text = "Answer here.\nconfidence: 6/10"
        _, score = _extract_confidence(text)
        assert score == 6

    def test_no_confidence_defaults_to_7(self):
        text = "Just a normal response with no confidence line."
        clean, score = _extract_confidence(text)
        assert score == 7
        assert clean == text

    def test_confidence_clamped_min(self):
        text = "Bad answer.\nCONFIDENCE: 0/10"
        _, score = _extract_confidence(text)
        assert score == 1  # clamped to min 1

    def test_confidence_clamped_max(self):
        text = "Great answer.\nCONFIDENCE: 15/10"
        _, score = _extract_confidence(text)
        assert score == 10  # clamped to max 10


class TestAgentRoster:
    def test_agents_not_empty(self):
        assert len(AGENTS) > 0

    def test_all_agents_have_required_fields(self):
        required = {"id", "name", "models", "provider", "role", "strengths", "tier", "base_url", "key_env"}
        for agent in AGENTS:
            missing = required - set(agent.keys())
            assert not missing, f"Agent '{agent.get('id', '?')}' missing: {missing}"

    def test_all_agents_have_specialist_prompts(self):
        for agent in AGENTS:
            assert agent["id"] in SPECIALIST_PROMPTS, f"No specialist prompt for '{agent['id']}'"

    def test_lead_agents_cover_all_task_types(self):
        task_types = [TASK_CODE, TASK_DEBUG, TASK_ANALYSIS, TASK_CREATIVE, TASK_FACTUAL, TASK_DESIGN, TASK_GENERAL]
        for tt in task_types:
            assert tt in LEAD_AGENTS, f"No lead agent for task type '{tt}'"

    def test_agent_ids_unique(self):
        ids = [a["id"] for a in AGENTS]
        assert len(ids) == len(set(ids)), "Duplicate agent IDs found"

    def test_tiers_valid(self):
        valid_tiers = {"fast", "slow"}
        for agent in AGENTS:
            assert agent["tier"] in valid_tiers, f"Agent '{agent['id']}' has invalid tier '{agent['tier']}'"

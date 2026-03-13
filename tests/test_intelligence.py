"""Tests for src.utils.intelligence — emotion, topic, and task detection."""

from src.utils.intelligence import (
    _detect_emotion_regex,
    _fallback_classification,
    detect_emotion,
    detect_topic,
    emotion_hint,
    is_complex_coding_task,
    needs_plan_first,
    should_search,
)


class TestEmotionDetection:
    def test_frustrated(self):
        assert detect_emotion("ugh this doesn't work") == "frustrated"
        assert detect_emotion("wtf is going on") == "frustrated"

    def test_sad(self):
        assert detect_emotion("i'm sad today") == "sad"
        assert detect_emotion("feeling down lately") == "sad"

    def test_confused(self):
        assert detect_emotion("i don't understand this") == "confused"
        assert detect_emotion("can you explain that") == "confused"

    def test_happy(self):
        assert detect_emotion("thanks! that's great") == "happy"
        assert detect_emotion("awesome, love it") == "happy"

    def test_neutral(self):
        assert detect_emotion("what is python") is None
        assert detect_emotion("tell me about databases") is None

    def test_detect_emotion_regex_same_as_detect_emotion(self):
        text = "this is so annoying"
        assert _detect_emotion_regex(text) == detect_emotion(text)


class TestEmotionHint:
    def test_known_emotions(self):
        assert "patient" in emotion_hint("frustrated").lower()
        assert "warm" in emotion_hint("sad").lower() or "supportive" in emotion_hint("sad").lower()
        assert "clearly" in emotion_hint("confused").lower() or "simply" in emotion_hint("confused").lower()
        assert "positive" in emotion_hint("happy").lower() or "energy" in emotion_hint("happy").lower()

    def test_unknown_emotion(self):
        assert emotion_hint("unknown") == ""
        assert emotion_hint("") == ""


class TestTopicDetection:
    def test_coding_topic(self):
        assert detect_topic("write a python function") == "coding"

    def test_writing_topic(self):
        assert detect_topic("write an essay about climate") == "writing"

    def test_math_topic(self):
        assert detect_topic("solve this math equation") == "math"

    def test_no_topic(self):
        # Very generic text might not match strongly
        result = detect_topic("hello")
        # Should return None or a topic
        assert result is None or isinstance(result, str)


class TestShouldSearch:
    def test_search_triggers(self):
        assert should_search("search for python tutorials") is True
        assert should_search("what is the latest news") is True
        assert should_search("who is Elon Musk") is True
        assert should_search("price of bitcoin") is True

    def test_search_blocklist(self):
        assert should_search("what is your name") is False
        assert should_search("who are you") is False

    def test_no_search(self):
        assert should_search("write a function") is False
        assert should_search("explain recursion") is False


class TestIsComplexCodingTask:
    def test_complex_tasks(self):
        assert is_complex_coding_task("create a website with React") is True
        assert is_complex_coding_task("build an API server") is True
        assert is_complex_coding_task("implement a caching system") is True
        assert is_complex_coding_task("refactor the auth module") is True

    def test_simple_tasks(self):
        assert is_complex_coding_task("hello") is False
        assert is_complex_coding_task("what time is it") is False


class TestNeedsPlanFirst:
    def test_plan_triggers(self):
        assert needs_plan_first("create a folder structure for a project") is True
        assert needs_plan_first("scaffold a new React app") is True
        assert needs_plan_first("build a complete web app from scratch") is True

    def test_no_plan_needed(self):
        assert needs_plan_first("fix this bug") is False
        assert needs_plan_first("explain how async works") is False


class TestFallbackClassification:
    def test_returns_dict(self):
        result = _fallback_classification("hello world")
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        result = _fallback_classification("test input")
        assert "intent" in result
        assert "emotion" in result
        assert "urgency" in result
        assert "needs_clarification" in result
        assert "tools" in result
        assert "routing" in result

    def test_coding_intent(self):
        result = _fallback_classification("create a website with index.html")
        assert result["intent"] == "coding"

    def test_search_intent(self):
        result = _fallback_classification("search for the latest python version")
        assert result["intent"] == "search"
        assert "search" in result["tools"]

    def test_debug_intent(self):
        result = _fallback_classification("debug this error fix the bug")
        assert result["intent"] == "debug"

    def test_general_intent(self):
        result = _fallback_classification("hello there")
        assert result["intent"] == "general"

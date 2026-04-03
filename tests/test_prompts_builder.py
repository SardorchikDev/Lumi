"""Tests for src.prompts.builder — system prompt construction."""

from src.prompts.builder import (
    PromptContext,
    build_dynamic_system_prompt,
    build_messages,
    build_system_prompt,
    is_coding_task,
    is_file_generation_task,
    load_persona,
)


class TestLoadPersona:
    def test_returns_dict(self):
        persona = load_persona()
        assert isinstance(persona, dict)

    def test_has_required_keys(self):
        persona = load_persona()
        assert "name" in persona
        assert "creator" in persona
        assert "tone" in persona
        assert "traits" in persona

    def test_default_name_is_lumi(self):
        persona = load_persona()
        assert persona["name"] == "Lumi"


class TestBuildSystemPrompt:
    def test_basic_prompt(self):
        persona = {"name": "TestBot", "creator": "Tester", "tone": "friendly", "traits": ["smart"]}
        prompt = build_system_prompt(persona)
        assert "TestBot" in prompt
        assert "Tester" in prompt
        assert "friendly" in prompt

    def test_coding_mode_injects_coding_system(self):
        persona = {"name": "Lumi", "creator": "Test", "tone": "chill", "traits": []}
        prompt_normal = build_system_prompt(persona, coding_mode=False)
        prompt_coding = build_system_prompt(persona, coding_mode=True)
        assert "CODING MODE" in prompt_coding
        assert "CODING MODE" not in prompt_normal

    def test_file_mode_injects_file_generation(self):
        persona = {"name": "Lumi", "creator": "Test", "tone": "chill", "traits": []}
        prompt_normal = build_system_prompt(persona, file_mode=False)
        prompt_file = build_system_prompt(persona, file_mode=True)
        assert "Generating complete projects" in prompt_file
        assert "Generating complete projects" not in prompt_normal

    def test_memory_block_included(self):
        persona = {"name": "Lumi", "creator": "Test", "tone": "chill", "traits": []}
        memory = "User prefers TypeScript"
        prompt = build_system_prompt(persona, memory_block=memory)
        assert "User prefers TypeScript" in prompt

    def test_empty_memory_block(self):
        persona = {"name": "Lumi", "creator": "Test", "tone": "chill", "traits": []}
        prompt = build_system_prompt(persona, memory_block="")
        assert "What you know about this user" not in prompt

    def test_traits_joined(self):
        persona = {"name": "Bot", "creator": "X", "tone": "calm", "traits": ["smart", "funny"]}
        prompt = build_system_prompt(persona)
        assert "smart, funny" in prompt

    def test_empty_traits_uses_default(self):
        persona = {"name": "Bot", "creator": "X", "tone": "calm", "traits": []}
        prompt = build_system_prompt(persona)
        assert "supportive, honest, laid-back" in prompt

    def test_never_break_character(self):
        persona = {"name": "Aria", "creator": "Dev", "tone": "formal", "traits": ["precise"]}
        prompt = build_system_prompt(persona)
        assert "Never break character" in prompt

    def test_identity_rules_require_answering_as_lumi(self):
        persona = {"name": "Lumi", "creator": "Dev", "tone": "calm", "traits": ["precise"]}
        prompt = build_system_prompt(persona)
        assert "If the user asks who you are" in prompt
        assert "Never claim to be Claude Code" in prompt

    def test_dynamic_prompt_includes_creator_and_release_identity(self):
        persona = {"name": "Lumi", "creator": "Sardor Sodiqov (SardorchikDev)", "tone": "calm", "traits": ["precise"]}
        prompt = build_dynamic_system_prompt(
            persona,
            context=PromptContext(date="2026-04-03", cwd="/repo", git_branch="main"),
        )
        assert "Sardor Sodiqov" in prompt
        assert "SardorchikDev" in prompt
        assert "Lumi v0.7.5: Beacon" in prompt


class TestIsCodingTask:
    def test_coding_task_detected(self):
        assert is_coding_task("write a function to sort arrays") is True
        assert is_coding_task("fix the bug in my Python code") is True
        assert is_coding_task("create a REST API endpoint") is True

    def test_non_coding_task(self):
        assert is_coding_task("hello how are you") is False
        assert is_coding_task("what's the weather today") is False

    def test_requires_at_least_two_keywords(self):
        # Single keyword shouldn't trigger
        assert is_coding_task("code") is False
        # Two keywords should
        assert is_coding_task("code function") is True


class TestIsFileGenerationTask:
    def test_file_generation_detected(self):
        assert is_file_generation_task("create a folder with index.html") is True
        assert is_file_generation_task("scaffold a new project") is True
        assert is_file_generation_task("create a project from scratch") is True

    def test_non_file_generation(self):
        assert is_file_generation_task("explain how folders work") is False
        assert is_file_generation_task("what is a file system") is False


class TestBuildMessages:
    def test_system_prompt_prepended(self):
        history = [{"role": "user", "content": "hello"}]
        messages = build_messages("You are helpful", history)
        assert messages[0] == {"role": "system", "content": "You are helpful"}
        assert messages[1] == {"role": "user", "content": "hello"}

    def test_empty_history(self):
        messages = build_messages("system prompt", [])
        assert len(messages) == 1
        assert messages[0]["role"] == "system"

    def test_preserves_history_order(self):
        history = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "third"},
        ]
        messages = build_messages("sys", history)
        assert len(messages) == 4
        assert messages[1]["content"] == "first"
        assert messages[3]["content"] == "third"

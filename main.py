"""Lumi — conversational AI entry point."""

from dotenv import load_dotenv
load_dotenv()

from src.chat.hf_client import get_client, chat
from src.memory.short_term import ShortTermMemory
from src.prompts.builder import load_persona, build_system_prompt, build_messages


def main():
    persona = load_persona()
    system_prompt = build_system_prompt(persona)
    memory = ShortTermMemory(max_turns=20)
    client = get_client()

    name = persona.get("name", "Lumi")
    print(f"🤖 {name} is ready. Type 'quit' to exit, 'clear' to reset memory.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Bye!")
            break
        if user_input.lower() == "clear":
            memory.clear()
            print("[Memory cleared]\n")
            continue

        memory.add("user", user_input)
        messages = build_messages(system_prompt, memory.get())

        try:
            reply = chat(client, messages)
        except Exception as e:
            print(f"[Error: {e}]\n")
            memory._history.pop()
            continue

        memory.add("assistant", reply)
        print(f"{name}: {reply}\n")


if __name__ == "__main__":
    main()

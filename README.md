# Calendar Assistant (Mac)

A privacy-focused, voice-driven calendar assistant for macOS. This tool uses local AI models (Ollama for reasoning and Whisper for speech-to-text) to manage your calendar events without sending audio to the cloud.

> [!IMPORTANT]
> This application is specifically designed for **macOS** and leverages native features like the `say` command, system accessibility hooks, and macOS native dialogs.

## 🛠 Prerequisites

Before installation, ensure you have the following:

- **Hardware:** A Mac (Apple Silicon M-series recommended for best performance).
- **Python:** Version 3.11 or higher.
- **Microphone Access:** You will need to grant your Terminal or IDE permissions to access the microphone.
- **Ollama:** Download and install [Ollama](https://ollama.ai).
  - After installing Ollama, pull the reasoning model: `ollama pull llama3.1:8b` (or your preferred model according to `config.yaml`).

## 🚀 Installation

1. **Clone the project:**
   ```bash
   git clone <repository-url>
   cd assistant_tools
   ```

2. **Set up a Virtual Environment:**
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -e .
   ```

## ⚙️ Configuration

The application uses `config.yaml` for customization. If it doesn't exist, you can create it from the example:
```bash
cp config.example.yaml config.yaml
```

### Key Settings:
- **`llm_engine`**: Choose your reasoning brain:
  - `"ollama"` (Default): Free, local, private. Requires Ollama to be running.
  - `"openai"`: High performance. Requires `openai.api_key`.
  - `"gemini"`: Google's LLM. Requires `gemini.api_key`.
  - `"claude"`: Anthropic's LLM. Requires `claude.api_key`.
- **`hotkey`**: The trigger for the voice listener (default is `Cmd+Shift+Space`).
- **`tts`**: 
  - `voice`: Preferred system voice (e.g., `"Ava"`, `"Zari"`, `"Samantha"`). Run `say -v \?` in your terminal to see all options.
  - `rate`: Talking speed.
  - `mute`: Set to `true` for a silent assistant.

## 📅 Usage

### Starting the App
- **The easy way:** Double-click `Launch Calendar.command` in the Finder.
- **The terminal way:** Run `python -m assistant.main`.

### Interacting with Voice
1. **Trigger:** Press the hotkey (`Cmd+Shift+Space`) to start listening.
2. **Speak:** State your request clearly (e.g., *"Schedule a dentist appointment for tomorrow at 2 PM"* or *"Cancel my meeting with Alex"*).
3. **Finish:** Say **"execute"**, **"done"**, or simply press the hotkey again to trigger the actions immediately.
4. **Autonomous Mode:** You can toggle "Auto-Approve" in the **⚙️ Settings** icon in the UI to skip confirmation dialogs.

> [!TIP]
> **Context Memory:** You can refer to the last event you created by saying "delete **it**" or "move **that event**".

## 🔒 Security & Privacy
- **LLM Choices:** By default, everything is local and private using Ollama. If you switch to `openai`, `gemini`, or `claude`, your transcripts will be sent to the respective provider's API.
- **Full Local Logic:** Audio is transcribed locally using `faster-whisper`.
- **Prompt Injection Defense:** Basic sanitization prevents malicious commands from being executed via voice.
- **Persistence:** closing the application will save all your changes to the `.db` file normally.

## 🧪 Testing
A comprehensive test suite is provided to verify model reasoning and database logic:
```bash
python tests/test_ollama_parser.py
```

## 🤖 For Developers & AI Assistants

If you are an AI assistant or a developer working on this codebase, please **read [SYSTEM.md](./SYSTEM.md) first**. It contains the full project architecture, recent core enhancements (Streaming STT, Universal LLM Parser), and current state details to help you resume work without loss of context.

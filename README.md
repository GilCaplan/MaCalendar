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

### Views
- **Month / Week / Day** — Switch between views using the toolbar buttons.
- The **Day view** shows a full hourly timeline for any single date with a live red current-time indicator.
- **Tasks** — Apple Reminders-style task panel with Today and General lists (see below).

### Morning Briefing
Click the **🌅 Brief Me** button in the Day view (or ask via voice) to have your assistant read today's full schedule aloud — great for hands-free mornings.

Voice triggers: *"What does my day look like?"*, *"When is my first meeting?"*, *"What's next?"*, *"How many events do I have today?"*

### Tasks View
Switch to **Tasks** in the toolbar to manage your todo list with two sections:

| Section | Purpose |
|---------|---------|
| **Today** | Tasks for today. Click **🔄 Sync Today** to pull in today's calendar events automatically. |
| **General** | Ongoing or someday tasks, independent of any date. |

**Manual editing:** Click any task title to edit it inline. Click the checkbox to complete it. Hover to reveal the × delete button. Click **+ New Task** to add from the keyboard.

**Calendar sync:** The **🔄 Sync Today** button in the Today header pulls all of today's calendar events into your Today list as tasks. The ⚙ gear offers additional sync options (upcoming week → General list, or clear synced tasks).

**Voice commands (Tasks mode):**
When the Tasks tab is active, the mic button enters *Tasks mode* — voice commands are automatically biased towards task actions:
- *"Add task buy groceries"* — adds a single task
- *"Add tasks: buy milk, call dentist, walk the dog"* — adds multiple tasks at once
- *"Mark buy milk done"* / *"Check off call dentist"* — complete a task
- *"Delete buy groceries"* / *"Remove it"* — delete by title or by anaphoric "it"
- *"Rename buy milk to buy oat milk"* — update a task
- *"Move call dentist to general list"* — change list
- *"What tasks do I have today?"* — read out the list (switches to Tasks view)

> [!TIP]
> **Context Memory:** Within the Tasks view, "it" and "that task" always refer to the last task you created or modified.

### Interacting with Voice
1. **Trigger:** Press the hotkey (`Cmd+Shift+Space`) to start listening.
2. **Speak:** State your request clearly (e.g., *"Schedule a dentist appointment for tomorrow at 2 PM"* or *"Cancel my meeting with Alex"*).
3. **Finish:** Say **"execute"**, **"done"**, or simply press the hotkey again to trigger the actions immediately.
4. **Autonomous Mode:** You can toggle "Auto-Approve" in the **⚙️ Settings** icon in the UI to skip confirmation dialogs.

> [!TIP]
> **Context Memory:** You can refer to the last event you created by saying "delete **it**" or "move **that event**". Same works for tasks.

## 🔒 Security & Privacy
- **LLM Choices:** By default, everything is local and private using Ollama. If you switch to `openai`, `gemini`, or `claude`, your transcripts will be sent to the respective provider's API.
- **Full Local Logic:** Audio is transcribed locally using `faster-whisper`.
- **Prompt Injection Defense:** Basic sanitization prevents malicious commands from being executed via voice.
- **Persistence:** closing the application will save all your changes to the `.db` file normally.

## 🧪 Testing
A comprehensive test suite is provided to verify model reasoning and database logic:
```bash
# Calendar voice command tests (requires Ollama running)
python tests/test_ollama_parser.py

# Todo feature tests — direct execution (no LLM required)
python tests/test_todo_parser.py --direct

# Todo feature tests — full LLM routing (requires Ollama running)
python tests/test_todo_parser.py

# Full unit test suite
pytest tests/
```

## 📱 iPhone App

MACalendar includes a native SwiftUI companion app and a Flask REST API. The Mac acts as the source of truth, and the iPhone connects via Tailscale to manage events and tasks from anywhere.

### 1. Deploy the App (via Xcode)
1. Open `MACalendar-iOS/MACalendar-iOS.xcodeproj` in **Xcode**.
2. Set your **Signing Team** in *Signing & Capabilities*.
3. Connect your iPhone and click **Run**.
4. (First time) Go to iPhone **Settings → General → VPN & Device Management** and **Trust** your developer profile.

### 2. Connect via Tailscale (Recommended)
Tailscale provides a secure, private tunnel between your Mac and iPhone without port forwarding.
1. **Mac:** `brew install tailscale` → Sign in.
2. **iPhone:** Install [Tailscale](https://apps.apple.com/app/tailscale/id1470499037) → Sign in.
3. **Start API:** `python -m assistant.api --tailscale` (Prints your 100.x.x.x IP).
4. **App Settings:** Set Server URL to `http://<your-tailscale-ip>:8080`.

For full deployment details and API reference, see [**SYSTEM_IPHONE.md**](./SYSTEM_IPHONE.md).

### API endpoints (quick reference)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Server status |
| GET | `/events?date=YYYY-MM-DD` | Events for a day |
| POST | `/events` | Create event |
| POST | `/voice/text` | Voice command as text |
| GET | `/todos` | Todo list |
| PATCH | `/todos/<id>/toggle` | Complete a task |

Full API reference: [SYSTEM_IPHONE.md](./SYSTEM_IPHONE.md)

---

## 🤖 For Developers & AI Assistants

If you are an AI assistant or a developer working on this codebase, please **read [SYSTEM.md](./SYSTEM.md) first**. It contains the full project architecture, recent core enhancements (Streaming STT, Universal LLM Parser), and current state details to help you resume work without loss of context.

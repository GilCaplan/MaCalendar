# Reading the server log

The API server (`python -m assistant.api`) narrates every command. The log is
**colour-coded by event kind** so a skim shows the flow — a command arriving,
the work in the middle, the answer going back, and any problem in red — rather
than a wall of grey. Implemented in `assistant/api/log_color.py`.

## The legend

| Colour | Band | What it is |
|---|---|---|
| **cyan** | in | a command / transcript / audio arriving (`Text command`, `Transcript:`, `Audio received`, a queued retry) |
| _(plain)_ | processing | the middle you skim past — rule/LLM/validate/execute chatter |
| **green** | out | the answer going back (`Response: … \| refresh=… \| parse=…`) |
| **magenta** | learn | the assistant learned something (vocabulary alias, whitelisted word, memory, device location) |
| **yellow** | warn | warnings, warm-up, retry-loop notices |
| **red** | error | a parse or action failure, an unknown intent, a queue error |

So one command reads as **cyan → (plain) → green**; a broken one ends **red**.
The device emoji stays: 🖥️ Mac, 📱 iPhone, on every line.

## When colour is on

Only when a human is watching: stderr must be a TTY and `NO_COLOR` unset. A log
redirected to a file, or CI, stays plain text — so `Launch Calendar.command`'s
terminal is coloured, but `... > server.log` is not. Set `NO_COLOR=1` to force
plain even in a terminal.

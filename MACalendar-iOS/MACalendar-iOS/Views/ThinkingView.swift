import SwiftUI

// MARK: - Thinking timeline (live trace while a command runs)

/// One slot of the engine's canonical chain of thought. Mirrors
/// `assistant.trace.CHAINS[BRAIN_VERSION]` + `STAGE_INFO` on the host — kept
/// identical and pinned by `tests/unit/test_stage_info_parity.py`. It drives
/// the scaffold the panel renders (so a run reads as the diagram's flow, not as
/// raw step titles) and the ⓘ copy that explains each step in depth.
struct ChainSlot: Identifiable {
    let stage: String
    let label: String
    let heading: String
    let body: String
    var id: String { label }
}

/// What the chain rail is showing right now: which slots are done, which one
/// (if any) is the live one, and each done slot's duration in ms. See
/// `ThinkingView.railState`.
typealias ChainRailState = (done: Set<Int>, active: Int?, durations: [Int: Int])

enum EngineChain {
    /// The chain for a brain version. An unknown version shows no scaffold —
    /// the timeline falls back to the raw steps, exactly as before.
    static func scaffold(for brain: String) -> [ChainSlot] {
        guard brain == "engine-v2" else { return [] }
        return [
            ChainSlot(stage: "vocab", label: "fix words", heading: "Fix words",
                      body: "The transcript is corrected against your personal vocabulary — the names, places and phrases the speech model mishears. A word the vocabulary itself doubts can be checked with you before anything runs, so a mishearing never becomes a wrong event."),
            ChainSlot(stage: "rule", label: "rules first", heading: "Rules first",
                      body: "A deterministic rule parser reads the command first — 76 verb mappings — and scores its own confidence. When it is sure it answers in milliseconds without ever calling the language model. That is the fast lane; the deep track keeps checking behind it."),
            ChainSlot(stage: "rule", label: "split · split again", heading: "Split, then split again",
                      body: "The command is broken into its independent items, then each item is broken down again — two times in a sentence is two events, a list is one task per thing, a recurrence becomes a series. Deterministic where it can be; the model only when an item is genuinely ambiguous."),
            ChainSlot(stage: "validate", label: "repair · rules", heading: "Repair & validate",
                      body: "Named deterministic rules repair each item and guard the calendar — dates, am/pm, end-before-start, until/through, and rounding a recurrence to daily, weekly or monthly (announced, never silent). The observance gate lives here: what the assistant may book on Shabbat, yom tov and fast days."),
            ChainSlot(stage: "llm", label: "make each item", heading: "Make each item",
                      body: "Per item, the rules — or one schema-constrained model call when the rules cannot — produce the actual action: create this event, add that task, answer this question. Every model call is grounded on the raw words and can only return a valid shape."),
            ChainSlot(stage: "execute", label: "write · label", heading: "Write & label",
                      body: "The action runs against the local database, and the result is labelled — an event gets its category and colour, a task its tags. Nothing here reaches the internet; the database is a file on the machine."),
            ChainSlot(stage: "verify", label: "compare", heading: "Cross-check",
                      body: "The cross-check compares what was produced against what you actually said, and loops a wrong stage back to fix it — at most three times. Behind a fast answer it proposes rather than rewrites, so an instant answer is never silently changed under you."),
            ChainSlot(stage: "done", label: "done", heading: "Done",
                      body: "The command is finished. A fast-lane answer committed instantly and the deep track keeps checking behind it; a deep-track answer ran the whole pipeline in front of you. Every step above, and its timing, is this run."),
        ]
    }
}

/// Shown by VoiceButton while a command is in flight (Settings › Voice › Show
/// assistant thinking). Rows animate in as the Mac streams each stage.
struct ThinkingView: View {
    @EnvironmentObject var settings: AppSettings
    let steps: [TraceStep]
    let finished: Bool
    let response: VoiceResponse?
    let onFixWord: ((String) -> Void)?
    let onFeedback: ((String) -> Void)?
    var onRetry: ((Int) -> Void)? = nil
    var revertItems: [RevertItem] = []
    var onRevert: (() -> Void)? = nil
    @Environment(\.dismiss) private var dismiss
    @State private var expanded: Set<String> = []
    @State private var feedbackSent: String? = nil
    /// The step whose ⓘ was tapped — drives the in-depth explanation popover.
    @State private var infoSlot: ChainSlot? = nil

    // -- chain-rail live timer (mirrors the Mac's _ChainRail) --------------
    // The slot currently glowing, when it lit, and the redraw tick that keeps
    // its counter moving. `chainFrozenDurationsMs` holds only the one number
    // `railState` can't derive from the steps themselves: the last live slot,
    // frozen at whatever `finished` arrives (see the `onChange(of: finished)`
    // below) — every earlier slot's duration comes straight from the step
    // that superseded it, exactly like the Mac panel.
    @State private var chainActiveIndex: Int? = nil
    @State private var chainActiveSince = Date()
    @State private var chainFrozenDurationsMs: [Int: Int] = [:]
    @State private var chainLiveTick = Date()

    var body: some View {
        NavigationView {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        chainRail
                        ForEach(Array(steps.enumerated()), id: \.element.id) { idx, step in
                            row(step, isLast: idx == steps.count - 1)
                                .id(step.id)
                                .transition(.move(edge: .bottom).combined(with: .opacity))
                        }
                        if !finished {
                            HStack(spacing: 10) {
                                ProgressView().scaleEffect(0.8)
                                Text("Working…").font(.subheadline).foregroundColor(.secondary)
                            }
                            .padding(.leading, 40).padding(.top, 8)
                        }
                        if finished, let r = response {
                            resultCard(r).padding(.top, 16)
                        }
                        if !revertItems.isEmpty {
                            revertBanner.padding(.top, 12)
                        }
                    }
                    .padding(16)
                    .animation(.easeOut(duration: 0.25), value: steps.count)
                    .popover(item: $infoSlot) { slot in infoPopover(slot) }
                }
                .onChange(of: steps.count) { _ in
                    if let last = steps.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } }
                    syncChainActive()
                }
                .onChange(of: finished) { done in
                    if done {
                        freezeChainActiveIfNeeded()
                    } else {
                        // A new run started in the same presented sheet (a
                        // command sent again before this one's sheet was
                        // dismissed) — the previous run's chain bookkeeping
                        // must not leak into this one.
                        chainActiveIndex = nil
                        chainFrozenDurationsMs = [:]
                        chainActiveSince = Date()
                    }
                }
                .onReceive(Timer.publish(every: 0.1, on: .main, in: .common).autoconnect()) { now in
                    if !finished { chainLiveTick = now }
                }
                .onAppear { syncChainActive() }
            }
            .navigationTitle("Thinking")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    // -- the canonical chain scaffold (renders by brain version) -----------

    /// The engine's chain of thought as a compact scaffold, lit up as the live
    /// steps arrive, naming the brain version with an ⓘ per step. Empty for an
    /// unknown brain, so the timeline falls back to the raw steps as before.
    @ViewBuilder
    private var chainRail: some View {
        let brain = response?.brain ?? "engine-v2"
        let slots = EngineChain.scaffold(for: brain)
        if !slots.isEmpty {
            let state = railState(slots)
            VStack(alignment: .leading, spacing: 5) {
                HStack {
                    Text("chain of thought").font(.caption2.weight(.semibold)).foregroundColor(.secondary)
                    Spacer()
                    Text(brain).font(.caption2).foregroundColor(.secondary)
                }
                ForEach(Array(slots.enumerated()), id: \.element.id) { i, slot in
                    HStack(spacing: 8) {
                        AssistantIcon(icon(for: slot.stage), size: 11)
                            .foregroundColor(slotColor(i, state))
                        Text(slot.label)
                            .font(.caption)
                            .foregroundColor(state.done.contains(i) || i == state.active ? .primary : .secondary)
                        Spacer()
                        // Seconds, right of the mark — frozen once a slot is
                        // done, live and ticking while it's the one running,
                        // blank for a slot not reached (or skipped) yet.
                        Text(chainTimeText(i, state))
                            .font(.caption2.monospacedDigit())
                            .foregroundColor(.secondary)
                        // A small spinning wheel takes the mark's place only
                        // for the slot in progress — never resizing the row,
                        // since both sit in the same fixed-size frame.
                        Group {
                            if i == state.active && !finished {
                                ProgressView().controlSize(.small)
                            } else {
                                Text(stateMark(i, state))
                                    .font(.caption2)
                                    .foregroundColor(slotColor(i, state))
                            }
                        }
                        .frame(width: 14, height: 14)
                        Button { infoSlot = slot } label: {
                            Image(systemName: "info.circle").font(.caption)
                        }
                        .buttonStyle(.plain)
                        .foregroundColor(.secondary)
                    }
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.secondarySystemBackground))
            .cornerRadius(10)
            .padding(.bottom, 10)
        }
    }

    /// Sync the chain-rail's live-timer bookkeeping to whichever slot
    /// `railState` currently reports as active — called whenever a new step
    /// arrives, and once on appear for a sheet presented mid-run. A slot
    /// lighting up for the first time gets a fresh start time, mirroring the
    /// Mac's `_ChainRail._advance_to`, which resets `_active_since` the
    /// instant a new slot lights.
    private func syncChainActive() {
        let slots = EngineChain.scaffold(for: response?.brain ?? "engine-v2")
        guard !slots.isEmpty else { return }
        let active = railState(slots).active
        if active != chainActiveIndex {
            chainActiveIndex = active
            chainActiveSince = Date()
        }
    }

    /// The run ended while a slot was still live — there's no later step to
    /// source its duration from (the Mac panel has the identical gap, for the
    /// identical reason), so the wall-clock span it was active for — the same
    /// number its live counter was already showing — is frozen in its place.
    private func freezeChainActiveIfNeeded() {
        guard let a = chainActiveIndex, chainFrozenDurationsMs[a] == nil else { return }
        chainFrozenDurationsMs[a] = Int(Date().timeIntervalSince(chainActiveSince) * 1000)
    }

    private func chainTimeText(_ i: Int, _ state: ChainRailState) -> String {
        if state.done.contains(i) {
            let ms = state.durations[i] ?? chainFrozenDurationsMs[i]
            return ms.map(fmtChainSeconds) ?? ""
        }
        if i == state.active && !finished {
            _ = chainLiveTick   // read the 10Hz tick so this text redraws with it
            let elapsed = Date().timeIntervalSince(chainActiveSince) * 1000
            return fmtChainLiveSeconds(Int(elapsed))
        }
        return ""
    }

    // Same "always seconds" shape as the per-step rows below (see `row(_:)`):
    // two decimals under a second so a fast slot still reads as a duration,
    // one above it.
    private func fmtChainSeconds(_ ms: Int) -> String {
        ms >= 999
            ? String(format: "%.1f s", Double(ms) / 1000)
            : String(format: "%.2f s", Double(ms) / 1000)
    }

    // The live counter always shows tenths — a steady, readable rate rather
    // than snapping between one and two decimals as it crosses the 1s mark.
    private func fmtChainLiveSeconds(_ ms: Int) -> String {
        String(format: "%.1f s", Double(max(0, ms)) / 1000)
    }

    /// The in-depth explanation shown when a step's ⓘ is tapped. Kept a real
    /// popover ("tooltip") on iPhone where the OS allows it; a sheet below that.
    @ViewBuilder
    private func infoPopover(_ slot: ChainSlot) -> some View {
        let content = VStack(alignment: .leading, spacing: 8) {
            Text(slot.heading).font(.headline)
            Text(slot.body).font(.callout).foregroundColor(.secondary)
        }
        .padding(16)
        .frame(maxWidth: 300)
        if #available(iOS 16.4, *) {
            content.presentationCompactAdaptation(.popover)
        } else {
            content
        }
    }

    /// Which slots are done, which is live, and (for a done slot) how long it
    /// took — mapped from the live steps by stage, in order (mirrors the Mac
    /// panel's `_ChainRail.observe`/`_advance_to`). A slot's duration is the
    /// `ms` of the step that superseded it — that step's `ms` is "time since
    /// the previous step" (assistant.trace.Trace.step), exactly the span the
    /// earlier slot spent lit, whether this is a live run or a replayed one.
    /// The one slot this can't cover is whichever is still active when the
    /// run ends — `freezeChainActiveIfNeeded` supplies that one instead.
    private func railState(_ slots: [ChainSlot]) -> ChainRailState {
        var done = Set<Int>()
        var durations: [Int: Int] = [:]
        var active: Int? = nil
        var ptr = 0
        for step in steps {
            let stage = step.stage
            if stage == "stt" || stage == "memory" || stage == "error" { continue }
            var mapped = false
            var i = ptr
            while i < slots.count {
                if slots[i].stage == stage {
                    if let a = active { done.insert(a); durations[a] = step.ms }
                    active = i; ptr = i + 1; mapped = true; break
                }
                i += 1
            }
            if !mapped {   // a stage repeating past the pointer re-lights its last slot
                for j in stride(from: slots.count - 1, through: 0, by: -1) where slots[j].stage == stage {
                    active = j; break
                }
            }
        }
        if finished, let a = active { done.insert(a); active = nil }
        return (done, active, durations)
    }

    private func slotColor(_ i: Int, _ state: ChainRailState) -> Color {
        if state.done.contains(i) { return .green }
        if i == state.active && !finished { return settings.accentColor }
        return .secondary.opacity(0.5)
    }

    private func stateMark(_ i: Int, _ state: ChainRailState) -> String {
        if state.done.contains(i) { return "✓" }
        if i == state.active && !finished { return "…" }
        return finished ? "skipped" : ""
    }

    /// Shown when the background self-check undid something behind a fast answer
    /// — one tap re-creates it. Amber, not red: undoable, not a failure.
    @ViewBuilder
    private var revertBanner: some View {
        HStack(spacing: 10) {
            Image(systemName: "arrow.uturn.backward.circle")
            Text(revertItems.count > 1
                 ? "I undid \(revertItems.count) items behind your answer."
                 : "I undid something behind your answer.")
                .font(.footnote)
            Spacer()
            Button("Revert") { onRevert?() }
                .buttonStyle(.borderedProminent)
                .tint(.orange)
                .controlSize(.small)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.orange.opacity(0.12))
        .cornerRadius(10)
        .foregroundColor(.orange)
    }

    private func icon(for stage: String) -> AssistantIconName {
        switch stage {
        case "stt":      return .heard
        case "vocab":    return .vocab
        case "rule":     return .rule
        case "memory":   return .memory
        case "llm":      return .llm
        case "validate": return .validate
        case "execute":  return .execute
        case "verify":   return .verify
        case "done":     return .done
        case "error":    return .error
        default:         return .pending
        }
    }

    private func color(for step: TraceStep) -> Color {
        // Red is for something FATAL — the error stage. A step that merely
        // didn't fully succeed (a cross-check finding, a loop-back, a held-back
        // item) is the system reviewing itself, not a failure: that reads amber.
        if step.stage == "error" { return .red }
        if !step.ok { return .orange }
        switch step.stage {
        case "rule":  return settings.accentColor
        case "llm":   return .purple
        case "done":  return .green
        default:      return .secondary
        }
    }

    @ViewBuilder
    private func row(_ step: TraceStep, isLast: Bool) -> some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(spacing: 0) {
                ZStack {
                    Circle().fill(color(for: step).opacity(0.18)).frame(width: 30, height: 30)
                    AssistantIcon(icon(for: step.stage), size: 13)
                        .foregroundColor(color(for: step))
                }
                if !isLast || !finished {
                    Rectangle().fill(Color(.separator)).frame(width: 1.5).frame(minHeight: 18)
                }
            }
            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text(step.title).font(.subheadline.weight(.semibold))
                    Spacer()
                    // Always seconds, matching the Mac panel. Two decimals
                    // under a second so a fast step still reads as a duration
                    // instead of flattening to "0.0 s".
                    Text(step.ms >= 999
                         ? String(format: "%.1f s", Double(step.ms) / 1000)
                         : String(format: "%.2f s", Double(step.ms) / 1000))
                        .font(.caption2.monospacedDigit()).foregroundColor(.secondary)
                }
                if !step.detail.isEmpty {
                    Text(step.detail)
                        .font(.footnote)
                        .foregroundColor(step.stage == "error" ? .red : (step.ok ? .primary.opacity(0.8) : .orange))
                        .lineLimit(expanded.contains(step.id) ? nil : 3)
                        .onTapGesture {
                            if expanded.contains(step.id) { expanded.remove(step.id) } else { expanded.insert(step.id) }
                        }
                }
            }
            .padding(.bottom, 14)
        }
    }

    @ViewBuilder
    private func resultCard(_ r: VoiceResponse) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            if let t = r.transcript, !t.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("I heard").font(.caption).foregroundColor(.secondary)
                    if let onFixWord {
                        WrapWords(words: t.split(separator: " ").map(String.init), onTap: onFixWord)
                        Text("Tap a word to fix it").font(.caption2).foregroundColor(.secondary)
                    } else {
                        Text(t).font(.callout)
                    }
                }
            }
            if let c = r.corrections, !c.isEmpty {
                Text("Auto-corrected: " + c.map { "\($0.from) → \($0.to)" }.joined(separator: ", "))
                    .font(.caption).foregroundColor(.green)
            }
            if !r.message.isEmpty {
                Text(r.message).font(.callout.weight(.medium))
            }
            if let u = r.uncertainWords, !u.isEmpty, let onFixWord {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Not sure about these — tap to type the right word")
                        .font(.caption).foregroundColor(.orange)
                    FlowLayout(spacing: 6) {
                        ForEach(u) { w in
                            Button { onFixWord(w.heard) } label: {
                                HStack(spacing: 4) {
                                    Image(systemName: "questionmark.circle").font(.caption)
                                    Text(w.candidate.map { "\(w.heard) → \($0)?" } ?? w.heard)
                                        .font(.caption)
                                }
                                .padding(.horizontal, 8).padding(.vertical, 4)
                                .background(Color.orange.opacity(0.15))
                                .cornerRadius(8)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            if let pid = r.pendingId, let onRetry {
                Button {
                    onRetry(pid)
                } label: {
                    Label("Retry now", systemImage: "arrow.clockwise")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(settings.accentColor)
            }
            if r.memoryId != nil, let onFeedback, !r.actions.isEmpty {
                HStack(spacing: 12) {
                    Text("Was this right?").font(.caption).foregroundColor(.secondary)
                    Spacer()
                    if let f = feedbackSent {
                        HStack(spacing: 4) {
                            AssistantIcon(f == "approved" ? .approved : .rejected, size: 13)
                            Text(f == "approved" ? "Thanks" : "Noted")
                        }
                        .font(.caption).foregroundColor(.secondary)
                    } else {
                        Button { feedbackSent = "approved"; onFeedback("approved") } label: {
                            AssistantIcon(.thumbsUp, size: 16)
                        }
                        Button { feedbackSent = "rejected"; onFeedback("rejected") } label: {
                            AssistantIcon(.thumbsDown, size: 16)
                        }
                    }
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground))
        .cornerRadius(10)
    }
}

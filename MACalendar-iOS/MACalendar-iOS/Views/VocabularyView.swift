import SwiftUI

// MARK: - Vocabulary (teach the assistant your names & words)

/// Settings › Vocabulary. Lists the words the STT layer should know, the
/// aliases it has learned for each ("Kyira" → "Kyra"), and the most recent
/// transcripts so you can tap a misheard word and fix it. Every fix is sent
/// to the Mac (`POST /vocab/alias`) and applied to all future commands on
/// both devices.
struct VocabularyView: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var settings: AppSettings

    @State private var state: VocabState?
    @State private var loading = false
    @State private var error: String?
    @State private var newWord = ""
    @State private var fixTarget: (wrong: String, right: String)? = nil
    @State private var showFix = false
    @FocusState private var wordFocused: Bool
    @State private var showOnboarding = false
    @State private var wordSearch = ""
    @State private var editing: VocabWord? = nil
    @State private var showClearAll = false
    @State private var showImport = false

    /// The words to show: everything, or what the search box matches.
    ///
    /// Matches the word, its label and its expansion, because with a few
    /// hundred entries you are as likely to be looking for "everything tagged
    /// Coursework" as for one particular word.
    private var visibleWords: [VocabWord] {
        let all = state?.words ?? []
        let needle = wordSearch.trimmingCharacters(in: .whitespaces).lowercased()
        guard !needle.isEmpty else { return all }
        return all.filter {
            $0.word.lowercased().contains(needle)
            || $0.label.lowercased().contains(needle)
            || $0.expandsTo.lowercased().contains(needle)
            || $0.aliases.contains { $0.lowercased().contains(needle) }
        }
    }

    var body: some View {
        List {
            if let error {
                Section { Text(error).foregroundColor(.red).font(.footnote) }
            }

            Section {
                Button {
                    showOnboarding = true
                } label: {
                    HStack(spacing: 12) {
                        AssistantIcon(.question, size: 20)
                            .foregroundColor(settings.accentColor)
                        VStack(alignment: .leading, spacing: 2) {
                            Text((state?.onboarded ?? false) ? "Answer the questions again" : "Set up your vocabulary")
                                .font(.body.weight(.medium))
                            Text("A few questions about names, places and Hebrew words — plus starter packs.")
                                .font(.caption).foregroundColor(.secondary)
                        }
                    }
                }
                Button {
                    showImport = true
                } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "square.and.arrow.down.on.square")
                            .font(.title3).foregroundColor(settings.accentColor)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Import from WhatsApp, Contacts or text").font(.body.weight(.medium))
                            Text("Paste a chat export or notes — names and words are picked out for you to approve.")
                                .font(.caption).foregroundColor(.secondary)
                        }
                    }
                }
            }

            Section {
                Toggle("Auto-correct transcripts", isOn: Binding(
                    get: { state?.autoCorrect ?? true },
                    set: { v in Task { await update(autoCorrect: v) } }
                ))
                Toggle("Learn new misspellings automatically", isOn: Binding(
                    get: { state?.learnAliases ?? true },
                    set: { v in Task { await update(learnAliases: v) } }
                ))
                .disabled(!(state?.autoCorrect ?? true))
                HStack {
                    Text("Match strictness")
                    Spacer()
                    Text(String(format: "%.2f", state?.threshold ?? 0.8))
                        .font(.caption.monospacedDigit()).foregroundColor(.secondary)
                }
                Slider(value: Binding(
                    get: { state?.threshold ?? 0.8 },
                    set: { v in Task { await update(threshold: v) } }
                ), in: 0.6...0.95, step: 0.05)
                Text("Lower = fixes more aggressively (risk of false matches). Words are also given to Whisper as a hint, so most names come out right before correction is even needed.")
                    .font(.caption).foregroundColor(.secondary)
            } header: { Text("Auto-correct") }

            Section {
                HStack {
                    TextField("Add a name or word", text: $newWord)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.words)
                        .focused($wordFocused)
                        .onSubmit { Task { await addWord() } }
                    Button { Task { await addWord() } } label: {
                        Image(systemName: "plus.circle.fill").font(.title3)
                    }
                    .disabled(newWord.trimmingCharacters(in: .whitespaces).isEmpty)
                    .tint(settings.accentColor)
                }
                if !visibleWords.isEmpty {
                    ForEach(visibleWords) { w in
                        Button { editing = w } label: {
                            VStack(alignment: .leading, spacing: 3) {
                                HStack(spacing: 6) {
                                    Text(w.word).font(.body.weight(.medium))
                                        .foregroundColor(.primary)
                                    if !w.label.isEmpty {
                                        Text(w.label)
                                            .font(.caption2.weight(.medium))
                                            .padding(.horizontal, 6).padding(.vertical, 1)
                                            .background(Capsule().fill(settings.accentColor.opacity(0.16)))
                                            .foregroundColor(settings.accentColor)
                                    }
                                    Spacer()
                                    if w.hits > 0 {
                                        Text("\(w.hits)×").font(.caption2).foregroundColor(.secondary)
                                    }
                                    Image(systemName: "chevron.right")
                                        .font(.caption2).foregroundColor(.secondary)
                                }
                                // The three things a word can do, each said in
                                // the words the feature uses elsewhere.
                                if !w.expandsTo.isEmpty {
                                    Text("short for \(w.expandsTo)")
                                        .font(.caption).foregroundColor(.secondary)
                                }
                                if !w.aliases.isEmpty {
                                    Text("heard as: " + w.aliases.joined(separator: ", "))
                                        .font(.caption).foregroundColor(.secondary)
                                }
                            }
                        }
                        .buttonStyle(.plain)
                        .swipeActions(edge: .trailing) {
                            Button(role: .destructive) {
                                Task { try? await api.vocabDelete(word: w.word); await load() }
                            } label: { Label("Delete", systemImage: "trash") }
                        }
                    }
                } else if !loading {
                    Text(wordSearch.isEmpty
                         ? "No words yet. Add names of people, places, or words the assistant keeps getting wrong."
                         : "No word matches “\(wordSearch)”.")
                        .font(.footnote).foregroundColor(.secondary)
                }
            } header: {
                HStack {
                    Text("Your words (\(state?.words.count ?? 0))")
                    Spacer()
                    if (state?.words.count ?? 0) > 12 {
                        Button(role: .destructive) { showClearAll = true } label: {
                            Text("Clear all").font(.caption)
                        }
                    }
                }
            } footer: {
                Text("Tap a word to set what it means, or what it is short for.")
            }

            Section {
                if let recent = state?.recent, !recent.isEmpty {
                    ForEach(recent) { r in
                        RecentTranscriptRow(item: r) { word in
                            fixTarget = (wrong: word, right: word)
                            showFix = true
                        }
                    }
                } else if !loading {
                    Text("Recent voice commands will appear here. Tap any word to correct it.")
                        .font(.footnote).foregroundColor(.secondary)
                }
            } header: { Text("Recent transcripts — tap a word to fix it") }
        }
        .navigationTitle("Vocabulary")
        .searchable(text: $wordSearch, prompt: "Search your words")
        .refreshable { await load() }
        .task { await load() }
        .sheet(item: $editing) { word in
            NavigationStack {
                VocabWordEditor(word: word) { label, expandsTo, aliases in
                    try? await api.vocabUpdate(word: word.word, label: label,
                                               expandsTo: expandsTo, aliases: aliases)
                    await load()
                }
            }
            .presentationDetents([.medium, .large])
        }
        .alert("Clear the whole word list?", isPresented: $showClearAll) {
            Button("Cancel", role: .cancel) {}
            Button("Delete \(state?.words.count ?? 0) words", role: .destructive) {
                Task { await clearAllWords() }
            }
        } message: {
            Text("This removes every word, along with its corrections and labels. "
                 + "It cannot be undone, and the assistant will start mishearing "
                 + "names it currently gets right.")
        }
        .overlay { if loading && state == nil { ProgressView() } }
        .sheet(isPresented: $showImport, onDismiss: { Task { await load() } }) {
            VocabImportView()
        }
        .sheet(isPresented: $showOnboarding, onDismiss: { Task { await load() } }) {
            VocabOnboardingView()
        }
        .sheet(isPresented: $showFix) {
            if let t = fixTarget {
                FixWordSheet(wrong: t.wrong, initial: t.right) { right in
                    Task {
                        do { try await api.vocabTeach(wrong: t.wrong, right: right); await load() }
                        catch { self.error = error.localizedDescription }
                    }
                }
                .presentationDetents([.height(260)])
            }
        }
    }

    /// Delete every word, one call each — there is no bulk-delete endpoint,
    /// and inventing one for a button that should be pressed approximately
    /// never is the wrong trade.
    private func clearAllWords() async {
        for word in state?.words ?? [] {
            try? await api.vocabDelete(word: word.word)
        }
        await load()
    }

    private func load() async {
        loading = true
        defer { loading = false }
        do { state = try await api.vocab(); error = nil }
        catch { self.error = "Couldn't reach the Mac: \(error.localizedDescription)" }
    }

    private func addWord() async {
        let w = newWord.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !w.isEmpty else { return }
        do { try await api.vocabAddWord(w); newWord = ""; await load() }
        catch { self.error = error.localizedDescription }
    }

    private func update(autoCorrect: Bool? = nil, learnAliases: Bool? = nil, threshold: Double? = nil) async {
        do { state = try await api.vocabSettings(autoCorrect: autoCorrect, learnAliases: learnAliases, threshold: threshold) }
        catch { self.error = error.localizedDescription }
    }
}

/// One past transcript rendered as tappable word chips.
private struct RecentTranscriptRow: View {
    let item: VocabRecent
    let onTap: (String) -> Void

    private var words: [String] {
        item.corrected.split(separator: " ").map(String.init)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                AssistantIcon(item.source == "ios" ? .iphone : .mac, size: 12)
                    .foregroundColor(.secondary)
                Text(Date(timeIntervalSince1970: item.ts), style: .relative)
                    .font(.caption2).foregroundColor(.secondary)
                if !item.corrections.isEmpty {
                    Text("· fixed " + item.corrections.map { "\($0.from)→\($0.to)" }.joined(separator: ", "))
                        .font(.caption2).foregroundColor(.green)
                }
            }
            WrapWords(words: words, onTap: onTap)
        }
        .padding(.vertical, 2)
    }
}

/// Flow layout of word chips.
private struct WrapWords: View {
    let words: [String]
    let onTap: (String) -> Void

    var body: some View {
        FlowLayout(spacing: 4) {
            ForEach(Array(words.enumerated()), id: \.offset) { _, w in
                Button { onTap(w.trimmingCharacters(in: .punctuationCharacters)) } label: {
                    Text(w)
                        .font(.callout)
                        .padding(.horizontal, 6).padding(.vertical, 3)
                        .background(Color(.tertiarySystemFill))
                        .cornerRadius(6)
                }
                .buttonStyle(.plain)
            }
        }
    }
}

/// Minimal wrapping HStack (iOS 16+ Layout).
private struct FlowLayout: Layout {
    var spacing: CGFloat = 4

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, rowH: CGFloat = 0
        for s in subviews {
            let sz = s.sizeThatFits(.unspecified)
            if x + sz.width > width, x > 0 { x = 0; y += rowH + spacing; rowH = 0 }
            x += sz.width + spacing
            rowH = max(rowH, sz.height)
        }
        return CGSize(width: width == .infinity ? x : width, height: y + rowH)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, rowH: CGFloat = 0
        for s in subviews {
            let sz = s.sizeThatFits(.unspecified)
            if x + sz.width > bounds.maxX, x > bounds.minX { x = bounds.minX; y += rowH + spacing; rowH = 0 }
            s.place(at: CGPoint(x: x, y: y), proposal: .unspecified)
            x += sz.width + spacing
            rowH = max(rowH, sz.height)
        }
    }
}

private struct FixWordSheet: View {
    let wrong: String
    @State var right: String
    let onSave: (String) -> Void
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: Bool

    init(wrong: String, initial: String, onSave: @escaping (String) -> Void) {
        self.wrong = wrong
        self._right = State(initialValue: initial)
        self.onSave = onSave
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Fix a word").font(.headline)
            HStack {
                Text("Heard").foregroundColor(.secondary)
                Spacer()
                Text(wrong).font(.body.weight(.medium))
            }
            HStack {
                Text("Should be").foregroundColor(.secondary)
                TextField("Correct word", text: $right)
                    .multilineTextAlignment(.trailing)
                    .autocorrectionDisabled()
                    .focused($focused)
                    .onSubmit(save)
            }
            Text("From now on, whenever the assistant hears “\(wrong)” (or something close), it will use your word.")
                .font(.caption).foregroundColor(.secondary)
            Button(action: save) {
                Text("Teach it").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(right.trimmingCharacters(in: .whitespaces).isEmpty || right == wrong)
        }
        .padding(20)
        .onAppear { focused = true }
    }

    private func save() {
        let r = right.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !r.isEmpty, r != wrong else { return }
        onSave(r)
        dismiss()
    }
}

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
                }
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
                        Text(stateMark(i, state))
                            .font(.caption2)
                            .foregroundColor(slotColor(i, state))
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

    /// Which slots are done and which is live — mapped from the live steps by
    /// stage, in order (mirrors the Mac panel's `_ChainRail.observe`).
    private func railState(_ slots: [ChainSlot]) -> (done: Set<Int>, active: Int?) {
        var done = Set<Int>()
        var active: Int? = nil
        var ptr = 0
        for step in steps {
            let stage = step.stage
            if stage == "stt" || stage == "memory" || stage == "error" { continue }
            var mapped = false
            var i = ptr
            while i < slots.count {
                if slots[i].stage == stage {
                    if let a = active { done.insert(a) }
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
        return (done, active)
    }

    private func slotColor(_ i: Int, _ state: (done: Set<Int>, active: Int?)) -> Color {
        if state.done.contains(i) { return .green }
        if i == state.active && !finished { return settings.accentColor }
        return .secondary.opacity(0.5)
    }

    private func stateMark(_ i: Int, _ state: (done: Set<Int>, active: Int?)) -> String {
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


// MARK: - Editing one word

/// What a word means, and what it is short for.
///
/// These two fields change how commands are interpreted — a label decides how
/// a task is tagged — and until now they existed only in a JSON file on the
/// Mac. A wrong label has no visible symptom beyond tasks quietly filing
/// themselves in the wrong place, so being able to see and change one matters
/// more than the size of the screen suggests.
struct VocabWordEditor: View {
    let word: VocabWord
    /// (label, expansion, aliases) — all three sent together, since the screen
    /// shows all three and a partial save would drop what it did not send.
    let onSave: (String, String, [String]) async -> Void

    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var settings: AppSettings

    @State private var label: String
    @State private var expandsTo: String
    @State private var aliases: [String]
    @State private var newAlias = ""
    @State private var saving = false

    init(word: VocabWord, onSave: @escaping (String, String, [String]) async -> Void) {
        self.word = word
        self.onSave = onSave
        _label     = State(initialValue: word.label)
        _expandsTo = State(initialValue: word.expandsTo)
        _aliases   = State(initialValue: word.aliases)
    }

    var body: some View {
        Form {
            Section {
                TextField("Coursework, Groceries, Errands…", text: $label)
                    .textInputAutocapitalization(.words)
            } header: {
                Text("What it means")
            } footer: {
                Text("A task or event mentioning “\(word.word)” gets this tag. "
                     + "Leave it empty for no tag.")
            }

            Section {
                TextField("What it stands for", text: $expandsTo)
            } header: {
                Text("Short for")
            } footer: {
                Text("Only for shorthand you actually say. It is never "
                     + "substituted into your words — the assistant is just "
                     + "told what it means.")
            }

            Section {
                ForEach(aliases, id: \.self) { alias in
                    Text(alias).foregroundColor(.secondary)
                }
                .onDelete { aliases.remove(atOffsets: $0) }

                HStack {
                    TextField("Add a misheard spelling", text: $newAlias)
                        .autocorrectionDisabled()
                        .onSubmit(addAlias)
                    Button(action: addAlias) {
                        Image(systemName: "plus.circle.fill")
                    }
                    .disabled(newAlias.trimmingCharacters(in: .whitespaces).isEmpty)
                    .tint(settings.accentColor)
                }
            } header: {
                Text("Heard as")
            } footer: {
                Text("Transcripts containing any of these are rewritten to "
                     + "“\(word.word)”. Swipe to remove one.")
            }
        }
        .navigationTitle(word.word)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("Cancel") { dismiss() }
            }
            ToolbarItem(placement: .confirmationAction) {
                Button("Save") {
                    saving = true
                    Task {
                        await onSave(label.trimmingCharacters(in: .whitespaces),
                                     expandsTo.trimmingCharacters(in: .whitespaces),
                                     aliases)
                        dismiss()
                    }
                }
                .disabled(saving)
            }
        }
    }

    private func addAlias() {
        let value = newAlias.trimmingCharacters(in: .whitespaces)
        // An alias equal to the word would make the corrector rewrite it to
        // itself; the server drops those too, but saying so here is clearer
        // than a silent no-op.
        guard !value.isEmpty,
              value.lowercased() != word.word.lowercased(),
              !aliases.contains(where: { $0.lowercased() == value.lowercased() })
        else { newAlias = ""; return }
        aliases.append(value)
        newAlias = ""
    }
}

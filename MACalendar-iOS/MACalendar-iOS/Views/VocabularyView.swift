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
    @State private var showImport = false

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
                if let words = state?.words, !words.isEmpty {
                    ForEach(words) { w in
                        VStack(alignment: .leading, spacing: 3) {
                            HStack {
                                Text(w.word).font(.body.weight(.medium))
                                Spacer()
                                if w.hits > 0 {
                                    Text("\(w.hits)×").font(.caption2).foregroundColor(.secondary)
                                }
                            }
                            if !w.aliases.isEmpty {
                                Text("heard as: " + w.aliases.joined(separator: ", "))
                                    .font(.caption).foregroundColor(.secondary)
                            }
                        }
                        .swipeActions(edge: .trailing) {
                            Button(role: .destructive) {
                                Task { try? await api.vocabDelete(word: w.word); await load() }
                            } label: { Label("Delete", systemImage: "trash") }
                        }
                    }
                } else if !loading {
                    Text("No words yet. Add names of people, places, or Hebrew words the assistant keeps getting wrong.")
                        .font(.footnote).foregroundColor(.secondary)
                }
            } header: { Text("Your words (\(state?.words.count ?? 0))") }

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
        .refreshable { await load() }
        .task { await load() }
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
    @Environment(\.dismiss) private var dismiss
    @State private var expanded: Set<String> = []
    @State private var feedbackSent: String? = nil

    var body: some View {
        NavigationView {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
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
                    }
                    .padding(16)
                    .animation(.easeOut(duration: 0.25), value: steps.count)
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
        if !step.ok { return .red }
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
                        .foregroundColor(step.ok ? .primary.opacity(0.8) : .red)
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

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

/// Flow layout of word chips. Not private: ThinkingView's result card
/// renders the transcript with the same chips.
struct WrapWords: View {
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

/// Minimal wrapping HStack (iOS 16+ Layout). Not private: ThinkingView's
/// uncertain-word chips use it too.
struct FlowLayout: Layout {
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

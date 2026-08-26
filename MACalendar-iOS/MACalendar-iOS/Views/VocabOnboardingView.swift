import SwiftUI

/// First-run "vocabulary interview": a few questions whose answers seed the
/// assistant's personal vocabulary (names, places, Hebrew terms…) plus
/// opt-in preset packs. Answers go to the Mac's local vocab.json only.
struct VocabOnboardingView: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var settings: AppSettings
    @Environment(\.dismiss) private var dismiss
    var onFinished: (() -> Void)? = nil

    @State private var payload: VocabOnboarding?
    @State private var answers: [String: String] = [:]
    @State private var chosenPresets: Set<String> = []
    @State private var page = 0          // 0 = intro, 1...n = questions, n+1 = presets
    @State private var saving = false
    @State private var error: String?
    @FocusState private var focused: Bool

    private var questions: [VocabQuestion] { payload?.questions ?? [] }
    private var lastPage: Int { questions.count + 1 }

    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                if let p = payload {
                    ProgressView(value: Double(page), total: Double(lastPage))
                        .tint(settings.accentColor)
                        .padding(.horizontal)
                    TabView(selection: $page) {
                        intro(p).tag(0)
                        ForEach(Array(questions.enumerated()), id: \.element.id) { i, q in
                            questionPage(q).tag(i + 1)
                        }
                        presetsPage(p).tag(lastPage)
                    }
                    .tabViewStyle(.page(indexDisplayMode: .never))
                    .animation(.easeInOut, value: page)

                    HStack {
                        if page > 0 {
                            Button("Back") { page -= 1 }
                        }
                        Spacer()
                        if page < lastPage {
                            Button(page == 0 ? "Start" : "Next") { page += 1 }
                                .buttonStyle(.borderedProminent).tint(settings.accentColor)
                        } else {
                            Button { Task { await save() } } label: {
                                if saving { ProgressView() } else { Text("Save \(pendingCount) words") }
                            }
                            .buttonStyle(.borderedProminent).tint(settings.accentColor)
                            .disabled(saving)
                        }
                    }
                    .padding()
                } else if let error {
                    VStack(spacing: 12) {
                        Text(error).foregroundColor(.red).multilineTextAlignment(.center)
                        Button("Try again") { Task { await load() } }
                    }.padding()
                } else {
                    ProgressView("Loading…")
                }
            }
            .navigationTitle("Teach it your words")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Later") { skip() }
                }
            }
        }
        .task { await load() }
    }

    private var pendingCount: Int {
        let typed = answers.values.flatMap { $0.split(separator: ",") }
            .map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }.count
        let preset = (payload?.presets ?? []).filter { chosenPresets.contains($0.id) }
            .map { $0.words.count - $0.already }.reduce(0, +)
        return typed + preset
    }

    @ViewBuilder
    private func intro(_ p: VocabOnboarding) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Image(systemName: "character.book.closed.fill")
                    .font(.system(size: 44)).foregroundColor(settings.accentColor)
                Text("Speech recognition is trained on English. Names, Hebrew words and places it has never heard get mangled — “Shaul” becomes “Shawl”.")
                Text("Answer a few quick questions (skip any you like). The assistant will hear those words correctly from now on, and keep learning from your fixes.")
                Label("Stored only on your Mac — never uploaded or committed.", systemImage: "lock.fill")
                    .font(.footnote).foregroundColor(.secondary)
                if p.wordCount > 0 {
                    Text("You already have \(p.wordCount) words. Anything you add here is merged in.")
                        .font(.footnote).foregroundColor(.secondary)
                }
            }
            .padding(24)
        }
    }

    @ViewBuilder
    private func questionPage(_ q: VocabQuestion) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text(q.question).font(.title3.weight(.semibold))
                Text(q.hint).font(.subheadline).foregroundColor(.secondary)
                TextEditor(text: Binding(
                    get: { answers[q.id] ?? "" },
                    set: { answers[q.id] = $0 }
                ))
                .frame(minHeight: 110)
                .padding(8)
                .background(Color(.secondarySystemBackground))
                .cornerRadius(10)
                .autocorrectionDisabled()
                .focused($focused)
                Text("Separate words with commas.").font(.caption).foregroundColor(.secondary)
                if !q.examples.isEmpty {
                    HStack(spacing: 6) {
                        Text("e.g.").font(.caption).foregroundColor(.secondary)
                        ForEach(q.examples, id: \.self) { ex in
                            Button(ex) {
                                let cur = answers[q.id] ?? ""
                                answers[q.id] = cur.isEmpty ? ex : cur + ", " + ex
                            }
                            .font(.caption)
                            .buttonStyle(.bordered)
                        }
                    }
                }
            }
            .padding(24)
        }
        .onTapGesture { focused = false }
    }

    @ViewBuilder
    private func presetsPage(_ p: VocabOnboarding) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("Add a starter pack?").font(.title3.weight(.semibold))
                Text("Common words in Jewish and Israeli life. Turn on the ones you use — you can delete individual words later.")
                    .font(.subheadline).foregroundColor(.secondary)
                ForEach(p.presets) { pack in
                    Toggle(isOn: Binding(
                        get: { chosenPresets.contains(pack.id) },
                        set: { on in if on { chosenPresets.insert(pack.id) } else { chosenPresets.remove(pack.id) } }
                    )) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(pack.label).font(.body.weight(.medium))
                            Text(pack.words.prefix(6).joined(separator: ", ") + (pack.words.count > 6 ? "…" : ""))
                                .font(.caption).foregroundColor(.secondary).lineLimit(2)
                        }
                    }
                    .tint(settings.accentColor)
                }
            }
            .padding(24)
        }
    }

    private func load() async {
        do { payload = try await api.vocabOnboarding(); error = nil }
        catch { self.error = "Couldn't reach the Mac: \(error.localizedDescription)" }
    }

    private func save() async {
        saving = true
        defer { saving = false }
        var lists: [String: [String]] = [:]
        for (k, v) in answers {
            lists[k] = v.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        }
        do {
            try await api.vocabOnboardingSubmit(answers: lists, presets: Array(chosenPresets))
            settings.vocabOnboardingDone = true
            onFinished?()
            dismiss()
        } catch { self.error = error.localizedDescription }
    }

    private func skip() {
        settings.vocabOnboardingDone = true   // don't nag again; reachable from Settings › Vocabulary
        dismiss()
    }
}

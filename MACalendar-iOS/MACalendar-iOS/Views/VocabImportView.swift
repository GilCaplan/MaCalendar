import SwiftUI
import Contacts
import UniformTypeIdentifiers

/// Text handed to the app from the share sheet ("Export Chat" → MACalendar).
/// MACalendarApp fills it in from onOpenURL; ContentView presents the import
/// screen when it changes.
final class ImportInbox: ObservableObject {
    static let shared = ImportInbox()
    @Published var pendingText: String? = nil
    @Published var pendingName: String = ""
}

/// Import vocabulary from text you already have: a WhatsApp export, notes
/// about yourself, your Contacts, or your own calendar titles.
/// The text is scanned on your Mac for names and non-English words; only the
/// words you tick are kept. The text itself is never stored.
struct VocabImportView: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var settings: AppSettings
    @Environment(\.dismiss) private var dismiss

    /// Pre-filled when opened from the share sheet.
    var initialText: String? = nil
    var initialName: String = ""

    @State private var text = ""
    @State private var sourceName = ""
    @State private var candidates: [VocabCandidate] = []
    @State private var selected: Set<String> = []
    @State private var loading = false
    @State private var error: String?
    @State private var addedCount: Int?
    @State private var showFilePicker = false
    @State private var showHowTo = false
    @State private var scannedOnce = false
    @FocusState private var textFocused: Bool

    private var grouped: [(String, [VocabCandidate])] {
        let order = ["sender", "contact", "name", "hebrew", "non-english"]
        let labels = ["sender": "People in the chat", "contact": "Contacts", "name": "Names & places",
                      "hebrew": "Hebrew", "non-english": "Non-English words"]
        return order.compactMap { key in
            let items = candidates.filter { $0.reason == key }
            return items.isEmpty ? nil : (labels[key] ?? key, items)
        }
    }

    var body: some View {
        NavigationView {
            List {
                privacySection

                if let error { Section { Text(error).foregroundColor(.red).font(.footnote) } }
                if let n = addedCount {
                    Section {
                        Label("Added \(n) words. They'll be used from your next voice command.", systemImage: "checkmark.circle")
                            .foregroundColor(.green)
                    }
                }

                if !scannedOnce { sourcesSection }

                if scannedOnce && candidates.isEmpty && !loading {
                    Section {
                        Text("Nothing new found — everything in that text is either already in your vocabulary or ordinary English.")
                            .font(.footnote).foregroundColor(.secondary)
                        Button("Scan something else") { reset() }
                    }
                }

                ForEach(grouped, id: \.0) { label, items in
                    Section {
                        ForEach(items) { c in candidateRow(c) }
                    } header: {
                        HStack {
                            Text("\(label) (\(items.count))")
                            Spacer()
                            Button(items.allSatisfy { selected.contains($0.word) } ? "None" : "All") {
                                if items.allSatisfy({ selected.contains($0.word) }) {
                                    items.forEach { selected.remove($0.word) }
                                } else {
                                    items.forEach { selected.insert($0.word) }
                                }
                            }
                            .font(.caption)
                        }
                    }
                }

                if scannedOnce && !candidates.isEmpty {
                    Section {
                        Text("Tick the words the assistant should know. People and Hebrew are pre-ticked; skim “Names & places” — it can include ordinary capitalised words.")
                            .font(.caption).foregroundColor(.secondary)
                        Button("Scan something else") { reset() }
                    }
                }
            }
            .navigationTitle(scannedOnce ? "Choose words" : "Import words")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) { Button("Close") { dismiss() } }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Add \(selected.count)") { Task { await addSelected() } }
                        .disabled(selected.isEmpty || loading)
                        .fontWeight(.semibold)
                }
            }
            .overlay {
                if loading {
                    ZStack {
                        Color.black.opacity(0.15).ignoresSafeArea()
                        VStack(spacing: 10) {
                            ProgressView()
                            Text("Scanning on your Mac…").font(.footnote)
                        }
                        .padding(20).background(.regularMaterial).cornerRadius(12)
                    }
                }
            }
            .sheet(isPresented: $showHowTo) { WhatsAppHowToView() }
            .fileImporter(isPresented: $showFilePicker,
                          allowedContentTypes: [.plainText, .text, .utf8PlainText],
                          allowsMultipleSelection: false) { result in
                switch result {
                case .success(let urls):
                    guard let url = urls.first else { return }
                    loadFile(url)
                case .failure(let err):
                    error = err.localizedDescription
                }
            }
            .onAppear {
                if let t = initialText, text.isEmpty {
                    text = t
                    sourceName = initialName
                    Task { await scanText() }
                }
            }
        }
    }

    // MARK: - Sections

    private var privacySection: some View {
        Section {
            VStack(alignment: .leading, spacing: 8) {
                Label("Stays on your Mac", systemImage: "lock.shield")
                    .font(.subheadline.weight(.semibold))
                Text("The text you import is scanned once for names and words the speech recogniser tends to get wrong. Only the words you tick are saved (to a file on your Mac). The messages themselves are not stored, not uploaded, and not sent to any AI service.")
                    .font(.footnote).foregroundColor(.secondary)
            }
            .padding(.vertical, 2)
        }
    }

    private var sourcesSection: some View {
        Group {
            Section {
                Button { showHowTo = true } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "questionmark.circle").font(.title3).foregroundColor(settings.accentColor)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("How to export a WhatsApp chat").font(.body.weight(.medium))
                            Text("Step by step — takes about 20 seconds").font(.caption).foregroundColor(.secondary)
                        }
                    }
                }
                Button { showFilePicker = true } label: {
                    Label("Choose an exported .txt file", systemImage: "doc.text")
                }
            } header: { Text("WhatsApp chat") } footer: {
                Text("Tip: from WhatsApp's Export Chat screen you can also share the file straight to MACalendar — it opens here automatically.")
            }

            Section {
                TextEditor(text: $text)
                    .frame(minHeight: 110)
                    .autocorrectionDisabled()
                    .focused($textFocused)
                HStack {
                    Button {
                        if let s = UIPasteboard.general.string { text = s; sourceName = "clipboard" }
                    } label: { Label("Paste", systemImage: "doc.on.clipboard") }
                    Spacer()
                    Button { Task { await scanText() } } label: { Label("Find words", systemImage: "magnifyingglass") }
                        .buttonStyle(.borderedProminent).tint(settings.accentColor)
                        .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || loading)
                }
            } header: { Text("Or paste any text") } footer: {
                Text("Anything works: a chat, notes about yourself, an email, a list of names. Hebrew is fine.")
            }

            Section {
                Button { Task { await importContacts() } } label: {
                    Label("Scan my Contacts", systemImage: "person.crop.circle")
                }
                Button { Task { await scanCalendar() } } label: {
                    Label("Scan my calendar & task titles", systemImage: "calendar")
                }
            } header: { Text("Or pull from") } footer: {
                Text("Contacts: first names (and unusual surnames) only; the contact list itself is not kept.")
            }
        }
    }

    @ViewBuilder
    private func candidateRow(_ c: VocabCandidate) -> some View {
        Button {
            if selected.contains(c.word) { selected.remove(c.word) } else { selected.insert(c.word) }
        } label: {
            HStack {
                Image(systemName: selected.contains(c.word) ? "checkmark.square.fill" : "square")
                    .foregroundColor(selected.contains(c.word) ? settings.accentColor : .secondary)
                VStack(alignment: .leading, spacing: 1) {
                    Text(c.word).foregroundColor(.primary)
                    if !c.sample.isEmpty, c.sample != c.word {
                        Text(c.sample).font(.caption2).foregroundColor(.secondary)
                    }
                }
                Spacer()
                if c.count > 1 {
                    Text("\(c.count)×").font(.caption2.monospacedDigit()).foregroundColor(.secondary)
                }
            }
        }
    }

    // MARK: - Actions

    private func reset() {
        candidates = []; selected = []; text = ""; sourceName = ""; scannedOnce = false; addedCount = nil; error = nil
    }

    private func show(_ found: [VocabCandidate]) {
        candidates = found
        selected = Set(found.filter { $0.reason == "sender" || $0.reason == "contact" || $0.reason == "hebrew" }.map(\.word))
        addedCount = nil
        error = nil
        scannedOnce = true
    }

    private func loadFile(_ url: URL) {
        let accessed = url.startAccessingSecurityScopedResource()
        defer { if accessed { url.stopAccessingSecurityScopedResource() } }
        do {
            let data = try Data(contentsOf: url)
            // WhatsApp exports are UTF-8; fall back to Latin-1 (the Mac repairs mojibake anyway)
            text = String(data: data, encoding: .utf8) ?? String(data: data, encoding: .isoLatin1) ?? ""
            sourceName = url.lastPathComponent
            Task { await scanText() }
        } catch { self.error = "Couldn't read that file: \(error.localizedDescription)" }
    }

    private func scanText() async {
        textFocused = false
        loading = true; defer { loading = false }
        do { show(try await api.vocabImport(text: text)) }
        catch { self.error = "Couldn't reach the Mac: \(error.localizedDescription)" }
    }

    private func scanCalendar() async {
        loading = true; defer { loading = false }
        do { show(try await api.vocabImport(source: "calendar")) }
        catch { self.error = error.localizedDescription }
    }

    private func importContacts() async {
        loading = true; defer { loading = false }
        let store = CNContactStore()
        do {
            let granted = try await store.requestAccess(for: .contacts)
            guard granted else { error = "Contacts access was denied. You can allow it in Settings › Privacy › Contacts."; return }
            let keys = [CNContactGivenNameKey, CNContactFamilyNameKey, CNContactNicknameKey] as [CNKeyDescriptor]
            let req = CNContactFetchRequest(keysToFetch: keys)
            var names: [String] = []
            try store.enumerateContacts(with: req) { c, _ in
                let n = [c.givenName, c.familyName].filter { !$0.isEmpty }.joined(separator: " ")
                if !n.isEmpty { names.append(n) }
                if !c.nickname.isEmpty { names.append(c.nickname) }
            }
            show(try await api.vocabImport(names: names))
        } catch { self.error = error.localizedDescription }
    }

    private func addSelected() async {
        loading = true; defer { loading = false }
        let words = Array(selected)
        do {
            try await api.vocabAddWords(words)
            addedCount = words.count
            candidates.removeAll { selected.contains($0.word) }
            selected = []
        } catch { self.error = error.localizedDescription }
    }
}

/// Numbered walkthrough for exporting a chat from WhatsApp on iPhone.
struct WhatsAppHowToView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var settings: AppSettings

    private let steps: [(String, String)] = [
        ("Open the chat in WhatsApp", "A small group or a one-to-one chat with a close friend works best — that's where your names and slang live."),
        ("Tap the name at the top", "This opens the chat info screen."),
        ("Scroll down and tap “Export Chat”", "On some versions it's under the ⋯ menu or “More”."),
        ("Choose “Without Media”", "Photos and voice notes aren't needed and make the file huge."),
        ("Share it to MACalendar", "In the share sheet pick MACalendar — the words appear here to review. Or tap “Save to Files” and use “Choose an exported .txt file”."),
    ]

    var body: some View {
        NavigationView {
            List {
                Section {
                    ForEach(Array(steps.enumerated()), id: \.offset) { i, step in
                        HStack(alignment: .top, spacing: 14) {
                            Text("\(i + 1)")
                                .font(.subheadline.weight(.bold))
                                .frame(width: 26, height: 26)
                                .background(settings.accentColor.opacity(0.18))
                                .foregroundColor(settings.accentColor)
                                .clipShape(Circle())
                            VStack(alignment: .leading, spacing: 3) {
                                Text(step.0).font(.body.weight(.medium))
                                Text(step.1).font(.footnote).foregroundColor(.secondary)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }
                Section {
                    Label("Nothing from the chat is kept. It's scanned once for names and words, you pick which to keep, and the text is discarded.",
                          systemImage: "lock.shield")
                        .font(.footnote).foregroundColor(.secondary)
                    Label("Export a chat per close friend or family group — three or four chats cover most of the names you'll ever say.",
                          systemImage: "lightbulb")
                        .font(.footnote).foregroundColor(.secondary)
                }
            }
            .navigationTitle("Export from WhatsApp")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .navigationBarTrailing) { Button("Done") { dismiss() } } }
        }
    }
}

import SwiftUI

/// "Was this right?" — a quick pass over recent voice commands that have no
/// feedback yet. Each 👍 / 👎 / fix feeds the command memory on the Mac so the
/// assistant's few-shot examples reflect what you actually meant.
struct AssistantReviewView: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var settings: AppSettings
    @Environment(\.dismiss) private var dismiss

    @State private var items: [MemoryExample] = []
    @State private var loading = false
    @State private var error: String?
    @State private var done = 0
    @State private var confirmSkip = false

    var body: some View {
        NavigationView {
            Group {
                if let error {
                    VStack(spacing: 10) { Text(error).foregroundColor(.red).multilineTextAlignment(.center); Button("Try again") { Task { await load() } } }.padding()
                } else if items.isEmpty && !loading {
                    VStack(spacing: 10) {
                        AssistantIcon(.approved).frame(width: 40, height: 40).foregroundColor(.green)
                        Text(done > 0 ? "All caught up — \(done) reviewed." : "Nothing to review").font(.headline)
                        Text("Every voice command shows up here until you've said whether it was right. Takes a few seconds a day and makes the assistant learn your phrasing.")
                            .font(.footnote).foregroundColor(.secondary).multilineTextAlignment(.center)
                    }.padding(30)
                } else {
                    List {
                        Section {
                            Text("\(items.count) to review · tap 👍 if it did the right thing, 👎 if not. Only what you tick is stored.")
                                .font(.footnote).foregroundColor(.secondary)
                        }
                        ForEach(items) { ex in
                            ReviewRow(example: ex) { verdict in Task { await send(ex, verdict) } }
                        }
                    }
                }
            }
            .navigationTitle("Review commands")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    if !items.isEmpty {
                        Button("Dismiss all") { confirmSkip = true }
                            .confirmationDialog("Dismiss all \(items.count) without a verdict? They won't count as right or wrong.",
                                                isPresented: $confirmSkip, titleVisibility: .visible) {
                                Button("Dismiss all", role: .destructive) { Task { _ = await api.skipAllUnreviewed(); items = []; done = 0 } }
                            }
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) { Button("Done") { dismiss() } }
            }
            .overlay { if loading && items.isEmpty { ProgressView() } }
            .task { await load() }
            .refreshable { await load() }
        }
    }

    private func load() async {
        loading = true; defer { loading = false }
        do { items = try await api.unreviewedCommands(); error = nil }
        catch {
            // A cancelled request (sheet closed / view refreshed mid-flight) is not an outage.
            if error is CancellationError || (error as? URLError)?.code == .cancelled
                || error.localizedDescription.lowercased().contains("cancel") { return }
            self.error = "Couldn't reach the Mac: \(error.localizedDescription)"
        }
    }

    private func send(_ ex: MemoryExample, _ verdict: String) async {
        await api.memoryFeedback(id: ex.id, feedback: verdict)
        withAnimation { items.removeAll { $0.id == ex.id } }
        done += 1
    }
}

private struct ReviewRow: View {
    let example: MemoryExample
    let onVerdict: (String) -> Void
    @EnvironmentObject var settings: AppSettings

    private var summary: String {
        example.actions.map { a in
            let p = a.parameters
            switch a.action {
            case "create_event", "update_event":
                let real = example.resolved?.first { $0.type == "event" && ($0.title == p["title"]?.stringValue || example.resolved?.count == 1) }
                let t = real?.title ?? p["title"]?.stringValue ?? "event"
                let date = real?.date ?? p["date"]?.stringValue
                let time = (real?.startTime).flatMap { $0.isEmpty ? nil : $0 } ?? p["start_time"]?.stringValue
                let when = [date.map(Self.prettyDate), time].compactMap { $0 }.joined(separator: " ")
                return "\(a.action == "update_event" ? "Updated event" : "Event"): \(t)\(when.isEmpty ? "" : " · " + when)"
            case "create_todo":
                let titles = (p["titles"]?.arrayValue ?? []).compactMap { $0.stringValue }
                return "Task\(titles.count > 1 ? "s" : ""): " + titles.joined(separator: ", ")
            case "delete_event": return "Deleted event \(p["match_title"]?.stringValue ?? "")"
            case "query_schedule": return "Read schedule"
            default: return a.action.replacingOccurrences(of: "_", with: " ")
            }
        }.joined(separator: " · ")
    }

    /// "2026-08-27" → "Thu 27 Aug"
    static func prettyDate(_ iso: String) -> String {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"
        guard let d = f.date(from: iso) else { return iso }
        let o = DateFormatter(); o.dateFormat = "EEE d MMM"
        return o.string(from: d)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                AssistantIcon(example.source == "ios" ? .iphone : .mac).frame(width: 14, height: 14).foregroundColor(.secondary)
                Text(example.time.replacingOccurrences(of: "T", with: " ").prefix(16)).font(.caption2).foregroundColor(.secondary)
                Spacer()
                Text(example.parsePath).font(.caption2.monospaced()).foregroundColor(.secondary)
            }
            Text("“\(example.transcript)”").font(.callout)
            Text(summary).font(.footnote).foregroundColor(.secondary)
            HStack(spacing: 18) {
                Button { onVerdict("approved") } label: {
                    Label("Right", systemImage: "").labelStyle(.titleOnly).frame(minWidth: 70)
                        .overlay(alignment: .leading) { AssistantIcon(.thumbsUp).frame(width: 16, height: 16).offset(x: -22) }
                }
                .buttonStyle(.bordered).tint(.green)
                Button { onVerdict("rejected") } label: {
                    Text("Wrong").frame(minWidth: 70)
                        .overlay(alignment: .leading) { AssistantIcon(.thumbsDown).frame(width: 16, height: 16).offset(x: -22) }
                }
                .buttonStyle(.bordered).tint(.red)
                Spacer()
            }
            .padding(.leading, 22)
        }
        .padding(.vertical, 4)
    }
}

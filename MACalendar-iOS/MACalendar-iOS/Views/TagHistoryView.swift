import SwiftUI

/// The record behind the assistant's once-a-week "add 'Pharmacy' as a tag?"
/// popup — every theme it has ever proposed, what you answered, and when.
///
/// **Why it needs to exist.** That popup is deliberately hard to get: one ask
/// per week at most, and a refused name is never proposed again. Both of those
/// make a wrong tap expensive — a "no" you meant as "not now" is permanent, and
/// the popup is gone before you can think about it. This screen is the undo:
/// every verdict can be changed after the fact, and an entry you have finished
/// with can be folded away without being deleted from the record.
///
/// Changing an answer is not cosmetic. Accepting adds the class to the tag
/// registry; un-accepting removes it again — and, exactly like deleting a tag
/// by hand, strips it from every task that carried it. So each change asks the
/// rest of the app to re-read its tags (`api.requestRefresh()`), which is what
/// the Tasks list already listens for.
struct TagHistoryView: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var settings: AppSettings

    @State private var rows: [TagSuggestionRecord] = []
    @State private var showHidden = false
    @State private var loading = false
    @State private var error: String?
    /// Names with a write in flight — the row's controls are disabled until
    /// the Mac has answered, so a double tap cannot race itself.
    @State private var busy: Set<String> = []

    // MARK: - Derived

    private var visible: [TagSuggestionRecord] {
        showHidden ? rows : rows.filter { !$0.isHidden }
    }

    private var hiddenCount: Int { rows.filter { $0.isHidden }.count }

    // MARK: - Body

    var body: some View {
        Group {
            if rows.isEmpty, let error {
                unreachable(error)
            } else if rows.isEmpty, !loading {
                nothingYet
            } else {
                list
            }
        }
        .navigationTitle("Suggestion history")
        .navigationBarTitleDisplayMode(.inline)
        .overlay { if loading, rows.isEmpty { ProgressView() } }
        .task { await load() }
        .refreshable { await load() }
    }

    private var list: some View {
        List {
            Section {
                Toggle("Show hidden", isOn: $showHidden)
                    .tint(settings.accentColor)
            } footer: {
                Text(hiddenCount == 0
                     ? "Every tag the assistant has offered to add, newest first. Tap a status to change your answer."
                     : "\(hiddenCount) hidden. Tap a status to change your answer or fold a row away.")
                .font(.footnote)
            }

            Section {
                ForEach(visible) { row in
                    HistoryRow(row: row,
                               accent: settings.accentColor,
                               busy: busy.contains(row.name),
                               onVerdict: { accept in Task { await revise(row, accept: accept) } },
                               onHide: { hide in Task { await setHidden(row, hidden: hide) } })
                }
            } header: {
                Text(visible.isEmpty ? "" : "\(visible.count) suggestion\(visible.count == 1 ? "" : "s")")
            } footer: {
                if visible.isEmpty {
                    Text("Nothing to show — every entry is hidden.")
                        .font(.footnote)
                } else if let error {
                    // The list loaded once and a later write failed: say so
                    // without throwing away what is on screen.
                    Text(error).font(.footnote).foregroundColor(.red)
                }
            }
        }
    }

    // MARK: - States the Mac isn't in

    private func unreachable(_ message: String) -> some View {
        VStack(spacing: 10) {
            Image(systemName: "wifi.exclamationmark")
                .font(.system(size: 34))
                .foregroundColor(.secondary)
            Text("Can't reach the Mac").font(.headline)
            Text(message)
                .font(.footnote)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            Text("The suggestion record lives on the Mac, so there is nothing to show offline.")
                .font(.footnote)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            Button("Try again") { Task { await load() } }
                .buttonStyle(.bordered)
                .tint(settings.accentColor)
        }
        .padding(30)
    }

    private var nothingYet: some View {
        VStack(spacing: 10) {
            Image(systemName: "tag")
                .font(.system(size: 34))
                .foregroundColor(.secondary)
            Text("No suggestions yet").font(.headline)
            Text("When several untagged tasks turn out to share a theme no existing tag covers, the assistant offers it as a new tag — at most once a week. Whatever you answer shows up here.")
                .font(.footnote)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(30)
    }

    // MARK: - Data

    private func load() async {
        loading = true
        defer { loading = false }
        do {
            rows = try await api.tagSuggestionHistory()
            error = nil
        } catch {
            // A cancelled request (the screen was popped mid-flight) is not an
            // outage — same rule the review screen uses.
            if error is CancellationError || (error as? URLError)?.code == .cancelled
                || error.localizedDescription.lowercased().contains("cancel") { return }
            self.error = error.localizedDescription
        }
    }

    private func revise(_ row: TagSuggestionRecord, accept: Bool) async {
        busy.insert(row.name)
        defer { busy.remove(row.name) }
        do {
            try await api.reviseTagSuggestion(name: row.name, accept: accept)
            error = nil
            await load()
            // Accepting created the class; un-accepting deleted it and stripped
            // it from every task. Either way the tag palette on screen is stale.
            api.requestRefresh()
        } catch {
            self.error = "Couldn't save that: \(error.localizedDescription)"
        }
    }

    private func setHidden(_ row: TagSuggestionRecord, hidden: Bool) async {
        busy.insert(row.name)
        defer { busy.remove(row.name) }
        do {
            try await api.setTagSuggestionHidden(name: row.name, hidden: hidden)
            error = nil
            await load()
        } catch {
            self.error = "Couldn't save that: \(error.localizedDescription)"
        }
    }
}

// MARK: - Row

private struct HistoryRow: View {
    let row: TagSuggestionRecord
    let accent: Color
    let busy: Bool
    let onVerdict: (Bool) -> Void
    let onHide: (Bool) -> Void

    var body: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(row.name)
                    .font(.system(size: 16, weight: .medium))
                    .foregroundColor(row.isHidden ? .secondary : .primary)
                Text(subtitle)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
            }

            Spacer(minLength: 8)

            if busy {
                ProgressView()
            } else {
                // The status IS the control — a pill that opens the menu, so
                // changing an answer needs no swipe to discover.
                Menu {
                    if row.verdict != .accepted {
                        Button { onVerdict(true) } label: {
                            Label("Add it as a tag", systemImage: "checkmark.circle")
                        }
                    }
                    if row.verdict != .declined {
                        Button(role: row.verdict == .accepted ? .destructive : nil) {
                            onVerdict(false)
                        } label: {
                            Label(row.verdict == .accepted
                                  ? "Remove it again" : "Don't add it",
                                  systemImage: "xmark.circle")
                        }
                    }
                    Divider()
                    Button { onHide(!row.isHidden) } label: {
                        Label(row.isHidden ? "Unhide" : "Hide",
                              systemImage: row.isHidden ? "eye" : "eye.slash")
                    }
                } label: {
                    StatusPill(verdict: row.verdict, accent: accent)
                }
            }
        }
        .padding(.vertical, 2)
        .opacity(row.isHidden ? 0.55 : 1)
        // Swipe stays as the fast path for the one action people repeat.
        .swipeActions(edge: .trailing) {
            Button { onHide(!row.isHidden) } label: {
                Label(row.isHidden ? "Unhide" : "Hide",
                      systemImage: row.isHidden ? "eye" : "eye.slash")
            }
            .tint(.gray)
        }
    }

    private var subtitle: String {
        var parts: [String] = []
        if let date = row.answeredAt {
            parts.append(Self.relative.localizedString(for: date, relativeTo: Date()))
        } else if !row.ts.isEmpty {
            parts.append(row.ts)
        }
        if row.isHidden { parts.append("hidden") }
        return parts.joined(separator: " · ")
    }

    private static let relative: RelativeDateTimeFormatter = {
        let f = RelativeDateTimeFormatter()
        f.unitsStyle = .full
        return f
    }()
}

private struct StatusPill: View {
    let verdict: TagSuggestionRecord.Verdict
    let accent: Color

    var body: some View {
        HStack(spacing: 4) {
            Text(label)
                .font(.system(size: 12, weight: .semibold))
            Image(systemName: "chevron.down")
                .font(.system(size: 9, weight: .bold))
        }
        .foregroundColor(tint)
        .padding(.horizontal, 9)
        .padding(.vertical, 5)
        .background(
            RoundedRectangle(cornerRadius: Theme.radiusSM)
                .fill(tint.opacity(0.15))
        )
    }

    private var label: String {
        switch verdict {
        case .accepted: return "Accepted"
        case .declined: return "Declined"
        case .pending:  return "Pending"
        }
    }

    private var tint: Color {
        switch verdict {
        case .accepted: return .green
        case .declined: return .secondary
        case .pending:  return accent
        }
    }
}

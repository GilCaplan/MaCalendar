import SwiftUI

/// Offline-first search over everything the phone has cached — the same
/// events and todos LocalStore serves when the Mac is unreachable. No
/// network round-trip: it works on the train, and it is instant.
///
/// Presented as a sheet from the Calendar tab's toolbar. Tapping an event
/// hands it back to ContentView (which owns selectedDate/viewedDate) to
/// navigate the calendar there; tapping a task switches to the Tasks tab.
struct SearchView: View {
    @EnvironmentObject var settings: AppSettings
    @Environment(\.dismiss) private var dismiss

    /// Called with the tapped event after the sheet dismisses itself.
    let onOpenEvent: (CalendarEvent) -> Void
    /// Called with the tapped task (ContentView switches to the Tasks tab).
    let onOpenTodo: (Todo) -> Void

    @State private var query = ""
    @FocusState private var searchFocused: Bool

    private var trimmed: String {
        query.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    private var eventHits: [CalendarEvent] {
        trimmed.isEmpty ? [] : LocalStore.shared.searchEvents(trimmed)
    }
    private var todoHits: [Todo] {
        trimmed.isEmpty ? [] : LocalStore.shared.searchTodos(trimmed)
    }

    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                searchField

                List {
                    if !eventHits.isEmpty {
                        Section("Events") {
                            ForEach(eventHits) { event in
                                Button {
                                    dismiss()
                                    onOpenEvent(event)
                                } label: {
                                    EventResultRow(event: event)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                    if !todoHits.isEmpty {
                        Section("Tasks") {
                            ForEach(todoHits) { todo in
                                Button {
                                    dismiss()
                                    onOpenTodo(todo)
                                } label: {
                                    TodoResultRow(todo: todo)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                    if !trimmed.isEmpty && eventHits.isEmpty && todoHits.isEmpty {
                        Text("Nothing on this phone matches “\(trimmed)”.")
                            .foregroundColor(.secondary)
                    }
                }
                .listStyle(.insetGrouped)
            }
            .navigationTitle("Search")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    private var searchField: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(.secondary)
                TextField("Search events and tasks", text: $query)
                    .focused($searchFocused)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                if !query.isEmpty {
                    Button { query = "" } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(10)
            .background(
                RoundedRectangle(cornerRadius: Theme.radiusMD)
                    .fill(Color(.secondarySystemBackground))
            )
            Text("Searches what's cached on this phone — works away from your Mac.")
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .onAppear { searchFocused = true }
    }
}

// MARK: - Result rows

private struct EventResultRow: View {
    @EnvironmentObject var settings: AppSettings
    let event: CalendarEvent

    private var dayLabel: String {
        guard let d = DateFormatter.isoDay.date(from: event.date) else { return event.date }
        let out = DateFormatter()
        out.dateFormat = "EEE, MMM d, yyyy"
        return out.string(from: d)
    }

    var body: some View {
        HStack(spacing: 10) {
            RoundedRectangle(cornerRadius: 2)
                .fill(Color(hex: event.color) ?? settings.accentColor)
                .frame(width: 4, height: 36)
            VStack(alignment: .leading, spacing: 2) {
                Text(event.title)
                    .lineLimit(1)
                Text(event.displayTime.isEmpty ? dayLabel : "\(dayLabel) · \(event.displayTime)")
                    .font(.caption)
                    .foregroundColor(.secondary)
                if !event.location.isEmpty {
                    Label(event.location, systemImage: "mappin.and.ellipse")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .contentShape(Rectangle())
    }
}

private struct TodoResultRow: View {
    let todo: Todo

    private var subtitle: String {
        var parts = [todo.list.capitalized]
        if !todo.dueDate.isEmpty { parts.append("due \(todo.dueDate)") }
        if !todo.tags.isEmpty { parts.append(todo.tags.joined(separator: ", ")) }
        return parts.joined(separator: " · ")
    }

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: todo.isDone ? "checkmark.circle.fill" : "circle")
                .foregroundColor(todo.isDone ? .green : .secondary)
            VStack(alignment: .leading, spacing: 2) {
                Text(todo.title)
                    .lineLimit(1)
                    .strikethrough(todo.isDone)
                    .foregroundColor(todo.isDone ? .secondary : .primary)
                Text(subtitle)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .contentShape(Rectangle())
    }
}

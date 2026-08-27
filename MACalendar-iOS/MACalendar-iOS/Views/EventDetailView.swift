import SwiftUI

struct EventDetailView: View {
    @EnvironmentObject var api: APIClient
    var event: CalendarEvent
    var isNew: Bool = false
    var onDismiss: (() -> Void)?

    @State private var title: String
    @State private var date: String
    @State private var startTime: String
    @State private var endTime: String
    @State private var location: String
    @State private var attendees: String
    @State private var saving = false
    @State private var confirmDelete = false
    @State private var errorMessage: String?
    @Environment(\.dismiss) var dismiss

    /// ICS-subscribed events are always read-only (no write endpoint behind
    /// a webcal link). Outlook events read-only-when-two-way-off aren't
    /// knowable client-side without an extra fetch, but the server enforces
    /// that too (PATCH/DELETE /events/<id> return 403) — save()/deleteEvent()
    /// surface that failure instead of silently swallowing it.
    private var isReadOnly: Bool { !isNew && event.isReadOnly }

    init(event: CalendarEvent, isNew: Bool = false, onDismiss: (() -> Void)? = nil) {
        self.event = event
        self.isNew = isNew
        self.onDismiss = onDismiss
        _title     = State(initialValue: event.title)
        _date      = State(initialValue: event.date)
        _startTime = State(initialValue: event.startTime)
        _endTime   = State(initialValue: event.endTime)
        _location  = State(initialValue: event.location)
        _attendees = State(initialValue: event.attendees)
    }

    // MARK: - Computed helpers

    /// Returns e.g. "Monday, Apr 14, 2026" or nil if the date string is invalid.
    private var parsedDayLabel: String? {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        guard let d = fmt.date(from: date) else { return nil }
        let out = DateFormatter()
        out.dateFormat = "EEEE, MMM d, yyyy"
        return out.string(from: d)
    }

    // MARK: - Body

    var body: some View {
        NavigationStack {
            Form {
                if isReadOnly {
                    Section {
                        Label("Synced from a subscribed calendar — read-only.", systemImage: "link")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
                Section(header: Text("Event")) {
                    TextField("Title", text: $title)
                        .onSubmit { if !saving && !title.isEmpty { save() } }

                    VStack(alignment: .leading, spacing: 2) {
                        TextField("Date (YYYY-MM-DD)", text: $date)
                            .keyboardType(.numbersAndPunctuation)
                            .onSubmit { if !saving && !title.isEmpty { save() } }
                        if let label = parsedDayLabel {
                            Text(label)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }

                    HStack {
                        TextField("Start (HH:MM)", text: $startTime)
                            .keyboardType(.numbersAndPunctuation)
                            .onChange(of: startTime) { newVal in
                                autoUpdateEndTime(from: newVal)
                            }
                            .onSubmit { if !saving && !title.isEmpty { save() } }
                        Text("–")
                        TextField("End (HH:MM)", text: $endTime)
                            .keyboardType(.numbersAndPunctuation)
                            .onSubmit { if !saving && !title.isEmpty { save() } }
                    }
                }
                Section(header: Text("Details")) {
                    TextField("Location", text: $location)
                        .onSubmit { if !saving && !title.isEmpty { save() } }
                    TextField("Attendees", text: $attendees)
                        .onSubmit { if !saving && !title.isEmpty { save() } }
                }
                GuestsSection(attendees: $attendees, title: title, date: date, startTime: startTime, endTime: endTime, location: location)
                if !isNew && !isReadOnly {
                    Section {
                        Button(role: .destructive) { confirmDelete = true } label: {
                            Label("Delete Event", systemImage: "trash")
                        }
                    }
                }
            }
            .disabled(isReadOnly)
            .navigationTitle(isNew ? "New Event" : "Edit Event")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                if !isReadOnly {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Save") { save() }
                            .disabled(saving || title.isEmpty)
                            .keyboardShortcut(.defaultAction)
                    }
                }
            }
            .confirmationDialog("Delete this event?", isPresented: $confirmDelete, titleVisibility: .visible) {
                Button("Delete", role: .destructive) { deleteEvent() }
                Button("Cancel", role: .cancel) {}
            }
            .alert("Couldn't Save", isPresented: .constant(errorMessage != nil), presenting: errorMessage) { _ in
                Button("OK") { errorMessage = nil }
            } message: { message in
                Text(message)
            }
        }
    }

    // MARK: - Auto end-time

    /// When the user changes the start time, push the end time to exactly 1 hour later.
    private func autoUpdateEndTime(from start: String) {
        let parts = start.split(separator: ":").compactMap { Int($0) }
        guard parts.count == 2 else { return }
        let totalMins = parts[0] * 60 + parts[1] + 60
        let h = (totalMins / 60) % 24
        let m = totalMins % 60
        endTime = String(format: "%02d:%02d", h, m)
    }

    // MARK: - Actions

    private func save() {
        guard !saving else { return }
        saving = true
        Task {
            do {
                if isNew {
                    _ = try await api.createEvent([
                        "title": title, "date": date,
                        "start_time": startTime, "end_time": endTime,
                        "location": location, "attendees": attendees
                    ])
                } else {
                    try await api.updateEvent(id: event.id, fields: [
                        "title": title, "date": date,
                        "start_time": startTime, "end_time": endTime,
                        "location": location, "attendees": attendees
                    ])
                }
                saving = false
                dismiss()
                onDismiss?()
            } catch {
                // Most failures (offline, bad URL) are already handled inside
                // APIClient by queuing for later — only a real rejection from
                // the server (e.g. 403 on a read-only synced event) reaches
                // here, so surface it instead of silently discarding it.
                saving = false
                errorMessage = "This event couldn't be saved — it may be read-only (synced from another calendar)."
            }
        }
    }

    private func deleteEvent() {
        Task {
            do {
                try await api.deleteEvent(id: event.id)
                dismiss()
                onDismiss?()
            } catch {
                errorMessage = "This event couldn't be deleted — it may be read-only (synced from another calendar)."
                onDismiss?()  // local optimistic removal already happened; refresh to restore it
            }
        }
    }
}

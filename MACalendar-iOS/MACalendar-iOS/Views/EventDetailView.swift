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
    @Environment(\.dismiss) var dismiss

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
                Section(header: Text("Event")) {
                    TextField("Title", text: $title)

                    VStack(alignment: .leading, spacing: 2) {
                        TextField("Date (YYYY-MM-DD)", text: $date)
                            .keyboardType(.numbersAndPunctuation)
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
                        Text("–")
                        TextField("End (HH:MM)", text: $endTime)
                            .keyboardType(.numbersAndPunctuation)
                    }
                }
                Section(header: Text("Details")) {
                    TextField("Location", text: $location)
                    TextField("Attendees", text: $attendees)
                }
                if !isNew {
                    Section {
                        Button(role: .destructive) { confirmDelete = true } label: {
                            Label("Delete Event", systemImage: "trash")
                        }
                    }
                }
            }
            .navigationTitle(isNew ? "New Event" : "Edit Event")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }
                        .disabled(saving || title.isEmpty)
                }
            }
            .confirmationDialog("Delete this event?", isPresented: $confirmDelete, titleVisibility: .visible) {
                Button("Delete", role: .destructive) { deleteEvent() }
                Button("Cancel", role: .cancel) {}
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
        saving = true
        Task {
            if isNew {
                _ = try? await api.createEvent([
                    "title": title, "date": date,
                    "start_time": startTime, "end_time": endTime,
                    "location": location, "attendees": attendees
                ])
            } else {
                try? await api.updateEvent(id: event.id, fields: [
                    "title": title, "date": date,
                    "start_time": startTime, "end_time": endTime,
                    "location": location, "attendees": attendees
                ])
            }
            saving = false
            dismiss()
            onDismiss?()
        }
    }

    private func deleteEvent() {
        Task {
            try? await api.deleteEvent(id: event.id)
            dismiss()
            onDismiss?()
        }
    }
}

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

    var body: some View {
        NavigationView {
            Form {
                Section(header: Text("Event")) {
                    TextField("Title", text: $title)
                    TextField("Date (YYYY-MM-DD)", text: $date)
                        .keyboardType(.numbersAndPunctuation)
                    HStack {
                        TextField("Start (HH:MM)", text: $startTime)
                            .keyboardType(.numbersAndPunctuation)
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

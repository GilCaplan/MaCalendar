import SwiftUI
import UIKit

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
    @State private var notes: String
    /// Reminder override: -1 = Inherit (no stored override), 0 = None,
    /// N = minutes before start. Mirrors reminder_minutes, where "inherit"
    /// is the column being NULL.
    @State private var reminderChoice: Int
    @State private var saving = false
    @State private var confirmDelete = false
    @State private var errorMessage: String?
    @State private var sharing = false
    @State private var shareFile: ShareFile?
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
        _notes     = State(initialValue: event.description)
        _reminderChoice = State(initialValue: event.reminderMinutes ?? -1)
    }

    // MARK: - Computed helpers

    /// Human reading of the server's notify_suppressed_reason — the effective
    /// state when a lead time exists but no reminder will fire. The server is
    /// the policy brain; this only translates its verdict.
    private var suppressionNote: String? {
        guard let r = event.notifySuppressedReason, !r.isEmpty else { return nil }
        if r == "shabbat" { return "Held for Shabbat" }
        if r.hasPrefix("yom_tov:") {
            let name = String(r.dropFirst("yom_tov:".count))
            return name.isEmpty ? "Held for yom tov" : "Held for \(name)"
        }
        if r == "clamped_past_start" {
            return "Skipped — the reminder would have landed during Shabbat or chag"
        }
        return "Reminder held (\(r))"
    }

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
                Section {
                    Picker("Reminder", selection: $reminderChoice) {
                        Text("Inherit").tag(-1)
                        Text("None").tag(0)
                        ForEach([5, 10, 15, 30, 60], id: \.self) { m in
                            Text("\(m) min before").tag(m)
                        }
                    }
                    .onChange(of: reminderChoice) { choice in
                        // First actual use of reminders on this device — the
                        // moment to ask, not app launch.
                        if choice != -1 { NotificationPermission.requestIfNeeded() }
                    }
                } footer: {
                    if let note = suppressionNote {
                        Label(note, systemImage: "moon.stars")
                    } else if reminderChoice == -1 {
                        Text("Inherit uses the category's lead time, or the default from Settings › Reminders.")
                    }
                }
                // The event body. This is where a planned session keeps the
                // part that matters — "2 × 10 min @ 4:40 — 2 min jog between" —
                // so it needs room to wrap, not a one-line TextField.
                Section(header: Text("Notes")) {
                    TextField("Notes", text: $notes, axis: .vertical)
                        .lineLimit(3...12)
                }
                GuestsSection(attendees: $attendees, title: title, date: date, startTime: startTime, endTime: endTime, location: location)
                if !isNew {
                    Section {
                        Button {
                            shareICS()
                        } label: {
                            HStack {
                                Label("Share Event (.ics)", systemImage: "square.and.arrow.up")
                                if sharing {
                                    Spacer()
                                    ProgressView()
                                }
                            }
                        }
                        // Offline temp rows (negative id) don't exist on the
                        // Mac yet, so there is nothing to fetch.
                        .disabled(sharing || event.id <= 0)
                    } footer: {
                        if event.id <= 0 {
                            Text("Sharing becomes available once this event has synced to your Mac.")
                        }
                    }
                }
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
            .sheet(item: $shareFile) { file in
                ShareSheet(items: [file.url])
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
                var fields: [String: Any] = [
                    "title": title, "date": date,
                    "start_time": startTime, "end_time": endTime,
                    "location": location, "attendees": attendees,
                    "description": notes
                ]
                if isNew {
                    // Only send an override that exists — a fresh event with
                    // "Inherit" simply has no reminder_minutes.
                    if reminderChoice != -1 { fields["reminder_minutes"] = reminderChoice }
                    _ = try await api.createEvent(fields)
                } else {
                    // NSNull → JSON null → the Mac clears the override back
                    // to Inherit. The offline patchEvent path reads the same
                    // convention.
                    fields["reminder_minutes"] = reminderChoice == -1 ? NSNull() : reminderChoice
                    try await api.updateEvent(id: event.id, fields: fields)
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

    // MARK: - Share as .ics

    /// A filesystem-safe slug of the title for the shared file's name.
    private var titleSlug: String {
        let safe = title
            .replacingOccurrences(of: "[^A-Za-z0-9 _-]", with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespaces)
            .replacingOccurrences(of: " ", with: "-")
        return safe.isEmpty ? "event" : safe
    }

    /// Download the Mac's rendering of this event (GET /events/<id>.ics),
    /// park it in a temp file named after the title, and present the share
    /// sheet for that file. The Mac is the source of truth for the .ics —
    /// recurrence, categories and any Mac-side edits come out right without
    /// the phone re-deriving them from possibly-unsaved form fields.
    private func shareICS() {
        guard !sharing, event.id > 0 else { return }
        sharing = true
        Task {
            do {
                let data = try await api.fetchICS(eventId: event.id)
                let url = FileManager.default.temporaryDirectory
                    .appendingPathComponent("\(titleSlug).ics")
                try data.write(to: url)
                sharing = false
                shareFile = ShareFile(url: url)
            } catch {
                sharing = false
                errorMessage = "Couldn't fetch this event from your Mac — sharing needs the Mac reachable."
            }
        }
    }
}

/// Identifiable wrapper so `.sheet(item:)` can present the share sheet the
/// moment the .ics file lands on disk. ShareLink wants its item up front,
/// which an async fetch can't provide — GuestsSection gets away with
/// ShareLink because it composes its .ics synchronously on-device.
private struct ShareFile: Identifiable {
    let url: URL
    var id: String { url.path }
}

/// The system share sheet (runs in-process; nothing here talks to a service).
private struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}

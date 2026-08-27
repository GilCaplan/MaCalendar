import SwiftUI
import Contacts
import ContactsUI
import UIKit

/// Guests on an event. Names live in the event's `attendees` field (comma
/// separated, synced with the Mac and used by the voice assistant). Phone
/// numbers / emails are looked up in the phone's own Contacts on demand and
/// never stored or uploaded. Invites go out through the apps already on the
/// phone (Messages, WhatsApp, Mail, or the share sheet with an .ics file) —
/// nothing here talks to any online service.
struct GuestsSection: View {
    @Binding var attendees: String
    var title: String
    var date: String
    var startTime: String
    var endTime: String
    var location: String

    @State private var showPicker = false
    @State private var newGuest = ""

    private var guests: [String] {
        attendees.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }

    var body: some View {
        Section {
            ForEach(guests, id: \.self) { name in
                GuestRow(name: name, invite: inviteText, ics: icsData) { remove(name) }
            }
            HStack {
                TextField("Add guest by name", text: $newGuest)
                    .onSubmit(addTyped)
                Button("Add", action: addTyped).disabled(newGuest.trimmingCharacters(in: .whitespaces).isEmpty)
                Button { showPicker = true } label: { Image(systemName: "person.crop.circle.badge.plus") }
                    .buttonStyle(.borderless)
            }
            if !guests.isEmpty {
                ShareLink(item: icsFileURL(), subject: Text(title), message: Text(inviteText)) {
                    Label("Share invite (.ics) to all", systemImage: "square.and.arrow.up")
                }
            }
        } header: { Text("Guests") } footer: {
            Text("Say “meeting with Noa” and the assistant adds Noa here. Numbers and emails come from your Contacts when you tap Message, WhatsApp or Mail — they are not stored.")
        }
        .sheet(isPresented: $showPicker) {
            ContactPicker { contact in
                let name = CNContactFormatter.string(from: contact, style: .fullName) ?? contact.givenName
                add(name)
            }
        }
    }

    private func addTyped() { add(newGuest); newGuest = "" }
    private func add(_ name: String) {
        let n = name.trimmingCharacters(in: .whitespaces)
        guard !n.isEmpty, !guests.contains(where: { $0.caseInsensitiveCompare(n) == .orderedSame }) else { return }
        attendees = (guests + [n]).joined(separator: ", ")
    }
    private func remove(_ name: String) { attendees = guests.filter { $0 != name }.joined(separator: ", ") }

    // MARK: invite content

    private var prettyWhen: String {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"
        let o = DateFormatter(); o.dateFormat = "EEEE d MMM"
        let day = f.date(from: date).map { o.string(from: $0) } ?? date
        return "\(day), \(startTime)–\(endTime)"
    }
    private var inviteText: String {
        var t = "You're invited: \(title)\n\(prettyWhen)"
        if !location.isEmpty { t += "\nWhere: \(location)" }
        return t
    }
    private var icsData: Data {
        func stamp(_ hhmm: String) -> String {
            "\(date.replacingOccurrences(of: "-", with: ""))T\(hhmm.replacingOccurrences(of: ":", with: ""))00"
        }
        let uid = "\(date)-\(startTime)-\(title.hashValue)@macalendar"
        let body = """
        BEGIN:VCALENDAR\r
        VERSION:2.0\r
        PRODID:-//MACalendar//EN\r
        BEGIN:VEVENT\r
        UID:\(uid)\r
        DTSTART:\(stamp(startTime))\r
        DTEND:\(stamp(endTime))\r
        SUMMARY:\(title)\r
        LOCATION:\(location)\r
        END:VEVENT\r
        END:VCALENDAR\r

        """
        return Data(body.utf8)
    }
    private func icsFileURL() -> URL {
        let safe = title.replacingOccurrences(of: "[^A-Za-z0-9 _-]", with: "", options: .regularExpression)
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("\(safe.isEmpty ? "event" : safe).ics")
        try? icsData.write(to: url)
        return url
    }
}

private struct GuestRow: View {
    let name: String
    let invite: String
    let ics: Data
    let onRemove: () -> Void
    @State private var phone: String?
    @State private var email: String?
    @State private var looked = false

    var body: some View {
        HStack(spacing: 10) {
            Text(name)
            Spacer()
            if let phone {
                Button { open("sms:\(phone)&body=\(enc(invite))") } label: { Image(systemName: "message") }
                Button { open("https://wa.me/\(digits(phone))?text=\(enc(invite))") } label: { Image(systemName: "phone.bubble") }
            }
            if let email {
                Button { open("mailto:\(email)?subject=\(enc("Invitation: " + firstLine))&body=\(enc(invite))") } label: { Image(systemName: "envelope") }
            }
            if looked && phone == nil && email == nil {
                Text("not in Contacts").font(.caption2).foregroundColor(.secondary)
            }
            Button(role: .destructive, action: onRemove) { Image(systemName: "xmark.circle") }
        }
        .buttonStyle(.borderless)
        .task(id: name) { await lookup() }
    }

    private var firstLine: String { invite.split(separator: "\n").first.map(String.init)?.replacingOccurrences(of: "You're invited: ", with: "") ?? "" }
    private func enc(_ s: String) -> String { s.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed.subtracting(CharacterSet(charactersIn: "&+"))) ?? s }
    private func digits(_ s: String) -> String {
        var d = s.filter(\.isNumber)
        if d.hasPrefix("0") { d = "972" + d.dropFirst() }      // local Israeli number → international
        return d
    }
    private func open(_ url: String) { if let u = URL(string: url) { UIApplication.shared.open(u) } }

    /// Local Contacts lookup by name; asks for permission the first time.
    private func lookup() async {
        defer { looked = true }
        let store = CNContactStore()
        let status = CNContactStore.authorizationStatus(for: .contacts)
        if status == .notDetermined { _ = try? await store.requestAccess(for: .contacts) }
        guard CNContactStore.authorizationStatus(for: .contacts) == .authorized else { return }
        let keys = [CNContactPhoneNumbersKey, CNContactEmailAddressesKey] as [CNKeyDescriptor]
        let pred = CNContact.predicateForContacts(matchingName: name)
        guard let hits = try? store.unifiedContacts(matching: pred, keysToFetch: keys), let c = hits.first else { return }
        phone = c.phoneNumbers.first?.value.stringValue
        email = c.emailAddresses.first.map { String($0.value) }
    }
}

/// System contact picker (runs in-process, no network).
private struct ContactPicker: UIViewControllerRepresentable {
    var onPick: (CNContact) -> Void
    func makeUIViewController(context: Context) -> CNContactPickerViewController {
        let vc = CNContactPickerViewController(); vc.delegate = context.coordinator; return vc
    }
    func updateUIViewController(_ vc: CNContactPickerViewController, context: Context) {}
    func makeCoordinator() -> Coord { Coord(onPick: onPick) }
    final class Coord: NSObject, CNContactPickerDelegate {
        let onPick: (CNContact) -> Void
        init(onPick: @escaping (CNContact) -> Void) { self.onPick = onPick }
        func contactPicker(_ picker: CNContactPickerViewController, didSelect contact: CNContact) { onPick(contact) }
    }
}

import Foundation

// A write operation that couldn't reach the server and needs to be replayed.
struct PendingChange: Codable, Identifiable {
    let id: UUID
    let method: String   // "POST" | "PATCH" | "DELETE"
    let path: String     // e.g. "/events", "/todos/5"
    let bodyJSON: Data?  // JSON-serialised body dict
    let createdAt: Date

    init(method: String, path: String, body: [String: Any]?) {
        self.id        = UUID()
        self.method    = method
        self.path      = path
        self.bodyJSON  = body.flatMap { try? JSONSerialization.data(withJSONObject: $0) }
        self.createdAt = Date()
    }

    private init(id: UUID, method: String, path: String, bodyJSON: Data?, createdAt: Date) {
        self.id = id; self.method = method; self.path = path
        self.bodyJSON = bodyJSON; self.createdAt = createdAt
    }

    /// Same queued change, pointed at a different path (used when a temporary
    /// offline id is replaced by the real one the Mac assigned).
    func replacingPath(_ newPath: String) -> PendingChange {
        PendingChange(id: id, method: method, path: newPath,
                      bodyJSON: bodyJSON, createdAt: createdAt)
    }
}

/// A voice command recorded while the Mac was unreachable.
///
/// The Mac does all the thinking, so a command spoken offline cannot be
/// understood on the phone — but the audio is kept and replayed the moment the
/// Mac is back, and the result is reported. Without this the recording was
/// simply thrown away and the user was told it failed.
struct PendingVoiceCommand: Codable, Identifiable {
    enum Status: String, Codable { case queued, running, done, failed }

    let id: UUID
    let recordedAt: Date
    var status: Status
    var result: String        // what the Mac replied, once it has run
    var audioFile: String     // file name inside the store's directory

    init(audioFile: String) {
        self.id = UUID()
        self.recordedAt = Date()
        self.status = .queued
        self.result = ""
        self.audioFile = audioFile
    }
}

/// Persists events, todos, and queued writes to disk.
/// Temp IDs are negative integers; they're replaced by real server IDs after sync.
@MainActor
class LocalStore: ObservableObject {
    static let shared = LocalStore()

    @Published private(set) var pendingCount = 0
    /// Voice commands waiting for the Mac to come back, newest last.
    @Published private(set) var pendingVoice: [PendingVoiceCommand] = []

    private var events:  [CalendarEvent] = []
    private var todos:   [Todo]          = []
    private var tags:    [TodoTag]       = []
    private var pending: [PendingChange] = []
    private var nextTemp = -1

    private let dir = FileManager.default
        .urls(for: .documentDirectory, in: .userDomainMask)[0]

    private init() { load() }

    // MARK: - Persistence

    private func url(_ name: String) -> URL { dir.appendingPathComponent(name) }

    private func load() {
        let d = JSONDecoder()
        events  = (try? d.decode([CalendarEvent].self, from: Data(contentsOf: url("mc_events.json"))))  ?? []
        todos   = (try? d.decode([Todo].self,          from: Data(contentsOf: url("mc_todos.json"))))   ?? []
        tags    = (try? d.decode([TodoTag].self,       from: Data(contentsOf: url("mc_tags.json"))))    ?? []
        pending = (try? d.decode([PendingChange].self, from: Data(contentsOf: url("mc_pending.json")))) ?? []
        pendingCount = pending.count
        // Prevent temp-ID collisions after a restart: start below the lowest existing negative ID.
        let negIDs = events.map { $0.id }.filter { $0 < 0 } + todos.map { $0.id }.filter { $0 < 0 }
        nextTemp = (negIDs.min().map { $0 - 1 }) ?? -1
        loadVoice()
    }

    func persist() {
        let e = JSONEncoder()
        try? e.encode(events).write(to:  url("mc_events.json"))
        try? e.encode(todos).write(to:   url("mc_todos.json"))
        try? e.encode(tags).write(to:    url("mc_tags.json"))
        try? e.encode(pending).write(to: url("mc_pending.json"))
        pendingCount = pending.count
    }

    // MARK: - Events

    func cacheEvents(_ fresh: [CalendarEvent]) {
        // Keep items created offline that the Mac hasn't got yet — but drop any
        // whose twin is already in the fresh data, or they show up twice for
        // ever: once as the local placeholder, once as the Mac's copy.
        let arrived = Set(fresh.map { "\($0.title)|\($0.date)|\($0.startTime)" })
        let local = events.filter {
            $0.id < 0 && !arrived.contains("\($0.title)|\($0.date)|\($0.startTime)")
        }
        events = local + fresh
        persist()
    }

    func eventsForDate(_ str: String) -> [CalendarEvent] {
        events.filter { $0.date == str }
    }

    func eventsForMonth(_ year: Int, _ month: Int) -> [CalendarEvent] {
        let pfx = String(format: "%04d-%02d", year, month)
        return events.filter { $0.date.hasPrefix(pfx) }
    }

    func eventsForWeek(startStr: String) -> [CalendarEvent] {
        let fmt = DateFormatter.isoDay
        guard let start = fmt.date(from: startStr) else { return [] }
        let end = Calendar.current.date(byAdding: .day, value: 7, to: start)!
        return events.filter {
            guard let d = fmt.date(from: $0.date) else { return false }
            return d >= start && d < end
        }
    }

    func insertEvent(_ fields: [String: Any]) -> CalendarEvent {
        let e = CalendarEvent(
            id: nextTemp,
            title:         fields["title"]          as? String ?? "New Event",
            date:          fields["date"]           as? String ?? DateFormatter.isoDay.string(from: Date()),
            startTime:     fields["start_time"]     as? String ?? "",
            endTime:       fields["end_time"]       as? String ?? "",
            attendees:     fields["attendees"]      as? String ?? "",
            location:      fields["location"]       as? String ?? "",
            description:   fields["description"]    as? String ?? "",
            color:         fields["color"]          as? String ?? "",
            recurrence:    fields["recurrence"]     as? String ?? "",
            recurrenceEnd: fields["recurrence_end"] as? String ?? ""
        )
        nextTemp -= 1
        events.append(e)
        persist()
        return e
    }

    func event(_ id: Int) -> CalendarEvent? { events.first { $0.id == id } }
    func todo(_ id: Int) -> Todo? { todos.first { $0.id == id } }

    func patchEvent(_ id: Int, fields: [String: Any]) {
        guard let i = events.firstIndex(where: { $0.id == id }) else { return }
        if let v = fields["title"]      as? String { events[i].title     = v }
        if let v = fields["date"]       as? String { events[i].date      = v }
        if let v = fields["start_time"] as? String { events[i].startTime = v }
        if let v = fields["end_time"]   as? String { events[i].endTime   = v }
        if let v = fields["location"]   as? String { events[i].location  = v }
        if let v = fields["attendees"]  as? String { events[i].attendees = v }
        persist()
    }

    func removeEvent(_ id: Int) { events.removeAll { $0.id == id }; persist() }

    // MARK: - Todos

    func cacheTodos(_ fresh: [Todo]) {
        let arrived = Set(fresh.map { "\($0.title)|\($0.list)" })
        let local = todos.filter { $0.id < 0 && !arrived.contains("\($0.title)|\($0.list)") }
        todos = local + fresh
        persist()
    }

    func allTodos(list: String?, includeCompleted: Bool) -> [Todo] {
        todos.filter {
            (list == nil || $0.list == list) && (includeCompleted || $0.completed == 0)
        }
    }

    func insertTodo(title: String, list: String, tags: [String] = []) -> Todo {
        let t = Todo(id: nextTemp, title: title, list: list,
                     completed: 0, priority: "none", dueDate: "", tags: tags)
        nextTemp -= 1
        todos.append(t)
        persist()
        return t
    }

    @discardableResult
    func toggleTodo(_ id: Int) -> Bool {
        guard let i = todos.firstIndex(where: { $0.id == id }) else { return false }
        todos[i].completed = todos[i].completed == 0 ? 1 : 0
        persist()
        return todos[i].completed != 0
    }

    func patchTodo(_ id: Int, fields: [String: Any]) {
        guard let i = todos.firstIndex(where: { $0.id == id }) else { return }
        if let v = fields["title"]     as? String { todos[i].title    = v }
        if let v = fields["list_name"] as? String { todos[i].list     = v }
        if let v = fields["priority"]  as? String { todos[i].priority = v }
        if let v = fields["due_date"]  as? String { todos[i].dueDate  = v }
        if let v = fields["tags"]      as? [String] { todos[i].tags   = v }
        persist()
    }

    func removeTodo(_ id: Int) { todos.removeAll { $0.id == id }; persist() }

    // MARK: - Tags (palette cache)

    func cacheTags(_ fresh: [TodoTag]) {
        tags = fresh
        persist()
    }

    func allTags() -> [TodoTag] {
        if tags.isEmpty {
            // Never-synced device: show the server's built-in set so tag mode is usable offline.
            return ["Coursework", "Groceries", "Errands", "Work", "Personal"].map { TodoTag(name: $0, builtin: 1) }
        }
        return tags
    }

    func insertTag(_ tag: TodoTag) {
        var current = allTags()
        guard !current.contains(where: { $0.name.caseInsensitiveCompare(tag.name) == .orderedSame }) else { return }
        current.append(tag)
        tags = current
        persist()
    }

    func removeTag(_ name: String) {
        tags = allTags().filter { $0.name.caseInsensitiveCompare(name) != .orderedSame }
        for i in todos.indices {
            todos[i].tags.removeAll { $0.caseInsensitiveCompare(name) == .orderedSame }
        }
        persist()
    }

    // MARK: - Pending queue

    func enqueue(method: String, path: String, body: [String: Any]? = nil) {
        pending.append(PendingChange(method: method, path: path, body: body))
        persist()
    }

    // MARK: - Voice commands queued while offline

    private var voiceURL: URL { url("mc_pending_voice.json") }

    private func loadVoice() {
        guard let data = try? Data(contentsOf: voiceURL),
              let rows = try? JSONDecoder().decode([PendingVoiceCommand].self, from: data)
        else { return }
        pendingVoice = rows
    }

    private func persistVoice() {
        if let data = try? JSONEncoder().encode(pendingVoice) {
            try? data.write(to: voiceURL)
        }
    }

    /// Park a recording until the Mac is reachable. Returns the queued command.
    @discardableResult
    func enqueueVoice(_ audio: Data) -> PendingVoiceCommand {
        let name = "voice-\(UUID().uuidString).wav"
        try? audio.write(to: url(name))
        let cmd = PendingVoiceCommand(audioFile: name)
        pendingVoice.append(cmd)
        persistVoice()
        return cmd
    }

    func voiceAudio(_ cmd: PendingVoiceCommand) -> Data? {
        try? Data(contentsOf: url(cmd.audioFile))
    }

    func updateVoice(_ id: UUID, status: PendingVoiceCommand.Status, result: String = "") {
        guard let i = pendingVoice.firstIndex(where: { $0.id == id }) else { return }
        pendingVoice[i].status = status
        if !result.isEmpty { pendingVoice[i].result = result }
        persistVoice()
    }

    func removeVoice(_ id: UUID) {
        if let cmd = pendingVoice.first(where: { $0.id == id }) {
            try? FileManager.default.removeItem(at: url(cmd.audioFile))
        }
        pendingVoice.removeAll { $0.id == id }
        persistVoice()
    }

    /// Drop finished entries once they have been seen.
    func clearFinishedVoice() {
        for cmd in pendingVoice where cmd.status == .done || cmd.status == .failed {
            try? FileManager.default.removeItem(at: url(cmd.audioFile))
        }
        pendingVoice.removeAll { $0.status == .done || $0.status == .failed }
        persistVoice()
    }

    func allPending() -> [PendingChange] { pending }

    func removePending(_ id: UUID) {
        pending.removeAll { $0.id == id }
        persist()
    }

    /// Rewrite queued requests that still refer to an item by the temporary
    /// negative id it was given while offline.
    ///
    /// Anything created offline gets a placeholder id (`nextTemp`, counting
    /// down from -1). If you then tick it off or edit it, that action was
    /// queued against the placeholder — e.g. `PATCH /todos/-1/toggle`. Once the
    /// create is replayed the Mac assigns a real id, and the queued action
    /// 404s forever: the change is silently lost AND (since the sync loop stops
    /// at the first failure) it blocks everything queued behind it.
    func remapTemporaryID(_ tempID: Int, to realID: Int) {
        guard tempID < 0 else { return }
        for (i, change) in pending.enumerated() {
            guard change.path.contains("/\(tempID)") else { continue }
            pending[i] = change.replacingPath(
                change.path.replacingOccurrences(of: "/\(tempID)", with: "/\(realID)"))
        }
        for (i, t) in todos.enumerated() where t.id == tempID { todos[i].id = realID }
        for (i, e) in events.enumerated() where e.id == tempID { events[i].id = realID }
        persist()
    }
}

extension DateFormatter {
    static let isoDay: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()
}

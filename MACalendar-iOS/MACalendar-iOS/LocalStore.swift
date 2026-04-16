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
}

/// Persists events, todos, and queued writes to disk.
/// Temp IDs are negative integers; they're replaced by real server IDs after sync.
@MainActor
class LocalStore: ObservableObject {
    static let shared = LocalStore()

    @Published private(set) var pendingCount = 0

    private var events:  [CalendarEvent] = []
    private var todos:   [Todo]          = []
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
        pending = (try? d.decode([PendingChange].self, from: Data(contentsOf: url("mc_pending.json")))) ?? []
        pendingCount = pending.count
        // Prevent temp-ID collisions after a restart: start below the lowest existing negative ID.
        let negIDs = events.map { $0.id }.filter { $0 < 0 } + todos.map { $0.id }.filter { $0 < 0 }
        nextTemp = (negIDs.min().map { $0 - 1 }) ?? -1
    }

    func persist() {
        let e = JSONEncoder()
        try? e.encode(events).write(to:  url("mc_events.json"))
        try? e.encode(todos).write(to:   url("mc_todos.json"))
        try? e.encode(pending).write(to: url("mc_pending.json"))
        pendingCount = pending.count
    }

    // MARK: - Events

    func cacheEvents(_ fresh: [CalendarEvent]) {
        let local = events.filter { $0.id < 0 }   // keep unsynced local items
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
        let local = todos.filter { $0.id < 0 }
        todos = local + fresh
        persist()
    }

    func allTodos(list: String?, includeCompleted: Bool) -> [Todo] {
        todos.filter {
            (list == nil || $0.list == list) && (includeCompleted || $0.completed == 0)
        }
    }

    func insertTodo(title: String, list: String) -> Todo {
        let t = Todo(id: nextTemp, title: title, list: list,
                     completed: 0, priority: "none", dueDate: "")
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
        persist()
    }

    func removeTodo(_ id: Int) { todos.removeAll { $0.id == id }; persist() }

    // MARK: - Pending queue

    func enqueue(method: String, path: String, body: [String: Any]? = nil) {
        pending.append(PendingChange(method: method, path: path, body: body))
        persist()
    }

    func allPending() -> [PendingChange] { pending }

    func removePending(_ id: UUID) {
        pending.removeAll { $0.id == id }
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

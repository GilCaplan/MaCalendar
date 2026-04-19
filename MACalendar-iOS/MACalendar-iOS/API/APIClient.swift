import Foundation

@MainActor
class APIClient: ObservableObject {
    @Published var isLoading  = false
    @Published var lastError: String?
    @Published var isOnline   = true

    private let settings: AppSettings

    init(settings: AppSettings) {
        self.settings = settings
    }

    // MARK: - Base

    private var base: String {
        var url = settings.serverURL
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: .init(charactersIn: "/"))
        if url.hasPrefix("https://") { url = "http://" + url.dropFirst(8) }
        return url
    }

    private func request(_ path: String, method: String = "GET",
                         body: [String: Any]? = nil) async throws -> Data {
        let isPlaceholder = base.contains("x.x.x") || base.contains("100.x")
        guard !base.isEmpty, !isPlaceholder, let url = URL(string: base + path) else {
            throw APIError.badURL
        }
        var req = URLRequest(url: url, timeoutInterval: 8)
        req.httpMethod = method
        if !settings.apiKey.isEmpty {
            req.setValue(settings.apiKey, forHTTPHeaderField: "X-API-Key")
        }
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse,
                  (200...299).contains(http.statusCode) else {
                let msg = String(data: data, encoding: .utf8) ?? "Unknown error"
                throw APIError.serverError(msg)
            }
            isOnline = true
            return data
        } catch let err as APIError {
            throw err
        } catch {
            // URLError / network unreachable
            isOnline = false
            throw APIError.offline
        }
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        try JSONDecoder().decode(type, from: data)
    }

    // MARK: - Pending sync

    /// Replay queued offline writes. Call when the app becomes active.
    /// Returns true if anything was synced (caller should refresh UI).
    @discardableResult
    func syncPending() async -> Bool {
        let all = LocalStore.shared.allPending()
        guard !all.isEmpty else { return false }
        var synced = 0
        for change in all {
            do {
                var body: [String: Any]? = nil
                if let data = change.bodyJSON {
                    body = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                }
                _ = try await request(change.path, method: change.method, body: body)
                LocalStore.shared.removePending(change.id)
                synced += 1
            } catch {
                break   // server still unreachable — stop, keep remainder queued
            }
        }
        return synced > 0
    }

    // MARK: - Health

    func health() async throws -> HealthResponse {
        let data = try await request("/health")
        return try decode(HealthResponse.self, from: data)
    }

    // MARK: - Events

    func eventsForDay(_ date: Date) async throws -> [CalendarEvent] {
        let d = ISO8601DateFormatter.yyyyMMdd.string(from: date)
        do {
            let data   = try await request("/events?date=\(d)")
            let events = try decode([CalendarEvent].self, from: data)
            LocalStore.shared.cacheEvents(events)
            return events
        } catch APIError.offline, APIError.badURL {
            return LocalStore.shared.eventsForDate(d)
        }
    }

    func eventsForMonth(year: Int, month: Int) async throws -> [CalendarEvent] {
        do {
            let data   = try await request("/events?year=\(year)&month=\(month)")
            let events = try decode([CalendarEvent].self, from: data)
            LocalStore.shared.cacheEvents(events)
            return events
        } catch APIError.offline, APIError.badURL {
            return LocalStore.shared.eventsForMonth(year, month)
        }
    }

    func eventsForWeek(start: Date) async throws -> [CalendarEvent] {
        let d = ISO8601DateFormatter.yyyyMMdd.string(from: start)
        do {
            let data   = try await request("/events?week_start=\(d)")
            let events = try decode([CalendarEvent].self, from: data)
            LocalStore.shared.cacheEvents(events)
            return events
        } catch APIError.offline, APIError.badURL {
            return LocalStore.shared.eventsForWeek(startStr: d)
        }
    }

    func createEvent(_ fields: [String: Any]) async throws -> Int {
        do {
            let data = try await request("/events", method: "POST", body: fields)
            let obj  = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            return obj?["id"] as? Int ?? 0
        } catch APIError.offline, APIError.badURL {
            let local = LocalStore.shared.insertEvent(fields)
            LocalStore.shared.enqueue(method: "POST", path: "/events", body: fields)
            return local.id
        }
    }

    func updateEvent(id: Int, fields: [String: Any]) async throws {
        do {
            _ = try await request("/events/\(id)", method: "PATCH", body: fields)
        } catch APIError.offline, APIError.badURL {
            LocalStore.shared.patchEvent(id, fields: fields)   // keep local cache current
            LocalStore.shared.enqueue(method: "PATCH", path: "/events/\(id)", body: fields)
        }
    }

    func deleteEvent(id: Int) async throws {
        LocalStore.shared.removeEvent(id)   // optimistic local remove
        do {
            _ = try await request("/events/\(id)", method: "DELETE")
        } catch APIError.offline, APIError.badURL {
            LocalStore.shared.enqueue(method: "DELETE", path: "/events/\(id)")
        }
    }

    // MARK: - Todos

    func todos(list: String = "all", includeCompleted: Bool = false) async throws -> [Todo] {
        do {
            let data  = try await request("/todos?list=\(list)&include_completed=\(includeCompleted)")
            let items = try decode([Todo].self, from: data)
            LocalStore.shared.cacheTodos(items)
            return items
        } catch APIError.offline, APIError.badURL {
            let l = list == "all" ? nil : list
            return LocalStore.shared.allTodos(list: l, includeCompleted: includeCompleted)
        }
    }

    func createTodo(title: String, list: String = "today") async throws -> Int {
        do {
            let data = try await request("/todos", method: "POST",
                                         body: ["title": title, "list_name": list])
            let obj  = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            return obj?["id"] as? Int ?? 0
        } catch APIError.offline, APIError.badURL {
            let local = LocalStore.shared.insertTodo(title: title, list: list)
            LocalStore.shared.enqueue(method: "POST", path: "/todos",
                                      body: ["title": title, "list_name": list])
            return local.id
        }
    }

    func toggleTodo(id: Int) async throws -> Bool {
        LocalStore.shared.toggleTodo(id)    // optimistic
        do {
            let data = try await request("/todos/\(id)/toggle", method: "PATCH")
            let obj  = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            return (obj?["completed"] as? Int ?? 0) != 0
        } catch APIError.offline, APIError.badURL {
            LocalStore.shared.enqueue(method: "PATCH", path: "/todos/\(id)/toggle")
            return LocalStore.shared.allTodos(list: nil, includeCompleted: true)
                .first { $0.id == id }?.completed != 0
        }
    }

    func deleteTodo(id: Int) async throws {
        LocalStore.shared.removeTodo(id)    // optimistic
        do {
            _ = try await request("/todos/\(id)", method: "DELETE")
        } catch APIError.offline, APIError.badURL {
            LocalStore.shared.enqueue(method: "DELETE", path: "/todos/\(id)")
        }
    }

    func reorderTodos(list: String, ids: [Int]) async throws {
        _ = try await request("/todos/reorder", method: "POST",
                              body: ["list": list, "ids": ids])
    }

    func updateTodo(id: Int, title: String? = nil, list: String? = nil,
                    priority: String? = nil, dueDate: String? = nil) async throws {
        var fields: [String: Any] = [:]
        if let title    { fields["title"]    = title }
        if let list     { fields["list_name"] = list }
        if let priority { fields["priority"] = priority }
        if let dueDate  { fields["due_date"] = dueDate }
        guard !fields.isEmpty else { return }
        do {
            _ = try await request("/todos/\(id)", method: "PATCH", body: fields)
        } catch APIError.offline, APIError.badURL {
            LocalStore.shared.patchTodo(id, fields: fields)   // keep local cache current
            LocalStore.shared.enqueue(method: "PATCH", path: "/todos/\(id)", body: fields)
        }
    }

    func clearCompletedTodos(list: String? = nil) async throws {
        let path = list != nil ? "/todos/completed?list=\(list!)" : "/todos/completed"
        _ = try await request(path, method: "DELETE")
    }

    // MARK: - Voice (requires server)

    /// After a rule-path voice response, poll for LLM background verification.
    /// Retries every 4 s for up to 40 s, then gives up (assumes ok).
    /// Calls `onCorrection` on the main actor if the LLM found an error.
    func pollVerify(token: String, onCorrection: @escaping (VerifyResult) async -> Void) {
        Task.detached(priority: .background) { [weak self] in
            guard let self else { return }
            for _ in 1...10 {
                try? await Task.sleep(nanoseconds: 4_000_000_000)  // 4 s
                guard let data = try? await self.request("/voice/verify/\(token)"),
                      let result = try? JSONDecoder().decode(VerifyResult.self, from: data)
                else { continue }

                if result.pending == true { continue }  // not ready yet
                if result.ok == true { return }         // confirmed correct — silent

                // LLM found a correction
                await onCorrection(result)
                return
            }
            // Timed out — assume ok
        }
    }

    func sendText(_ transcript: String) async throws -> VoiceResponse {
        let data = try await request("/voice/text", method: "POST",
                                     body: ["transcript": transcript])
        return try decode(VoiceResponse.self, from: data)
    }

    func sendAudio(_ audioData: Data) async throws -> VoiceResponse {
        guard !base.isEmpty, let url = URL(string: base + "/voice") else {
            throw APIError.badURL
        }
        var req = URLRequest(url: url, timeoutInterval: 30)
        req.httpMethod = "POST"
        if !settings.apiKey.isEmpty {
            req.setValue(settings.apiKey, forHTTPHeaderField: "X-API-Key")
        }
        let boundary = UUID().uuidString
        req.setValue("multipart/form-data; boundary=\(boundary)",
                     forHTTPHeaderField: "Content-Type")
        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"audio\"; filename=\"audio.wav\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: audio/wav\r\n\r\n".data(using: .utf8)!)
        body.append(audioData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        req.httpBody = body
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            isOnline = true
            return try decode(VoiceResponse.self, from: data)
        } catch {
            isOnline = false
            throw APIError.offline
        }
    }

    // MARK: - Courses

    func courses() async throws -> [Course] {
        let data = try await request("/courses")
        return try decode([Course].self, from: data)
    }

    @discardableResult
    func createCourse(number: String, name: String, color: String, partners: [String]) async throws -> Int {
        let body: [String: Any] = ["number": number, "name": name, "color": color, "partners": partners]
        let data = try await request("/courses", method: "POST", body: body)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return json?["id"] as? Int ?? -1
    }

    func updateCourse(id: Int, number: String, name: String, color: String, partners: [String]) async throws {
        let body: [String: Any] = ["number": number, "name": name, "color": color, "partners": partners]
        _ = try await request("/courses/\(id)", method: "PATCH", body: body)
    }

    func deleteCourse(id: Int) async throws {
        _ = try await request("/courses/\(id)", method: "DELETE")
    }

    // MARK: - Assignments

    func allAssignments() async throws -> [Assignment] {
        let data = try await request("/assignments")
        return try decode([Assignment].self, from: data)
    }

    @discardableResult
    func createAssignment(courseId: Int, title: String, dueDate: String = "") async throws -> Int {
        let body: [String: Any] = ["course_id": courseId, "title": title, "due_date": dueDate]
        let data = try await request("/assignments", method: "POST", body: body)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return json?["id"] as? Int ?? -1
    }

    func updateAssignment(id: Int, title: String? = nil, dueDate: String? = nil,
                          calendarEventId: Int? = nil) async throws {
        var body: [String: Any] = [:]
        if let v = title           { body["title"]             = v }
        if let v = dueDate         { body["due_date"]          = v }
        if let v = calendarEventId { body["calendar_event_id"] = v }
        _ = try await request("/assignments/\(id)", method: "PATCH", body: body)
    }

    @discardableResult
    func toggleAssignment(id: Int) async throws -> Bool {
        let data = try await request("/assignments/\(id)/toggle", method: "PATCH", body: [:])
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return (json?["completed"] as? Int ?? 0) != 0
    }

    func deleteAssignment(id: Int) async throws {
        _ = try await request("/assignments/\(id)", method: "DELETE")
    }
}

// MARK: - Errors

enum APIError: LocalizedError {
    case badURL
    case offline
    case serverError(String)

    var errorDescription: String? {
        switch self {
        case .badURL:
            return "Server URL is not configured. Go to Settings and enter your Mac's Tailscale address."
        case .offline:
            return "Mac is unreachable — changes saved locally and will sync when connected."
        case .serverError(let msg):
            return msg
        }
    }
}

// MARK: - Helpers

extension ISO8601DateFormatter {
    static let yyyyMMdd: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()
}

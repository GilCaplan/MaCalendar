import Foundation
import UIKit
@preconcurrency import UserNotifications

/// Keeps the app alive for the ~30 s iOS grants after it's backgrounded, so a
/// voice command that's mid-flight finishes instead of being suspended with
/// its stream half-read. Without this, walking away from the app right after
/// speaking dropped the thinking timeline (the Mac still ran the command —
/// the phone just stopped hearing about it).
@MainActor
final class BackgroundAssertion {
    private var id: UIBackgroundTaskIdentifier = .invalid

    func begin(_ name: String) {
        guard id == .invalid else { return }
        id = UIApplication.shared.beginBackgroundTask(withName: name) { [weak self] in
            self?.end()          // expiration handler — iOS is out of patience
        }
    }

    func end() {
        guard id != .invalid else { return }
        UIApplication.shared.endBackgroundTask(id)
        id = .invalid
    }
}

@MainActor
class APIClient: ObservableObject {
    @Published var isLoading  = false
    @Published var lastError: String?
    @Published var isOnline   = true
    /// Bumped whenever every view should re-fetch from the Mac (foreground, 30 s poll,
    /// reconnect, voice command). Views subscribe with `.onReceive(api.$refreshTick)`.
    @Published var refreshTick = 0
    func requestRefresh() { refreshTick &+= 1 }

    /// While things are changing (a voice command just ran, an edit was saved) the
    /// background poll drops to 1 s; it returns to 30 s once this window passes.
    private var isFlushingVoice = false
    @Published var burstUntil = Date.distantPast
    func burstRefresh(seconds: TimeInterval = 45) { burstUntil = max(burstUntil, Date().addingTimeInterval(seconds)) }
    var pollInterval: TimeInterval { Date() < burstUntil ? 1 : 30 }

    private let settings: AppSettings

    init(settings: AppSettings) {
        self.settings = settings
    }

    // MARK: - Base

    /// Normalised server base URL. Accepts what people actually type:
    /// "100.92.216.112", "100.92.216.112:8080", "http://100.92.216.112:8080/",
    /// "macbook-air" (Tailscale MagicDNS) — and always yields http://host:port.
    private var base: String {
        var url = settings.serverURL
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: .init(charactersIn: "/"))
        guard !url.isEmpty else { return "" }
        if url.hasPrefix("https://") { url = "http://" + url.dropFirst(8) }
        if !url.hasPrefix("http://") { url = "http://" + url }
        // add the default port when none was given (host may be an IP or a name)
        let hostPart = url.dropFirst(7)
        if !hostPart.contains(":") { url += ":8080" }
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
            // Only assign when it actually changes: these are @Published, so a
            // redundant write still republishes and re-renders every subscriber.
            // With /changes polled every 2 s, blind assignment meant a full
            // re-render twice a second-and-a-half for as long as the Mac was away.
            if !isOnline {
                isOnline = true
                requestRefresh()
                // The Mac just came back. Flush anything parked while it was away
                // now, rather than on the next 30 s tick — a command you spoke
                // minutes ago should run the moment it can, not up to a minute later.
                Task { [weak self] in
                    _ = await self?.syncPending()
                    await self?.syncPendingVoice()
                }
            }
            return data
        } catch let err as APIError {
            throw err
        } catch {
            // URLError / network unreachable — keep the real reason for Settings › Test Connection
            if isOnline { isOnline = false }
            let reason = "\(url.absoluteString): \(error.localizedDescription)"
            if lastError != reason { lastError = reason }
            throw APIError.offline(error.localizedDescription)
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
        guard !LocalStore.shared.allPending().isEmpty else { return false }
        var synced = 0
        // Re-read the queue each pass: replaying a create rewrites the paths of
        // later entries that still point at its temporary offline id.
        while let change = LocalStore.shared.allPending().first {
            do {
                var body: [String: Any]? = nil
                if let data = change.bodyJSON {
                    body = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                }
                let data = try await request(change.path, method: change.method, body: body)

                // A create comes back with the row the Mac actually stored. Point
                // anything still queued against the placeholder id at the real one,
                // otherwise "add a task offline, tick it off, reconnect" loses the tick.
                if change.method == "POST", let temp = temporaryID(in: change),
                   let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let realID = obj["id"] as? Int {
                    LocalStore.shared.remapTemporaryID(temp, to: realID)
                }

                LocalStore.shared.removePending(change.id)
                synced += 1
            } catch APIError.offline {
                break        // the Mac is away again — keep the rest for later
            } catch APIError.serverError(let detail) where detail.contains("\"code\": 409")
                                                        || detail.contains("\"code\":409") {
                // The same event was changed on the Mac while we were away. The
                // Mac's version stands — say so rather than losing an edit in
                // silence, on whichever side it happened.
                LocalStore.shared.removePending(change.id)
                Self.notify(title: "One edit didn't apply",
                            body: "That event had already been changed on your Mac, so its version was kept.")
                requestRefresh()
            } catch {
                // The Mac answered and refused it (404 for a row that no longer
                // exists, 400 for something malformed). Retrying cannot help, and
                // leaving it at the head of the queue blocked every later change
                // forever. Drop it and carry on.
                LocalStore.shared.removePending(change.id)
            }
        }
        return synced > 0
    }

    /// Replay voice commands recorded while the Mac was away.
    ///
    /// The recording is uploaded exactly as it would have been live, and the
    /// result is reported with a local notification — the command may well run
    /// while the user is in another app, and silently changing their calendar
    /// without telling them would be worse than not running it at all.
    @discardableResult
    func syncPendingVoice() async -> Int {
        // Several things can ask for a flush at once (reconnect, foreground, the
        // poll loop, opening the queue screen); replaying the same audio twice
        // would create the event twice.
        guard !isFlushingVoice else { return 0 }
        let queued = LocalStore.shared.pendingVoice.filter { $0.status == .queued || $0.status == .failed }
        guard !queued.isEmpty else { return 0 }
        isFlushingVoice = true
        defer { isFlushingVoice = false }
        var ran = 0
        for cmd in queued {
            guard let audio = LocalStore.shared.voiceAudio(cmd) else {
                LocalStore.shared.removeVoice(cmd.id)
                continue
            }
            LocalStore.shared.updateVoice(cmd.id, status: .running)
            do {
                let response = try await sendAudio(audio)
                LocalStore.shared.updateVoice(cmd.id, status: .done,
                                              result: response.message.isEmpty ? "Done" : response.message)
                Self.notify(title: "Ran your queued command", body: response.message)
                ran += 1
                burstRefresh()
                requestRefresh()
            } catch APIError.offline {
                LocalStore.shared.updateVoice(cmd.id, status: .queued)   // still away — try again later
                break
            } catch {
                LocalStore.shared.updateVoice(cmd.id, status: .failed,
                                              result: error.localizedDescription)
                Self.notify(title: "A queued command didn't run",
                            body: error.localizedDescription)
            }
        }
        return ran
    }

    /// Local notification — the same pattern the workout rest timer uses.
    nonisolated static func notify(title: String, body: String) {
        let center = UNUserNotificationCenter.current()
        center.getNotificationSettings { settings in
            guard settings.authorizationStatus != .denied else { return }
            if settings.authorizationStatus == .notDetermined {
                center.requestAuthorization(options: [.alert, .sound]) { _, _ in }
            }
            let content = UNMutableNotificationContent()
            content.title = title
            content.body = body.isEmpty ? "Tap to see what changed." : body
            content.sound = .default
            center.add(UNNotificationRequest(identifier: UUID().uuidString,
                                             content: content, trigger: nil))
        }
    }

    /// The temporary offline id a create was made under, if it had one.
    /// LocalStore hands out negative ids for rows created while disconnected.
    private func temporaryID(in change: PendingChange) -> Int? {
        guard let data = change.bodyJSON,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let temp = obj["_temp_id"] as? Int, temp < 0
        else { return nil }
        return temp
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

    // MARK: - Holidays

    /// Jewish/Israeli holidays for [start, end]. Computed server-side (Mac)
    /// so the holiday list stays identical across devices. Not cached for
    /// offline use — returns [] if unreachable, same as any other refresh.
    func holidays(start: Date, end: Date, israel: Bool = true) async throws -> [Holiday] {
        let s = ISO8601DateFormatter.yyyyMMdd.string(from: start)
        let e = ISO8601DateFormatter.yyyyMMdd.string(from: end)
        let data = try await request("/holidays?start=\(s)&end=\(e)&israel=\(israel ? 1 : 0)")
        return try decode([Holiday].self, from: data)
    }

    func createEvent(_ fields: [String: Any]) async throws -> Int {
        burstRefresh(seconds: 10)
        do {
            let data = try await request("/events", method: "POST", body: fields)
            let obj  = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            return obj?["id"] as? Int ?? 0
        } catch APIError.offline, APIError.badURL {
            let local = LocalStore.shared.insertEvent(fields)
            // Carry the placeholder id so syncPending can repoint anything queued
            // against it once the Mac assigns the real one. The server ignores it.
            LocalStore.shared.enqueue(method: "POST", path: "/events",
                                      body: fields.merging(["_temp_id": local.id]) { a, _ in a })
            return local.id
        }
    }

    func updateEvent(id: Int, fields: [String: Any]) async throws {
        burstRefresh(seconds: 10)
        do {
            _ = try await request("/events/\(id)", method: "PATCH", body: fields)
        } catch APIError.offline, APIError.badURL {
            LocalStore.shared.patchEvent(id, fields: fields)   // keep local cache current
            // Record which version this edit was made from. If the same event is
            // changed on the Mac before we reconnect, the Mac refuses the replay
            // (409) instead of quietly discarding whichever edit came second.
            var queued = fields
            if let base = LocalStore.shared.event(id)?.updatedAt {
                queued["base_updated_at"] = base
            }
            LocalStore.shared.enqueue(method: "PATCH", path: "/events/\(id)", body: queued)
        }
    }

    func deleteEvent(id: Int) async throws {
        burstRefresh(seconds: 10)
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

    /// Tags are always sent explicitly (possibly empty) so the server's own
    /// "tag mode" (config.todo.auto_tag) never overrides what the phone chose.
    func createTodo(title: String, list: String = "today", tags: [String] = []) async throws -> Int {
        let body: [String: Any] = ["title": title, "list_name": list, "tags": tags]
        do {
            let data = try await request("/todos", method: "POST", body: body)
            let obj  = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            return obj?["id"] as? Int ?? 0
        } catch APIError.offline, APIError.badURL {
            let local = LocalStore.shared.insertTodo(title: title, list: list, tags: tags)
            LocalStore.shared.enqueue(method: "POST", path: "/todos",
                                      body: body.merging(["_temp_id": local.id]) { a, _ in a })
            return local.id
        }
    }

    // MARK: - Tags

    func tags() async throws -> [TodoTag] {
        do {
            let data  = try await request("/tags")
            let items = try decode([TodoTag].self, from: data)
            LocalStore.shared.cacheTags(items)
            return items
        } catch APIError.offline, APIError.badURL {
            return LocalStore.shared.allTags()
        }
    }

    func createTag(name: String) async throws {
        LocalStore.shared.insertTag(TodoTag(name: name))    // optimistic
        do {
            _ = try await request("/tags", method: "POST", body: ["name": name])
        } catch APIError.offline, APIError.badURL {
            LocalStore.shared.enqueue(method: "POST", path: "/tags", body: ["name": name])
        }
    }

    func deleteTag(name: String) async throws {
        LocalStore.shared.removeTag(name)                    // optimistic
        let encoded = name.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? name
        do {
            _ = try await request("/tags/\(encoded)", method: "DELETE")
        } catch APIError.offline, APIError.badURL {
            LocalStore.shared.enqueue(method: "DELETE", path: "/tags/\(encoded)")
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
                    priority: String? = nil, dueDate: String? = nil,
                    tags: [String]? = nil) async throws {
        var fields: [String: Any] = [:]
        if let title    { fields["title"]    = title }
        if let list     { fields["list_name"] = list }
        if let priority { fields["priority"] = priority }
        if let dueDate  { fields["due_date"] = dueDate }
        if let tags     { fields["tags"]     = tags }
        guard !fields.isEmpty else { return }
        do {
            _ = try await request("/todos/\(id)", method: "PATCH", body: fields)
        } catch APIError.offline, APIError.badURL {
            LocalStore.shared.patchTodo(id, fields: fields)   // keep local cache current
            var queued = fields
            if let base = LocalStore.shared.todo(id)?.updatedAt {
                queued["base_updated_at"] = base
            }
            LocalStore.shared.enqueue(method: "PATCH", path: "/todos/\(id)", body: queued)
        }
    }

    func clearCompletedTodos(list: String? = nil) async throws {
        let path = list != nil ? "/todos/completed?list=\(list!)" : "/todos/completed"
        _ = try await request(path, method: "DELETE")
    }

    // MARK: - Workout
    //
    // Workout IDs are client-generated UUIDs end-to-end (both locally and on
    // the server), so — unlike events/todos — there's no temp-ID/remap dance:
    // create locally (optimistic, in WorkoutStore) -> attempt to push to the
    // server immediately -> on failure/offline, fall back to LocalStore's
    // generic pending-write queue (same one events/todos use), replayed
    // generically by syncPending() above.

    private func workoutBody<T: Encodable>(_ value: T) -> [String: Any]? {
        guard let data = try? JSONEncoder.workout.encode(value),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        return obj
    }

    private func bodyId(_ p: PendingChange) -> UUID? {
        guard let data = p.bodyJSON,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let idStr = obj["id"] as? String else { return nil }
        return UUID(uuidString: idStr)
    }

    /// True if a POST to `path` for `id` is still sitting in the offline
    /// queue — i.e. the record doesn't exist server-side yet, so a PATCH/DELETE
    /// against it right now would 404 even though we're online.
    private func hasPendingCreate(path: String, id: UUID) -> Bool {
        LocalStore.shared.allPending().contains { $0.method == "POST" && $0.path == path && bodyId($0) == id }
    }

    // MARK: Workout — exercises

    @discardableResult
    func workoutExercises() async throws -> [Exercise] {
        do {
            let data = try await request("/workout/exercises")
            let items = try JSONDecoder.workout.decode([Exercise].self, from: data)
            WorkoutStore.shared.cacheExercises(items)
            return items
        } catch APIError.offline, APIError.badURL {
            return WorkoutStore.shared.exercises
        }
    }

    /// Called after WorkoutStore has already created the exercise locally
    /// (find-or-create is always local-first — exercises are never edited or
    /// deleted, only created, so there's no update/delete race to guard here).
    func syncNewExercise(_ exercise: Exercise) async {
        guard let body = workoutBody(exercise) else { return }
        do {
            _ = try await request("/workout/exercises", method: "POST", body: body)
        } catch APIError.offline, APIError.badURL {
            LocalStore.shared.enqueue(method: "POST", path: "/workout/exercises", body: body)
        } catch {
            // Other server error (e.g. validation) — don't enqueue a write
            // that would just fail identically on replay.
        }
    }

    // MARK: Workout — templates

    @discardableResult
    func workoutTemplates(includeDrafts: Bool = false) async throws -> [WorkoutTemplate] {
        do {
            let path = "/workout/templates" + (includeDrafts ? "?include_drafts=true" : "")
            let data = try await request(path)
            let items = try JSONDecoder.workout.decode([WorkoutTemplate].self, from: data)
            WorkoutStore.shared.cacheTemplates(items, includeDrafts: includeDrafts)
            return items
        } catch APIError.offline, APIError.badURL {
            return WorkoutStore.shared.templates
        }
    }

    func syncTemplate(_ template: WorkoutTemplate, isNew: Bool) async {
        guard let body = workoutBody(template) else { return }
        let path = isNew ? "/workout/templates" : "/workout/templates/\(template.id.uuidString)"
        let method = isNew ? "POST" : "PATCH"
        if !isNew && hasPendingCreate(path: "/workout/templates", id: template.id) {
            // Create hasn't synced yet — queue behind it so replay order is POST-then-PATCH.
            LocalStore.shared.enqueue(method: method, path: path, body: body)
            return
        }
        do {
            _ = try await request(path, method: method, body: body)
        } catch APIError.offline, APIError.badURL {
            LocalStore.shared.enqueue(method: method, path: path, body: body)
        } catch { }
    }

    func deleteWorkoutTemplate(_ id: UUID) async {
        let path = "/workout/templates/\(id.uuidString)"
        // If it never made it to the server (create still queued), just drop
        // the queued create — nothing to delete remotely.
        if let pc = LocalStore.shared.allPending().first(where: {
            $0.method == "POST" && $0.path == "/workout/templates" && bodyId($0) == id
        }) {
            LocalStore.shared.removePending(pc.id)
            return
        }
        do {
            _ = try await request(path, method: "DELETE")
        } catch APIError.offline, APIError.badURL {
            LocalStore.shared.enqueue(method: "DELETE", path: path)
        } catch { }
    }

    /// Finalizes an AI-drafted template. The draft already exists server-side
    /// (created by the generate_workout_routine voice action), so there's no
    /// pending-create race to guard against here.
    func approveWorkoutTemplate(_ id: UUID) async {
        let path = "/workout/templates/\(id.uuidString)/approve"
        do {
            _ = try await request(path, method: "PATCH")
        } catch APIError.offline, APIError.badURL {
            LocalStore.shared.enqueue(method: "PATCH", path: path)
        } catch { }
    }

    // MARK: Workout — sessions

    @discardableResult
    func workoutSessions(limit: Int? = nil, startDate: String? = nil, endDate: String? = nil) async throws -> [WorkoutSession] {
        var q: [String] = []
        if let limit { q.append("limit=\(limit)") }
        if let startDate { q.append("start_date=\(startDate)") }
        if let endDate { q.append("end_date=\(endDate)") }
        let qs = q.isEmpty ? "" : "?" + q.joined(separator: "&")
        do {
            let data = try await request("/workout/sessions" + qs)
            let items = try JSONDecoder.workout.decode([WorkoutSession].self, from: data)
            WorkoutStore.shared.cacheSessions(items)
            return items
        } catch APIError.offline, APIError.badURL {
            return WorkoutStore.shared.sessions
        }
    }

    func syncSession(_ session: WorkoutSession, isNew: Bool) async {
        guard let body = workoutBody(session) else { return }
        let path = isNew ? "/workout/sessions" : "/workout/sessions/\(session.id.uuidString)"
        let method = isNew ? "POST" : "PATCH"
        if !isNew && hasPendingCreate(path: "/workout/sessions", id: session.id) {
            LocalStore.shared.enqueue(method: method, path: path, body: body)
            return
        }
        do {
            _ = try await request(path, method: method, body: body)
        } catch APIError.offline, APIError.badURL {
            LocalStore.shared.enqueue(method: method, path: path, body: body)
        } catch { }
    }

    func deleteWorkoutSession(_ id: UUID) async {
        let path = "/workout/sessions/\(id.uuidString)"
        if let pc = LocalStore.shared.allPending().first(where: {
            $0.method == "POST" && $0.path == "/workout/sessions" && bodyId($0) == id
        }) {
            LocalStore.shared.removePending(pc.id)
            return
        }
        do {
            _ = try await request(path, method: "DELETE")
        } catch APIError.offline, APIError.badURL {
            LocalStore.shared.enqueue(method: "DELETE", path: path)
        } catch { }
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

    /// The last few commands the Mac ran (either device). Used to recover the
    /// outcome when a stream is cut short — the Mac finished the work, the
    /// phone just lost the connection.
    func recentCommands(limit: Int = 3) async -> [MemoryExample] {
        guard let data = try? await request("/memory?limit=\(limit)"),
              let list = try? JSONDecoder().decode(MemoryListResponse.self, from: data)
        else { return [] }
        return list.examples
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
            throw APIError.offline(error.localizedDescription)
        }
    }

    /// Streaming variant of sendAudio: POST /voice/stream returns NDJSON —
    /// one {"type":"step",...} line per pipeline stage, then {"type":"result",...}.
    /// `onStep` fires on the main actor as each stage arrives.
    func sendAudioStreaming(_ audioData: Data,
                            onStep: @escaping (TraceStep) -> Void) async throws -> VoiceResponse {
        guard !base.isEmpty, let url = URL(string: base + "/voice/stream") else {
            throw APIError.badURL
        }
        var req = URLRequest(url: url, timeoutInterval: 120)
        req.httpMethod = "POST"
        if !settings.apiKey.isEmpty {
            req.setValue(settings.apiKey, forHTTPHeaderField: "X-API-Key")
        }
        let boundary = UUID().uuidString
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"audio\"; filename=\"audio.wav\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: audio/wav\r\n\r\n".data(using: .utf8)!)
        body.append(audioData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        req.httpBody = body

        let decoder = JSONDecoder()
        let assertion = BackgroundAssertion()
        assertion.begin("voice-command")
        defer { assertion.end() }
        do {
            let (bytes, resp) = try await URLSession.shared.bytes(for: req)
            guard let http = resp as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                throw APIError.serverError("HTTP error")
            }
            isOnline = true
            var final: VoiceResponse?
            for try await line in bytes.lines {
                guard let data = line.data(using: .utf8),
                      let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let type = obj["type"] as? String else { continue }
                if type == "step", let step = try? decoder.decode(TraceStep.self, from: data) {
                    onStep(step)
                } else if type == "result" {
                    final = try? decoder.decode(VoiceResponse.self, from: data)
                }
            }
            guard let final else { throw APIError.serverError("Stream ended without a result") }
            return final
        } catch let err as APIError {
            throw err
        } catch {
            isOnline = false
            throw APIError.offline(error.localizedDescription)
        }
    }

    // MARK: - Vocabulary (STT auto-correct)

    func vocab() async throws -> VocabState {
        try decode(VocabState.self, from: try await request("/vocab"))
    }

    func vocabAddWord(_ word: String, aliases: [String] = []) async throws {
        _ = try await request("/vocab", method: "POST", body: ["word": word, "aliases": aliases])
    }

    /// Teach a correction: STT heard `wrong`, you meant `right`.
    func vocabTeach(wrong: String, right: String) async throws {
        _ = try await request("/vocab/alias", method: "POST", body: ["wrong": wrong, "right": right])
    }

    func vocabDelete(word: String, alias: String? = nil) async throws {
        var path = "/vocab/" + (word.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? word)
        if let alias, let a = alias.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) {
            path += "?alias=" + a
        }
        _ = try await request(path, method: "DELETE")
    }

    func vocabSettings(autoCorrect: Bool? = nil, learnAliases: Bool? = nil, threshold: Double? = nil) async throws -> VocabState {
        var body: [String: Any] = [:]
        if let autoCorrect { body["auto_correct"] = autoCorrect }
        if let learnAliases { body["learn_aliases"] = learnAliases }
        if let threshold { body["threshold"] = threshold }
        return try decode(VocabState.self, from: try await request("/vocab/settings", method: "PATCH", body: body))
    }

    func vocabImport(text: String? = nil, source: String? = nil, names: [String]? = nil) async throws -> [VocabCandidate] {
        var body: [String: Any] = [:]
        if let text { body["text"] = text }
        if let source { body["source"] = source }
        if let names { body["names"] = names }
        return try decode(VocabImportResult.self, from: try await request("/vocab/import", method: "POST", body: body)).candidates
    }

    func vocabAddWords(_ words: [String]) async throws {
        _ = try await request("/vocab/bulk", method: "POST", body: ["words": words])
    }

    func vocabOnboarding() async throws -> VocabOnboarding {
        try decode(VocabOnboarding.self, from: try await request("/vocab/onboarding"))
    }

    func vocabOnboardingSubmit(answers: [String: [String]], presets: [String]) async throws {
        _ = try await request("/vocab/onboarding", method: "POST",
                              body: ["answers": answers, "presets": presets, "done": true])
    }

    // MARK: - Pending (queued) commands

    func retryPending(id: Int) async throws -> VoiceResponse {
        try decode(VoiceResponse.self, from: try await request("/pending/\(id)/retry", method: "POST"))
    }

    // MARK: - Command memory feedback

    func unreviewedCommands(limit: Int = 30) async throws -> [MemoryExample] {
        try decode(UnreviewedResponse.self, from: try await request("/memory/unreviewed?limit=\(limit)")).examples
    }

    func unreviewedCount() async -> Int {
        (try? await unreviewedCommands(limit: 50).count) ?? 0
    }

    func skipAllUnreviewed() async -> Int? {
        guard let d = try? await request("/memory/unreviewed/skip", method: "POST", body: [:]),
              let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return nil }
        return o["skipped"] as? Int
    }

    func memoryFeedback(id: Int, feedback: String, correction: [[String: Any]]? = nil, notes: String = "") async {
        var body: [String: Any] = ["feedback": feedback, "notes": notes]
        if let correction { body["correction"] = correction }
        _ = try? await request("/memory/\(id)/feedback", method: "POST", body: body)
    }

    // MARK: - Timers & counters

    func timers(archived: Bool = false) async throws -> [WorkTimer] {
        try decode(TimersResponse.self, from: try await request("/timers" + (archived ? "?archived=1" : ""))).timers
    }
    func createTimer(_ body: [String: Any]) async -> Bool { (try? await request("/timers", method: "POST", body: body)) != nil }
    func updateTimer(_ id: Int, _ body: [String: Any]) async { _ = try? await request("/timers/\(id)", method: "PATCH", body: body) }
    func deleteTimer(_ id: Int) async { _ = try? await request("/timers/\(id)", method: "DELETE") }
    func startTimer(_ id: Int) async { _ = try? await request("/timers/\(id)/start", method: "POST", body: [:]) }
    func stopTimer(_ id: Int) async { _ = try? await request("/timers/\(id)/stop", method: "POST", body: [:]) }
    func timerSessions(_ id: Int) async throws -> [TimerSession] {
        try decode(TimerSessionsResponse.self, from: try await request("/timers/\(id)/sessions")).sessions
    }
    func deleteTimerSession(_ id: Int) async { _ = try? await request("/timer_sessions/\(id)", method: "DELETE") }

    /// Log time you forgot to start the timer for — the Mac's "Log past time…".
    /// `end` omitted creates a session that is still running.
    func logTimerSession(_ id: Int, start: Date, end: Date?, title: String = "") async -> Bool {
        let f = ISO8601DateFormatter()
        var body: [String: Any] = ["start_time": f.string(from: start), "title": title]
        if let end { body["end_time"] = f.string(from: end) }
        return (try? await request("/timers/\(id)/sessions", method: "POST", body: body)) != nil
    }

    func counters(archived: Bool = false) async throws -> [TallyCounter] {
        try decode(CountersResponse.self, from: try await request("/counters" + (archived ? "?archived=1" : ""))).counters
    }
    func createCounter(_ body: [String: Any]) async -> Bool { (try? await request("/counters", method: "POST", body: body)) != nil }
    func updateCounter(_ id: Int, _ body: [String: Any]) async { _ = try? await request("/counters/\(id)", method: "PATCH", body: body) }
    func deleteCounter(_ id: Int) async { _ = try? await request("/counters/\(id)", method: "DELETE") }
    func pressCounter(_ id: Int, delta: Int) async { _ = try? await request("/counters/\(id)/press", method: "POST", body: ["delta": delta]) }
    func cashOutCounter(_ id: Int) async { _ = try? await request("/counters/\(id)/cashout", method: "POST", body: [:]) }

    /// A few bytes that change whenever anything in the Mac's database does.
    /// Polling this is cheap enough to do every couple of seconds, so a change
    /// made on the Mac shows up almost at once instead of on the next 30 s
    /// full refresh. Returns nil if the Mac can't be reached.
    func changeToken() async -> String? {
        guard let data = try? await request("/changes"),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return obj["token"] as? String
    }

    /// Pull calendar events into the task list — the Mac's "Sync Today" button.
    /// `list` is "today" or "general".
    @discardableResult
    func syncTodosFromCalendar(list: String = "today") async -> Int {
        guard let data = try? await request("/todos/sync", method: "POST", body: ["list_name": list]),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let n = obj["synced"] as? Int
        else { return 0 }
        return n
    }

    // MARK: - Event categories

    func categories() async throws -> [EventCategory] {
        try decode(CategoriesResponse.self, from: try await request("/categories")).categories
    }

    func upsertCategory(name: String, color: String, alt: String, keywords: [String]) async -> Bool {
        (try? await request("/categories", method: "POST",
                            body: ["name": name, "color": color, "alt": alt, "keywords": keywords])) != nil
    }

    func deleteCategory(_ name: String) async {
        let enc = name.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? name
        _ = try? await request("/categories/\(enc)", method: "DELETE")
    }

    func recolorEvents(force: Bool) async -> Int? {
        guard let data = try? await request("/categories/recolor" + (force ? "?force=1" : ""), method: "POST", body: [:]),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        return obj["updated"] as? Int
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

    func clearCompletedAssignments(courseId: Int? = nil) async throws {
        let path = courseId != nil ? "/assignments/completed?course_id=\(courseId!)" : "/assignments/completed"
        _ = try await request(path, method: "DELETE")
    }
}

// MARK: - Errors

enum APIError: LocalizedError {
    case badURL
    case offline(String = "")
    case serverError(String)

    var errorDescription: String? {
        switch self {
        case .badURL:
            return "Server URL is not configured. Go to Settings and enter your Mac's Tailscale address (http://100.92.216.112:8080)."
        case .offline(let why):
            return "Mac is unreachable" + (why.isEmpty ? "" : " (\(why))") + " — changes saved locally and will sync when connected."
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

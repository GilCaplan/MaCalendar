import Foundation

struct CalendarEvent: Identifiable, Codable, Equatable {
    let id: Int
    var title: String
    var date: String
    var startTime: String
    var endTime: String
    var attendees: String
    var location: String
    var description: String
    var color: String
    var recurrence: String
    var recurrenceEnd: String
    // Sync bookkeeping — 'local' | 'ics' | 'outlook'. ICS-sourced events are
    // read-only (no write endpoint behind a subscription link); Outlook
    // events stay editable when two-way sync is on.
    var source: String? = nil
    var externalSource: String? = nil
    var externalId: String? = nil

    enum CodingKeys: String, CodingKey {
        case id, title, date, color, recurrence, attendees, location, description, source
        case startTime      = "start_time"
        case endTime        = "end_time"
        case recurrenceEnd  = "recurrence_end"
        case externalSource = "external_source"
        case externalId     = "external_id"
    }

    var displayTime: String {
        guard !startTime.isEmpty else { return "" }
        return endTime.isEmpty ? startTime : "\(startTime) – \(endTime)"
    }

    var isReadOnly: Bool { source == "ics" }
}

struct Todo: Identifiable, Codable, Equatable {
    let id: Int
    var title: String
    var list: String
    var completed: Int
    var priority: String
    var dueDate: String

    enum CodingKeys: String, CodingKey {
        case id, title, list, completed, priority
        case dueDate = "due_date"
    }

    var isDone: Bool { completed != 0 }
}

struct VoiceResponse: Codable {
    let message: String
    let actions: [String]
    let refresh: String
    let parse: String           // "rule" | "hybrid" | "llm" | "error"
    let verifyToken: String?    // present only for "rule" responses; poll /voice/verify/<token>

    enum CodingKeys: String, CodingKey {
        case message, actions, refresh, parse
        case verifyToken = "verify_token"
    }
}

/// Returned by GET /voice/verify/<token>
struct VerifyResult: Codable {
    let pending: Bool?          // true = LLM not done yet
    let ok: Bool?               // true = no correction needed
    let severity: String?       // "minor" | "major"
    let patch: [String: String]? // minor: fields to PATCH on existing record
    let action: String?         // major: corrected action name
    let parameters: [String: AnyCodable]? // major: corrected params
    let speech: String?         // TTS string for user
    let refresh: String?        // "events" | "todos" | ""
}

struct Holiday: Codable, Equatable, Identifiable {
    var nameEn: String
    var nameHe: String
    var category: String   // "major" | "minor" | "fast" | "modern"
    var gregorianErevStart: String   // ISO date — evening-before civil date
    var gregorianEnd: String         // ISO date — last full civil day

    enum CodingKeys: String, CodingKey {
        case nameEn = "name_en"
        case nameHe = "name_he"
        case category
        case gregorianErevStart = "gregorian_erev_start"
        case gregorianEnd = "gregorian_end"
    }

    var id: String { "\(nameEn)-\(gregorianErevStart)" }

    /// True if *date* (yyyy-MM-dd) is the erev (evening-before) day of this holiday.
    func isErev(on date: String) -> Bool { date == gregorianErevStart }

    /// True if *date* (yyyy-MM-dd) falls anywhere within this holiday's span.
    func spans(_ date: String) -> Bool { date >= gregorianErevStart && date <= gregorianEnd }
}

struct HealthResponse: Codable {
    let status: String
    let llm: String
    let db: String
}

struct Course: Identifiable, Codable, Equatable {
    let id: Int           // negative = local temp, positive = server ID
    var number: String
    var name: String
    var color: String
    var partners: [String]

    enum CodingKeys: String, CodingKey {
        case id, number, name, color, partners
    }
}

struct Assignment: Identifiable, Codable, Equatable {
    let id: Int           // negative = local temp, positive = server ID
    var courseId: Int
    var title: String
    var dueDate: String   // "YYYY-MM-DD" or ""
    // The server serializes this straight from a SQLite INTEGER column (0/1),
    // never a JSON true/false, so JSONDecoder's strict Bool decoding threw on
    // every GET /assignments — which silently broke loading (and, via the
    // try? refresh after a save, made new assignments vanish right after
    // being added). Int + isDone mirrors Todo.completed's already-correct pattern.
    var completed: Int
    var calendarEventId: Int?

    enum CodingKeys: String, CodingKey {
        case id, courseId = "course_id", title, dueDate = "due_date", completed, calendarEventId = "calendar_event_id"
    }

    var isDone: Bool { completed != 0 }
}

// Lightweight type-erased Codable value for heterogeneous JSON dicts
struct AnyCodable: Codable {
    let value: Any
    init(_ value: Any) { self.value = value }
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if let v = try? c.decode(Bool.self)   { value = v; return }
        if let v = try? c.decode(Int.self)    { value = v; return }
        if let v = try? c.decode(Double.self) { value = v; return }
        if let v = try? c.decode(String.self) { value = v; return }
        if let v = try? c.decode([String].self) { value = v; return }
        value = ""
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch value {
        case let v as Bool:     try c.encode(v)
        case let v as Int:      try c.encode(v)
        case let v as Double:   try c.encode(v)
        case let v as String:   try c.encode(v)
        case let v as [String]: try c.encode(v)
        default: try c.encodeNil()
        }
    }
}

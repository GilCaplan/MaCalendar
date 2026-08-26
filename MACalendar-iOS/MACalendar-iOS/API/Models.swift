import Foundation
import UIKit

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
    var tags: [String]

    enum CodingKeys: String, CodingKey {
        case id, title, list, completed, priority, tags
        case dueDate = "due_date"
    }

    init(id: Int, title: String, list: String, completed: Int,
         priority: String, dueDate: String, tags: [String] = []) {
        self.id = id; self.title = title; self.list = list
        self.completed = completed; self.priority = priority
        self.dueDate = dueDate; self.tags = tags
    }

    // Tolerant decode: older cached JSON (and older servers) have no `tags`.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id        = try c.decode(Int.self,    forKey: .id)
        title     = try c.decode(String.self, forKey: .title)
        list      = try c.decode(String.self, forKey: .list)
        completed = try c.decode(Int.self,    forKey: .completed)
        priority  = try c.decodeIfPresent(String.self, forKey: .priority) ?? "none"
        dueDate   = try c.decodeIfPresent(String.self, forKey: .dueDate)  ?? ""
        tags      = try c.decodeIfPresent([String].self, forKey: .tags)   ?? []
    }

    var isDone: Bool { completed != 0 }

    func hasTag(_ name: String) -> Bool {
        tags.contains { $0.caseInsensitiveCompare(name) == .orderedSame }
    }
}

/// A tag in the shared palette (server table `todo_tags`).
struct TodoTag: Identifiable, Codable, Equatable, Hashable {
    let name: String
    var color: String
    var builtin: Int

    var id: String { name }

    enum CodingKeys: String, CodingKey { case name, color, builtin }

    init(name: String, color: String = "", builtin: Int = 0) {
        self.name = name; self.color = color; self.builtin = builtin
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name    = try c.decode(String.self, forKey: .name)
        color   = try c.decodeIfPresent(String.self, forKey: .color) ?? ""
        builtin = try c.decodeIfPresent(Int.self, forKey: .builtin) ?? 0
    }

    /// Fallback palette so tags still look distinct when the server sends no color.
    static let defaultPalette: [String: String] = [
        "coursework": "#7c6ff0", "groceries": "#3fb27f", "errands": "#e0a020",
        "work": "#4a9edd", "personal": "#e0608a",
    ]

    var hexColor: String {
        if !color.isEmpty { return color }
        if let c = Self.defaultPalette[name.lowercased()] { return c }
        // Deterministic hue from the name so custom tags get a stable color.
        let h = name.unicodeScalars.reduce(0) { ($0 &* 31 &+ Int($1.value)) & 0xffff }
        let hue = Double(h % 360) / 360.0
        return UIColor(hue: hue, saturation: 0.55, brightness: 0.8, alpha: 1).hexString
    }
}

extension UIColor {
    var hexString: String {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        getRed(&r, green: &g, blue: &b, alpha: &a)
        return String(format: "#%02x%02x%02x", Int(r * 255), Int(g * 255), Int(b * 255))
    }
}

struct VoiceResponse: Codable {
    let message: String
    let actions: [String]
    let refresh: String
    let parse: String           // "rule" | "hybrid" | "llm" | "error"
    let verifyToken: String?    // present only for "rule" responses; poll /voice/verify/<token>
    // Added with the vocabulary / thinking-trace work. All optional so older
    // servers (and the empty-transcript reply) still decode.
    let transcript: String?          // after stop-word strip + vocab auto-correct
    let originalTranscript: String?  // raw Whisper output
    let corrections: [VocabCorrection]?
    let trace: [TraceStep]?
    let memoryId: Int?               // row in the command memory (for feedback)
    let pendingId: Int?              // set when the command was queued (LLM offline/slow)
    let uncertainWords: [UncertainWord]?

    enum CodingKeys: String, CodingKey {
        case message, actions, refresh, parse, transcript, corrections, trace
        case verifyToken = "verify_token"
        case originalTranscript = "original_transcript"
        case memoryId = "memory_id"
        case pendingId = "pending_id"
        case uncertainWords = "uncertain_words"
    }
}

/// A word the assistant isn't sure about — near-miss of a vocab word, or an
/// unknown capitalised token that's probably a name.
struct UncertainWord: Codable, Identifiable, Equatable {
    var id: String { heard }
    let heard: String
    let candidate: String?
    let score: Double
    let reason: String   // "near-miss" | "unknown-name"
}

/// One stage of the assistant's "thinking" — streamed live from POST /voice/stream
/// and also returned in full as `VoiceResponse.trace`.
struct TraceStep: Codable, Identifiable, Equatable {
    var id: String { "\(atMs)-\(stage)-\(title)" }
    let stage: String     // stt | vocab | rule | memory | llm | validate | execute | verify | done | error
    let title: String
    let detail: String
    let ms: Int
    let atMs: Int
    let ok: Bool

    enum CodingKeys: String, CodingKey {
        case stage, title, detail, ms, ok
        case atMs = "at_ms"
    }

    static func == (a: TraceStep, b: TraceStep) -> Bool { a.id == b.id && a.detail == b.detail }
}

struct VocabCorrection: Codable, Identifiable, Equatable {
    var id: String { from + "→" + to }
    let from: String
    let to: String
    let reason: String    // "alias" | "fuzzy"
    let score: Double
}

struct VocabWord: Codable, Identifiable, Equatable {
    var id: String { word }
    let word: String
    let aliases: [String]
    let hits: Int
}

struct VocabRecent: Codable, Identifiable {
    var id: Double { ts }
    let ts: Double
    let source: String
    let original: String
    let corrected: String
    let corrections: [VocabCorrection]
}

struct VocabState: Codable {
    let autoCorrect: Bool
    let learnAliases: Bool
    let threshold: Double
    let onboarded: Bool?
    let words: [VocabWord]
    let recent: [VocabRecent]

    enum CodingKeys: String, CodingKey {
        case words, recent, threshold, onboarded
        case autoCorrect = "auto_correct"
        case learnAliases = "learn_aliases"
    }
}

struct VocabQuestion: Codable, Identifiable {
    let id: String
    let question: String
    let hint: String
    let examples: [String]
}

struct VocabPreset: Codable, Identifiable {
    let id: String
    let label: String
    let words: [String]
    let already: Int
}

struct VocabOnboarding: Codable {
    let done: Bool
    let questions: [VocabQuestion]
    let presets: [VocabPreset]
    let wordCount: Int
    enum CodingKeys: String, CodingKey {
        case done, questions, presets
        case wordCount = "word_count"
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

/// A vocabulary candidate mined from text / contacts / calendar (POST /vocab/import).
struct VocabCandidate: Codable, Identifiable {
    var id: String { word }
    let word: String
    let count: Int
    let reason: String   // sender | contact | name | hebrew | non-english
    let sample: String
}

struct VocabImportResult: Codable { let candidates: [VocabCandidate] }

extension AnyCodable {
    var stringValue: String? {
        if let s = value as? String { return s }
        if let i = value as? Int { return String(i) }
        if let d = value as? Double { return String(d) }
        return nil
    }
    var arrayValue: [AnyCodable]? {
        if let a = value as? [String] { return a.map { AnyCodable($0) } }
        if let a = value as? [AnyCodable] { return a }
        return nil
    }
}

/// One executed action inside a remembered command (GET /memory, /memory/unreviewed).
struct MemoryAction: Codable {
    let action: String
    let parameters: [String: AnyCodable]
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        action = try c.decode(String.self, forKey: .action)
        parameters = (try? c.decode([String: AnyCodable].self, forKey: .parameters)) ?? [:]
    }
    enum CodingKeys: String, CodingKey { case action, parameters }
}

/// A remembered voice command from the Mac's command memory.
struct MemoryExample: Codable, Identifiable {
    let id: Int
    let ts: Double
    let time: String
    let source: String
    let transcript: String
    let parsePath: String
    let actions: [MemoryAction]
    let result: String
    let feedback: String
    var resolved: [ResolvedRecord]? = nil
    enum CodingKeys: String, CodingKey {
        case id, ts, time, source, transcript, actions, result, feedback, resolved
        case parsePath = "parse_path"
    }
}

struct UnreviewedResponse: Codable { let examples: [MemoryExample]; let count: Int }

/// What a voice command actually put in the calendar (server joins example → record).
struct ResolvedRecord: Codable, Equatable {
    let type: String
    let action: String
    let title: String
    let date: String
    let startTime: String
    enum CodingKeys: String, CodingKey { case type, action, title, date; case startTime = "start_time" }
}

import Foundation

// MARK: - Exercise

/// The user's own growing exercise catalog — starts empty, no canned
/// library. Reused via search-or-create autocomplete wherever an exercise
/// is picked (template builder, ad-hoc live session).
struct Exercise: Codable, Identifiable, Equatable, Hashable {
    let id: UUID
    var name: String
    var createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, name
        case createdAt = "created_at"
    }

    init(id: UUID = UUID(), name: String, createdAt: Date = Date()) {
        self.id = id
        self.name = name
        self.createdAt = createdAt
    }
}

// MARK: - Set type

/// Type is per-SET, not per-exercise — one exercise's sets can mix reps
/// and time sets (e.g. a plank exercise logged as 3 timed holds, or a
/// pull-up exercise mixing weighted reps and a max-time hang).
///
/// `.distance` is what makes running fit here. A "5 × 400 m @ 3:50" interval
/// session is one single-exercise block of five distance sets, with the
/// recovery jog as the rest between them — so intervals reuse the whole
/// live-session engine (flatten → current set → rest → log) rather than
/// needing a parallel one.
enum SetType: String, Codable {
    case reps
    case time
    case distance
}

/// A single planned set inside a template's block. `note` is optional
/// free text, e.g. "L-sit hold".
struct SetTemplate: Codable, Identifiable, Equatable {
    let id: UUID
    var type: SetType

    // .reps
    var targetReps: Int?
    var weightKg: Double?     // nil = bodyweight; supports added weight like +10kg

    // .time
    var targetSeconds: Int?

    // .distance — metres, and an optional target pace in seconds per km
    // (nil = "run it by feel", which is what an easy run wants).
    var distanceM: Double?
    var targetPaceSecPerKm: Int?

    var note: String?

    enum CodingKeys: String, CodingKey {
        case id, type, note
        case targetReps = "target_reps"
        case weightKg = "weight_kg"
        case targetSeconds = "target_seconds"
        case distanceM = "distance_m"
        case targetPaceSecPerKm = "target_pace_sec_per_km"
    }

    init(id: UUID = UUID(), type: SetType, targetReps: Int? = nil, weightKg: Double? = nil,
         targetSeconds: Int? = nil, distanceM: Double? = nil, targetPaceSecPerKm: Int? = nil,
         note: String? = nil) {
        self.id = id
        self.type = type
        self.targetReps = targetReps
        self.weightKg = weightKg
        self.targetSeconds = targetSeconds
        self.distanceM = distanceM
        self.targetPaceSecPerKm = targetPaceSecPerKm
        self.note = note
    }

    static func reps(_ n: Int, weightKg: Double? = nil, note: String? = nil) -> SetTemplate {
        SetTemplate(type: .reps, targetReps: n, weightKg: weightKg, note: note)
    }
    static func time(_ seconds: Int, note: String? = nil) -> SetTemplate {
        SetTemplate(type: .time, targetSeconds: seconds, note: note)
    }
    static func distance(_ metres: Double, paceSecPerKm: Int? = nil, note: String? = nil) -> SetTemplate {
        SetTemplate(type: .distance, distanceM: metres, targetPaceSecPerKm: paceSecPerKm, note: note)
    }
}

// MARK: - Block

/// Either a single exercise, or a superset of two exercises alternating
/// A→B as one unit. Kept as one struct (rather than an enum with
/// associated values) so the builder UI can toggle a block between the two
/// shapes without re-modeling; unused fields for the non-active kind are
/// simply left empty.
enum BlockKind: String, Codable {
    case single
    case superset
}

struct Block: Codable, Identifiable, Equatable {
    let id: UUID
    var kind: BlockKind

    // .single
    var exerciseId: UUID?
    var sets: [SetTemplate]
    var restBetweenSetsOverride: Int?   // falls back to template default

    // .superset — same set count on both sides = number of rounds; A and B
    // alternate one set each per round. Rest only happens after a full
    // A+B round, not between A and B.
    var exerciseIdA: UUID?
    var exerciseIdB: UUID?
    var setsA: [SetTemplate]
    var setsB: [SetTemplate]
    var restAfterRound: Int?

    enum CodingKeys: String, CodingKey {
        case id, kind, sets
        case exerciseId = "exercise_id"
        case restBetweenSetsOverride = "rest_between_sets_override"
        case exerciseIdA = "exercise_id_a"
        case exerciseIdB = "exercise_id_b"
        case setsA = "sets_a"
        case setsB = "sets_b"
        case restAfterRound = "rest_after_round"
    }

    static func single(exerciseId: UUID, sets: [SetTemplate] = [], restBetweenSetsOverride: Int? = nil) -> Block {
        Block(id: UUID(), kind: .single, exerciseId: exerciseId, sets: sets,
              restBetweenSetsOverride: restBetweenSetsOverride,
              exerciseIdA: nil, exerciseIdB: nil, setsA: [], setsB: [], restAfterRound: nil)
    }

    static func superset(exerciseIdA: UUID, exerciseIdB: UUID, setsA: [SetTemplate] = [],
                          setsB: [SetTemplate] = [], restAfterRound: Int = 60) -> Block {
        Block(id: UUID(), kind: .superset, exerciseId: nil, sets: [], restBetweenSetsOverride: nil,
              exerciseIdA: exerciseIdA, exerciseIdB: exerciseIdB, setsA: setsA, setsB: setsB,
              restAfterRound: restAfterRound)
    }
}

// MARK: - Template

struct WorkoutTemplate: Codable, Identifiable, Equatable {
    let id: UUID
    var name: String
    var blocks: [Block]
    var defaultRestBetweenSets: Int       // seconds
    var defaultRestBetweenExercises: Int  // seconds
    var createdAt: Date
    // 'draft' | 'saved' (server default when omitted is 'saved'). nil locally
    // means "not yet known / plain saved template" — kept optional rather than
    // defaulted to a literal so old locally-persisted templates (from before
    // this field existed) decode fine with no status key present.
    var status: String?

    enum CodingKeys: String, CodingKey {
        case id, name, blocks, status
        case defaultRestBetweenSets = "default_rest_between_sets"
        case defaultRestBetweenExercises = "default_rest_between_exercises"
        case createdAt = "created_at"
    }

    init(id: UUID = UUID(), name: String, blocks: [Block] = [],
         defaultRestBetweenSets: Int = 90, defaultRestBetweenExercises: Int = 120,
         createdAt: Date = Date(), status: String? = nil) {
        self.id = id
        self.name = name
        self.blocks = blocks
        self.defaultRestBetweenSets = defaultRestBetweenSets
        self.defaultRestBetweenExercises = defaultRestBetweenExercises
        self.createdAt = createdAt
        self.status = status
    }

    /// AI-generated routines land as drafts (status == "draft") and are
    /// excluded from the normal template list until approved.
    var isDraft: Bool { status == "draft" }
}

// MARK: - Session log

struct SetLog: Codable, Identifiable, Equatable {
    let id: UUID
    var exerciseId: UUID
    var setIndex: Int
    var type: SetType
    var actualReps: Int?
    var actualSeconds: Int?
    var actualWeightKg: Double?
    var actualDistanceM: Double?
    var actualPaceSecPerKm: Int?
    var completedAt: Date?
    var skipped: Bool

    enum CodingKeys: String, CodingKey {
        case id, type, skipped
        case exerciseId = "exercise_id"
        case setIndex = "set_index"
        case actualReps = "actual_reps"
        case actualSeconds = "actual_seconds"
        case actualWeightKg = "actual_weight_kg"
        case actualDistanceM = "actual_distance_m"
        case actualPaceSecPerKm = "actual_pace_sec_per_km"
        case completedAt = "completed_at"
    }

    init(id: UUID = UUID(), exerciseId: UUID, setIndex: Int, type: SetType,
         actualReps: Int? = nil, actualSeconds: Int? = nil, actualWeightKg: Double? = nil,
         actualDistanceM: Double? = nil, actualPaceSecPerKm: Int? = nil,
         completedAt: Date? = nil, skipped: Bool = false) {
        self.id = id
        self.exerciseId = exerciseId
        self.setIndex = setIndex
        self.type = type
        self.actualReps = actualReps
        self.actualSeconds = actualSeconds
        self.actualWeightKg = actualWeightKg
        self.actualDistanceM = actualDistanceM
        self.actualPaceSecPerKm = actualPaceSecPerKm
        self.completedAt = completedAt
        self.skipped = skipped
    }
}

struct WorkoutSession: Codable, Identifiable, Equatable {
    let id: UUID
    var templateId: UUID?     // nil = ad-hoc
    var startedAt: Date
    var endedAt: Date?        // nil = in progress
    var notes: String
    var setLogs: [SetLog]

    enum CodingKeys: String, CodingKey {
        case id, notes
        case templateId = "template_id"
        case startedAt = "started_at"
        case endedAt = "ended_at"
        case setLogs = "set_logs"
    }

    init(id: UUID = UUID(), templateId: UUID? = nil, startedAt: Date = Date(),
         endedAt: Date? = nil, notes: String = "", setLogs: [SetLog] = []) {
        self.id = id
        self.templateId = templateId
        self.startedAt = startedAt
        self.endedAt = endedAt
        self.notes = notes
        self.setLogs = setLogs
    }
}

// MARK: - Live session (flattened plan + resumable state)

/// One set in the flattened, linear plan a live session walks through.
/// Templates (with their blocks/supersets) are flattened into this shape
/// at session start so the live-session engine only ever has to deal with
/// "what's the current set / what's next" — it never has to re-reason
/// about block/superset structure while the workout is running.
struct PlannedSet: Codable, Identifiable, Equatable {
    let id: UUID
    var exerciseId: UUID
    var setIndex: Int          // 0-based index of this set within its exercise, for this session
    var type: SetType
    var targetReps: Int?
    var targetWeightKg: Double?
    var targetSeconds: Int?
    var targetDistanceM: Double?
    var targetPaceSecPerKm: Int?
    var note: String?
    var restAfterSeconds: Int      // rest to take after completing this set (0 = none)
    var startsNewExercise: Bool    // true if this is the first planned set of a new exercise

    init(id: UUID = UUID(), exerciseId: UUID, setIndex: Int, type: SetType,
         targetReps: Int? = nil, targetWeightKg: Double? = nil, targetSeconds: Int? = nil,
         targetDistanceM: Double? = nil, targetPaceSecPerKm: Int? = nil,
         note: String? = nil, restAfterSeconds: Int = 0, startsNewExercise: Bool = false) {
        self.id = id
        self.exerciseId = exerciseId
        self.setIndex = setIndex
        self.type = type
        self.targetReps = targetReps
        self.targetWeightKg = targetWeightKg
        self.targetSeconds = targetSeconds
        self.targetDistanceM = targetDistanceM
        self.targetPaceSecPerKm = targetPaceSecPerKm
        self.note = note
        self.restAfterSeconds = restAfterSeconds
        self.startsNewExercise = startsNewExercise
    }
}

/// Persisted in-progress session state. Written to disk on every mutation
/// so the app can be killed or backgrounded mid-session or mid-rest and
/// resume exactly where it left off. `restDeadline` is an absolute Date,
/// never a running countdown, so it survives the process dying.
struct LiveSessionState: Codable, Equatable {
    var session: WorkoutSession
    var plannedSets: [PlannedSet]
    var currentIndex: Int          // index into plannedSets of the set that's current/up-next
    var isResting: Bool
    var restDeadline: Date?
    var restDurationSeconds: Int
    var pendingNotificationId: String?

    var currentPlanned: PlannedSet? {
        guard currentIndex >= 0, currentIndex < plannedSets.count else { return nil }
        return plannedSets[currentIndex]
    }
    var nextPlanned: PlannedSet? {
        let i = currentIndex + 1
        guard i >= 0, i < plannedSets.count else { return nil }
        return plannedSets[i]
    }
    var isFinished: Bool { currentIndex >= plannedSets.count }
}

// MARK: - Running display

extension Double {
    /// Metres as a runner reads them: "400 m" under a kilometre, "12.5 km" over.
    var formattedDistance: String {
        if self < 1000 { return "\(Int(self.rounded())) m" }
        let km = self / 1000
        return km.truncatingRemainder(dividingBy: 1) == 0
            ? String(format: "%.0f km", km)
            : String(format: "%.1f km", km)
    }
}

extension Int {
    /// Seconds per km as "4:35". Pace is never read as a decimal.
    var formattedPace: String {
        String(format: "%d:%02d", self / 60, self % 60)
    }
}

// MARK: - Server sync coding

/// The backend stores workout timestamps as naive local `datetime.isoformat()`
/// strings (e.g. "2026-08-19T13:45:30.123", no timezone suffix — see
/// assistant/db.py) and never reparses/reformats them, just round-trips the
/// TEXT column verbatim (including for `ORDER BY started_at DESC` sorting on
/// GET /workout/sessions, which relies on the string being lexicographically
/// sortable — i.e. always the same fixed width). This formatter is used only
/// for the network layer; on-disk local persistence keeps using the default
/// JSONEncoder/JSONDecoder (which encodes Date as a Double) unchanged.
extension DateFormatter {
    static let workoutTimestamp: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS"
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone.current   // naive local time, matching the Mac backend's convention
        return f
    }()
}

extension JSONEncoder {
    static let workout: JSONEncoder = {
        let e = JSONEncoder()
        e.dateEncodingStrategy = .formatted(.workoutTimestamp)
        return e
    }()
}

extension JSONDecoder {
    static let workout: JSONDecoder = {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .formatted(.workoutTimestamp)
        return d
    }()
}

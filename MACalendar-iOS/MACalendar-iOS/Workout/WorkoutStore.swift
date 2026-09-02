import Foundation
@preconcurrency import UserNotifications
import UIKit

/// Local-only JSON-file persistence for the Workout domain — a separate
/// store from `LocalStore`/`CourseStore` since it's a distinct local-only
/// domain (no backend/API sync at all), but follows the exact same shape:
/// `@MainActor` singleton, `Codable` model structs, `load()`/`persist()`
/// pairs against files in the app's documents directory.
@MainActor
class WorkoutStore: ObservableObject {
    static let shared = WorkoutStore()

    @Published private(set) var exercises: [Exercise] = []
    @Published private(set) var templates: [WorkoutTemplate] = []
    @Published private(set) var sessions: [WorkoutSession] = []
    @Published private(set) var liveState: LiveSessionState?

    /// Set once at app start (see ContentView.task) so local mutations below
    /// can immediately attempt to push themselves to the server. Weak since
    /// APIClient is owned by the app root, not by this singleton.
    weak var api: APIClient?
    func configure(api: APIClient) { self.api = api }

    /// AI-generated routines that landed as drafts (see generate_workout_routine)
    /// — excluded from the normal template list until approved.
    var drafts: [WorkoutTemplate] { templates.filter { $0.isDraft } }

    private let dir = FileManager.default
        .urls(for: .documentDirectory, in: .userDomainMask)[0]

    private init() { load() }

    // MARK: - Persistence

    private func url(_ name: String) -> URL { dir.appendingPathComponent(name) }

    private func load() {
        let d = JSONDecoder()
        exercises = (try? d.decode([Exercise].self,       from: Data(contentsOf: url("wo_exercises.json"))))  ?? []
        templates = (try? d.decode([WorkoutTemplate].self, from: Data(contentsOf: url("wo_templates.json")))) ?? []
        sessions  = (try? d.decode([WorkoutSession].self,  from: Data(contentsOf: url("wo_sessions.json"))))  ?? []
        liveState = try? d.decode(LiveSessionState.self,   from: Data(contentsOf: url("wo_live.json")))
    }

    private func persistCatalog() {
        let e = JSONEncoder()
        try? e.encode(exercises).write(to: url("wo_exercises.json"))
        try? e.encode(templates).write(to: url("wo_templates.json"))
    }

    private func persistSessions() {
        let e = JSONEncoder()
        try? e.encode(sessions).write(to: url("wo_sessions.json"))
    }

    /// Called on every mutation of the in-progress session so a kill/resume
    /// (or background/foreground cycle) never loses state.
    private func persistLive() {
        let e = JSONEncoder()
        if let state = liveState {
            try? e.encode(state).write(to: url("wo_live.json"))
        } else {
            try? FileManager.default.removeItem(at: url("wo_live.json"))
        }
    }

    // MARK: - Server cache merge
    //
    // Workout IDs are client-generated UUIDs end-to-end (never remapped, per
    // Phase 1), so unlike LocalStore's events/todos there's no temp-ID
    // concept. The merge rule is simply: take the server's version of
    // everything it returned, plus keep any local item the server didn't
    // return IF it still has a write queued in LocalStore's pending queue
    // (i.e. it was created/edited locally but the sync hasn't landed yet) —
    // otherwise a refresh racing an offline write would silently drop it.

    /// IDs of workout items (under `pathPrefix`) that still have a queued
    /// offline write — found either in the REST path ("/workout/x/<id>" or
    /// "/workout/x/<id>/approve" for PATCH/DELETE) or in the POST body's
    /// "id" field (POST always carries the client-generated id).
    private func idsWithPendingWrites(pathPrefix: String) -> Set<UUID> {
        var ids = Set<UUID>()
        for p in LocalStore.shared.allPending() {
            guard p.path.hasPrefix(pathPrefix) else { continue }
            let rest = p.path.dropFirst(pathPrefix.count)
            let comps = rest.split(separator: "/")
            if let first = comps.first, let uuid = UUID(uuidString: String(first)) {
                ids.insert(uuid)
                continue
            }
            if let data = p.bodyJSON,
               let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let idStr = obj["id"] as? String, let uuid = UUID(uuidString: idStr) {
                ids.insert(uuid)
            }
        }
        return ids
    }

    func cacheExercises(_ fresh: [Exercise]) {
        let pendingIds = idsWithPendingWrites(pathPrefix: "/workout/exercises")
        let freshIds = Set(fresh.map { $0.id })
        let keepLocal = exercises.filter { pendingIds.contains($0.id) && !freshIds.contains($0.id) }
        exercises = fresh + keepLocal
        persistCatalog()
    }

    /// `includeDrafts` reflects what was actually requested from the server —
    /// when false (the common background-refresh case), the response never
    /// contains drafts at all, so any draft already cached locally (from an
    /// earlier `include_drafts=true` fetch, e.g. right after a voice-generated
    /// routine) must be preserved rather than treated as "gone".
    func cacheTemplates(_ fresh: [WorkoutTemplate], includeDrafts: Bool) {
        let pendingIds = idsWithPendingWrites(pathPrefix: "/workout/templates")
        let freshIds = Set(fresh.map { $0.id })
        let keepLocal = templates.filter { existing in
            guard !freshIds.contains(existing.id) else { return false }
            if pendingIds.contains(existing.id) { return true }
            if !includeDrafts && existing.isDraft { return true }
            return false
        }
        templates = fresh + keepLocal
        persistCatalog()
    }

    func cacheSessions(_ fresh: [WorkoutSession]) {
        let pendingIds = idsWithPendingWrites(pathPrefix: "/workout/sessions")
        let freshIds = Set(fresh.map { $0.id })
        let keepLocal = sessions.filter { pendingIds.contains($0.id) && !freshIds.contains($0.id) }
        sessions = fresh + keepLocal
        persistSessions()
    }

    // MARK: - Exercise catalog

    /// Search-or-create: case-insensitive exact match reuses the existing
    /// exercise, otherwise a new one is created and added to the catalog.
    @discardableResult
    func findOrCreateExercise(named rawName: String) -> Exercise {
        let name = rawName.trimmingCharacters(in: .whitespacesAndNewlines)
        if let existing = exercises.first(where: { $0.name.caseInsensitiveCompare(name) == .orderedSame }) {
            return existing
        }
        let e = Exercise(name: name)
        exercises.append(e)
        persistCatalog()
        if let api { Task { await api.syncNewExercise(e) } }
        return e
    }

    func exercise(_ id: UUID) -> Exercise? { exercises.first { $0.id == id } }

    func matchingExercises(_ query: String) -> [Exercise] {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return exercises.sorted { $0.name < $1.name } }
        return exercises
            .filter { $0.name.range(of: q, options: .caseInsensitive) != nil }
            .sorted { $0.name < $1.name }
    }

    // MARK: - Templates

    @discardableResult
    func saveTemplate(_ template: WorkoutTemplate) -> WorkoutTemplate {
        let isNew = !templates.contains { $0.id == template.id }
        if let i = templates.firstIndex(where: { $0.id == template.id }) {
            templates[i] = template
        } else {
            templates.append(template)
        }
        persistCatalog()
        if let api { Task { await api.syncTemplate(template, isNew: isNew) } }
        return template
    }

    func deleteTemplate(_ id: UUID) {
        templates.removeAll { $0.id == id }
        persistCatalog()
        if let api { Task { await api.deleteWorkoutTemplate(id) } }
    }

    /// Finalizes an AI-drafted template (status 'draft' -> 'saved'). Any
    /// edits made in the review sheet should already have been pushed via
    /// `saveTemplate` before calling this — see TemplateBuilderView.approveDraft().
    func approveTemplate(_ id: UUID) {
        guard let i = templates.firstIndex(where: { $0.id == id }) else { return }
        templates[i].status = "saved"
        persistCatalog()
        if let api { Task { await api.approveWorkoutTemplate(id) } }
    }

    // MARK: - Session history

    func deleteSession(_ id: UUID) {
        sessions.removeAll { $0.id == id }
        persistSessions()
        if let api { Task { await api.deleteWorkoutSession(id) } }
    }

    /// Bound directly to per-keystroke/per-tap edits (notes field, set-log
    /// steppers in SessionDetailView), so the network push is debounced
    /// rather than fired on every call — otherwise editing a session offline
    /// would flood LocalStore's pending queue with near-duplicate PATCHes.
    private var sessionSyncTask: Task<Void, Never>?

    func updateSession(_ session: WorkoutSession) {
        guard let i = sessions.firstIndex(where: { $0.id == session.id }) else { return }
        sessions[i] = session
        persistSessions()
        guard let api else { return }
        sessionSyncTask?.cancel()
        sessionSyncTask = Task {
            try? await Task.sleep(nanoseconds: 800_000_000)
            guard !Task.isCancelled else { return }
            await api.syncSession(session, isNew: false)
        }
    }

    func recentSessions(limit: Int = 20) -> [WorkoutSession] {
        sessions.sorted { $0.startedAt > $1.startedAt }.prefix(limit).map { $0 }
    }

    /// Most recently logged (non-skipped) set for an exercise, used to
    /// prefill defaults for ad-hoc sets ("last time this exercise was
    /// logged").
    func lastLoggedSet(for exerciseId: UUID) -> SetLog? {
        let candidates = sessions
            .sorted { $0.startedAt > $1.startedAt }
            .flatMap { $0.setLogs }
            .filter { $0.exerciseId == exerciseId && !$0.skipped && $0.completedAt != nil }
        return candidates.sorted { ($0.completedAt ?? .distantPast) > ($1.completedAt ?? .distantPast) }.first
    }

    // MARK: - Flattening a template into a linear plan

    /// Flattens a template's blocks (including supersets) into an ordered
    /// list of individual sets. Doing this once at session start means the
    /// live-session engine never has to re-reason about block/superset
    /// structure — it just walks an array.
    func flatten(_ template: WorkoutTemplate) -> [PlannedSet] {
        var result: [PlannedSet] = []
        let lastBlockIndex = template.blocks.count - 1

        for (blockIdx, block) in template.blocks.enumerated() {
            switch block.kind {
            case .single:
                guard let exId = block.exerciseId, !block.sets.isEmpty else { continue }
                let lastSetIdx = block.sets.count - 1
                for (i, set) in block.sets.enumerated() {
                    let isLastSetOfExercise = i == lastSetIdx
                    let isVeryLastSet = isLastSetOfExercise && blockIdx == lastBlockIndex
                    let rest = isVeryLastSet ? 0
                        : (isLastSetOfExercise ? template.defaultRestBetweenExercises
                                                : (block.restBetweenSetsOverride ?? template.defaultRestBetweenSets))
                    result.append(PlannedSet(
                        exerciseId: exId, setIndex: i, type: set.type,
                        targetReps: set.targetReps, targetWeightKg: set.weightKg,
                        targetSeconds: set.targetSeconds,
                        targetDistanceM: set.distanceM,
                        targetPaceSecPerKm: set.targetPaceSecPerKm,
                        note: set.note,
                        restAfterSeconds: rest, startsNewExercise: i == 0
                    ))
                }

            case .superset:
                guard let exA = block.exerciseIdA, let exB = block.exerciseIdB else { continue }
                let rounds = min(block.setsA.count, block.setsB.count)
                guard rounds > 0 else { continue }
                let restAfterRound = block.restAfterRound ?? 60
                for r in 0..<rounds {
                    let isLastRound = r == rounds - 1
                    let a = block.setsA[r]
                    result.append(PlannedSet(
                        exerciseId: exA, setIndex: r, type: a.type,
                        targetReps: a.targetReps, targetWeightKg: a.weightKg,
                        targetSeconds: a.targetSeconds,
                        targetDistanceM: a.distanceM,
                        targetPaceSecPerKm: a.targetPaceSecPerKm,
                        note: a.note,
                        restAfterSeconds: 0, startsNewExercise: r == 0
                    ))
                    let b = block.setsB[r]
                    let isVeryLastSet = isLastRound && blockIdx == lastBlockIndex
                    result.append(PlannedSet(
                        exerciseId: exB, setIndex: r, type: b.type,
                        targetReps: b.targetReps, targetWeightKg: b.weightKg,
                        targetSeconds: b.targetSeconds,
                        targetDistanceM: b.distanceM,
                        targetPaceSecPerKm: b.targetPaceSecPerKm,
                        note: b.note,
                        restAfterSeconds: isVeryLastSet ? 0 : restAfterRound,
                        startsNewExercise: r == 0
                    ))
                }
            }
        }
        return result
    }

    // MARK: - Live session engine

    func startSession(template: WorkoutTemplate?) {
        let plan = template.map(flatten) ?? []
        let session = WorkoutSession(templateId: template?.id)
        liveState = LiveSessionState(
            session: session, plannedSets: plan, currentIndex: 0,
            isResting: false, restDeadline: nil, restDurationSeconds: 0,
            pendingNotificationId: nil
        )
        persistLive()
    }

    /// For ad-hoc sessions (and "add another exercise" mid-session):
    /// appends a new exercise's sets to the end of the plan.
    func addExercise(_ exerciseId: UUID, sets: [SetTemplate], restBetweenSets: Int, restBeforeNext: Int = 90) {
        guard var state = liveState else { return }
        let lastIdx = sets.count - 1
        var appended: [PlannedSet] = []
        for (i, set) in sets.enumerated() {
            let isLast = i == lastIdx
            appended.append(PlannedSet(
                exerciseId: exerciseId, setIndex: i, type: set.type,
                targetReps: set.targetReps, targetWeightKg: set.weightKg,
                targetSeconds: set.targetSeconds,
                targetDistanceM: set.distanceM,
                targetPaceSecPerKm: set.targetPaceSecPerKm,
                note: set.note,
                restAfterSeconds: isLast ? 0 : restBetweenSets, startsNewExercise: i == 0
            ))
        }
        // The set that *used to be* last-of-session now needs its rest
        // filled in (it previously had 0 because nothing followed it).
        if state.plannedSets.indices.contains(state.plannedSets.count - 1) {
            let lastExisting = state.plannedSets.count - 1
            if lastExisting >= state.currentIndex, state.plannedSets[lastExisting].restAfterSeconds == 0 {
                state.plannedSets[lastExisting].restAfterSeconds = restBeforeNext
            }
        }
        state.plannedSets.append(contentsOf: appended)
        liveState = state
        persistLive()
    }

    /// Duplicates the given planned set as a new one inserted right after
    /// it — "+ Add Set" for the current exercise.
    func addSet(after plannedId: UUID) {
        guard var state = liveState,
              let idx = state.plannedSets.firstIndex(where: { $0.id == plannedId }) else { return }
        let template = state.plannedSets[idx]
        var copy = template
        // Give it a fresh identity and the next set-index for this exercise.
        let existingCount = state.plannedSets.filter { $0.exerciseId == template.exerciseId }.count
        copy = PlannedSet(
            exerciseId: template.exerciseId, setIndex: existingCount, type: template.type,
            targetReps: template.targetReps, targetWeightKg: template.targetWeightKg,
            targetSeconds: template.targetSeconds,
            targetDistanceM: template.targetDistanceM,
            targetPaceSecPerKm: template.targetPaceSecPerKm,
            note: template.note,
            restAfterSeconds: template.restAfterSeconds, startsNewExercise: false
        )
        // The now-earlier set no longer ends its exercise, so it should
        // rest like a between-set rest rather than whatever it had.
        state.plannedSets.insert(copy, at: idx + 1)
        liveState = state
        persistLive()
    }

    /// Reorders the *upcoming* (not-yet-performed) planned sets.
    func reorderUpcoming(from source: IndexSet, to destination: Int) {
        guard var state = liveState else { return }
        let start = state.currentIndex
        guard start < state.plannedSets.count else { return }
        var upcoming = Array(state.plannedSets[start...])
        upcoming.move(fromOffsets: source, toOffset: destination)
        state.plannedSets.replaceSubrange(start..., with: upcoming)
        liveState = state
        persistLive()
    }

    /// Updates the target values of the current (or a specific) planned
    /// set — inline overrides from the "THEN, AUTOMATICALLY" strip or the
    /// current-set steppers. `nil` for reps/seconds means "leave as-is";
    /// weight has its own setter below since `nil` is itself a meaningful
    /// value there (bodyweight), so it can't share that convention.
    func updatePlannedSet(_ id: UUID, reps: Int? = nil, seconds: Int? = nil,
                          distanceM: Double? = nil, paceSecPerKm: Int? = nil) {
        guard var state = liveState, let idx = state.plannedSets.firstIndex(where: { $0.id == id }) else { return }
        if let reps { state.plannedSets[idx].targetReps = reps }
        if let seconds { state.plannedSets[idx].targetSeconds = seconds }
        if let distanceM { state.plannedSets[idx].targetDistanceM = distanceM }
        if let paceSecPerKm { state.plannedSets[idx].targetPaceSecPerKm = paceSecPerKm }
        liveState = state
        persistLive()
    }

    /// Sets a planned set's target weight. `nil` = bodyweight.
    func updatePlannedWeight(_ id: UUID, weightKg: Double?) {
        guard var state = liveState, let idx = state.plannedSets.firstIndex(where: { $0.id == id }) else { return }
        state.plannedSets[idx].targetWeightKg = weightKg
        liveState = state
        persistLive()
    }

    func updateRestAfter(_ id: UUID, seconds: Int) {
        guard var state = liveState, let idx = state.plannedSets.firstIndex(where: { $0.id == id }) else { return }
        state.plannedSets[idx].restAfterSeconds = max(0, seconds)
        liveState = state
        persistLive()
    }

    /// Logs the current set as complete (or skipped) and either starts the
    /// rest countdown or advances immediately if no rest follows.
    func completeCurrentSet(actualReps: Int? = nil, actualWeightKg: Double? = nil,
                             actualSeconds: Int? = nil, actualDistanceM: Double? = nil,
                             actualPaceSecPerKm: Int? = nil, skipped: Bool = false) {
        guard var state = liveState, let planned = state.currentPlanned else { return }

        let log = SetLog(
            exerciseId: planned.exerciseId, setIndex: planned.setIndex, type: planned.type,
            actualReps: skipped ? nil : (actualReps ?? planned.targetReps),
            actualSeconds: skipped ? nil : (actualSeconds ?? planned.targetSeconds),
            actualWeightKg: skipped ? nil : (actualWeightKg ?? planned.targetWeightKg),
            actualDistanceM: skipped ? nil : (actualDistanceM ?? planned.targetDistanceM),
            actualPaceSecPerKm: skipped ? nil : (actualPaceSecPerKm ?? planned.targetPaceSecPerKm),
            completedAt: skipped ? nil : Date(), skipped: skipped
        )
        state.session.setLogs.append(log)

        let hasNext = (state.currentIndex + 1) < state.plannedSets.count
        state.currentIndex += 1

        if !skipped, planned.restAfterSeconds > 0, hasNext {
            let deadline = Date().addingTimeInterval(TimeInterval(planned.restAfterSeconds))
            state.isResting = true
            state.restDeadline = deadline
            state.restDurationSeconds = planned.restAfterSeconds
            liveState = state
            persistLive()
            scheduleRestNotification(deadline: deadline)
        } else {
            state.isResting = false
            state.restDeadline = nil
            state.restDurationSeconds = 0
            liveState = state
            persistLive()
            cancelRestNotification()
        }
    }

    func skipCurrentSet() {
        completeCurrentSet(skipped: true)
    }

    func adjustRest(bySeconds delta: Int) {
        guard var state = liveState, state.isResting, let deadline = state.restDeadline else { return }
        let newDeadline = max(Date(), deadline.addingTimeInterval(TimeInterval(delta)))
        state.restDeadline = newDeadline
        liveState = state
        persistLive()
        scheduleRestNotification(deadline: newDeadline)
    }

    func skipRest() {
        guard var state = liveState else { return }
        state.isResting = false
        state.restDeadline = nil
        state.restDurationSeconds = 0
        liveState = state
        persistLive()
        cancelRestNotification()
    }

    /// Checked on appear / foreground / tick: flips isResting off once the
    /// stored deadline has passed. Rest time itself is always computed from
    /// this absolute Date, never a live-counting Timer.
    func endRestIfDue() {
        guard var state = liveState, state.isResting, let deadline = state.restDeadline else { return }
        guard Date() >= deadline else { return }
        state.isResting = false
        state.restDeadline = nil
        state.restDurationSeconds = 0
        liveState = state
        persistLive()
    }

    func finishSession(notes: String = "") {
        guard var state = liveState else { return }
        state.session.notes = notes
        state.session.endedAt = Date()
        let finished = state.session
        sessions.append(finished)
        persistSessions()
        liveState = nil
        persistLive()
        cancelRestNotification()
        if let api { Task { await api.syncSession(finished, isNew: true) } }
    }

    func discardSession() {
        liveState = nil
        persistLive()
        cancelRestNotification()
    }

    // MARK: - Rest-end notifications

    private func requestNotificationPermissionIfNeeded() {
        let center = UNUserNotificationCenter.current()
        center.getNotificationSettings { settings in
            guard settings.authorizationStatus == .notDetermined else { return }
            center.requestAuthorization(options: [.alert, .sound]) { _, _ in }
        }
    }

    private func scheduleRestNotification(deadline: Date) {
        requestNotificationPermissionIfNeeded()
        cancelRestNotification()

        let content = UNMutableNotificationContent()
        content.title = "Rest over"
        content.body = "Time for your next set."
        content.sound = .default

        let interval = max(1, deadline.timeIntervalSinceNow)
        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: interval, repeats: false)
        let id = UUID().uuidString
        let request = UNNotificationRequest(identifier: id, content: content, trigger: trigger)
        UNUserNotificationCenter.current().add(request)

        liveState?.pendingNotificationId = id
        persistLive()
    }

    private func cancelRestNotification() {
        if let id = liveState?.pendingNotificationId {
            UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: [id])
        }
        liveState?.pendingNotificationId = nil
    }

    /// Haptic feedback for when the app is foregrounded right as (or after)
    /// rest ends — the notification covers the backgrounded/locked case.
    func fireRestEndedHapticIfNeeded() {
        guard let state = liveState, state.isResting, let deadline = state.restDeadline, Date() >= deadline else { return }
        UINotificationFeedbackGenerator().notificationOccurred(.success)
    }

    // MARK: - Stats helpers

    func filteredSessions(in range: ClosedRange<Date>) -> [WorkoutSession] {
        sessions.filter { $0.startedAt >= range.lowerBound && $0.startedAt <= range.upperBound && $0.endedAt != nil }
    }
}

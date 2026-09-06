import Foundation
import ActivityKit
import os

/// Drives the "Up Next" Live Activity — the persistent lock-screen card that
/// shows the next upcoming event and flips to "Now" once it starts.
///
/// **Why this can exist in a strictly local-only app.** Live Activities are
/// normally kept alive by APNs push, which this project will never use. The
/// trick is that the only thing changing second-by-second — the countdown — is
/// drawn by the *system*: `Text(timerInterval:)` and `ProgressView(timerInterval:)`
/// re-render on the lock screen with zero updates from us. The app therefore
/// only has to push content when the *event* changes (next → now → the one
/// after), and that is a handful of updates a day.
///
/// **The cost of no push.** Those handful of updates can only happen when iOS
/// gives the app execution time: foregrounding, and the poll paths that already
/// run while it is open. A card whose event started while the phone was locked
/// therefore keeps saying "in 0:00" until the app next wakes — so every card
/// carries a `staleDate` (`ContentState.staleDate`) at exactly the moment it
/// stops being true, and iOS dims it rather than letting it lie.
///
/// Same inputs as `ReminderScheduler`: the `LocalStore` event cache and the
/// device-local `remindersEnabled` toggle. It re-derives nothing about
/// reminder policy — this card is about what is *next*, not about what rings.
@MainActor
final class LiveActivityManager {
    static let shared = LiveActivityManager()

    /// Live Activities are hard-capped at 8 hours by iOS, so there is no point
    /// starting one for an event further out than that.
    static let horizon: TimeInterval = 8 * 3600

    /// Assumed length of an event with no end time — enough for the "Now"
    /// phase to have a sensible bar and a sensible `staleDate`.
    static let assumedDuration: TimeInterval = 3600

    private var pendingSync: Task<Void, Never>? = nil

    private let log = Logger(subsystem: "com.macalendar.app", category: "LiveActivity")

    private init() {}

    // MARK: - Entry point

    /// The single entry point, called from every place the app already wakes:
    /// `ContentView`'s foreground handler, its `/changes` poll branch and its
    /// 30 s tick, and `ReminderScheduler.reconcile()` (which covers every
    /// cache write). Idempotent, cheap and debounced 300 ms so the bursty
    /// paths collapse into one pass, exactly like `reconcile()`.
    func sync() {
        pendingSync?.cancel()
        pendingSync = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 300_000_000)
            guard !Task.isCancelled else { return }
            await self?.performSync()
        }
    }

    private func performSync() async {
        // Everything below is 16.2 API (`ActivityContent`, `staleDate`, the
        // request/update overloads that take it). Older phones simply never
        // get a card; nothing else in the app notices.
        guard #available(iOS 16.2, *) else { return }
        await syncActivity()
    }

    // MARK: - The work

    @available(iOS 16.2, *)
    private func syncActivity() async {
        // The user can switch Live Activities off for the app in Settings, and
        // the app has its own reminders switch. Either one off means no card —
        // and any card already up is ended, not left orphaned.
        guard ActivityAuthorizationInfo().areActivitiesEnabled else {
            await endAll(reason: "Live Activities disabled for this app")
            return
        }
        guard ReminderScheduler.isEnabled else {
            await endAll(reason: "reminders toggle is off")
            return
        }

        guard let state = Self.currentCard(now: Date(),
                                           events: LocalStore.shared.allEvents(),
                                           accentHex: Self.accentHex) else {
            await endAll(reason: "nothing running and nothing starting within 8 h")
            return
        }

        let content = ActivityContent(state: state, staleDate: state.staleDate)
        let live = Activity<UpNextAttributes>.activities

        // Belt and braces: only one "Up Next" card is ever meaningful. If a
        // crash or a reinstall left more than one behind, keep the first and
        // end the strays.
        if live.count > 1 {
            for extra in live.dropFirst() {
                await extra.end(nil, dismissalPolicy: .immediate)
            }
            log.notice("ended \(live.count - 1) stray Up Next activities")
        }

        if let activity = live.first {
            guard !Self.sameCard(activity.content.state, state) else { return }
            await activity.update(content)
            log.notice("""
                updated Up Next → \(state.phase.rawValue, privacy: .public) \
                event #\(state.eventId, privacy: .public) \
                (stale at \(state.staleDate, privacy: .public))
                """)
            print("[LiveActivity] updated → \(state.phase.rawValue) event #\(state.eventId)")
        } else {
            do {
                let activity = try Activity.request(
                    attributes: UpNextAttributes(),
                    content: content,
                    pushType: nil            // local-only: never APNs
                )
                // "Started" is precisely this: the API returned an Activity
                // instead of throwing. Logged so a device run can be verified
                // without seeing the lock screen.
                log.notice("""
                    STARTED Up Next id=\(activity.id, privacy: .public) \
                    phase=\(state.phase.rawValue, privacy: .public) \
                    event #\(state.eventId, privacy: .public) \
                    starts \(state.start, privacy: .public)
                    """)
                print("[LiveActivity] STARTED id=\(activity.id) phase=\(state.phase.rawValue) "
                      + "event #\(state.eventId) \"\(state.title)\" at \(state.timeLabel)")
            } catch {
                log.error("Up Next request failed: \(error.localizedDescription, privacy: .public)")
                print("[LiveActivity] request FAILED: \(error)")
            }
        }
    }

    @available(iOS 16.2, *)
    private func endAll(reason: String) async {
        let live = Activity<UpNextAttributes>.activities
        guard !live.isEmpty else { return }
        for activity in live {
            await activity.end(nil, dismissalPolicy: .immediate)
        }
        log.notice("ended \(live.count) Up Next activities: \(reason, privacy: .public)")
        print("[LiveActivity] ended \(live.count): \(reason)")
    }

    // MARK: - Choosing what the card shows

    /// The event currently running, or failing that the soonest one starting
    /// within the 8-hour horizon. Pure and static so it can be reasoned about
    /// (and tested) without ActivityKit or a device.
    ///
    /// An in-progress event wins over an upcoming one: a card that says
    /// "Now: Standup" while standup is happening is the whole point of the
    /// "then flips to the next one" behaviour.
    @available(iOS 16.1, *)
    static func currentCard(now: Date,
                            events: [CalendarEvent],
                            accentHex: String) -> UpNextAttributes.ContentState? {
        struct Slot { let event: CalendarEvent; let start: Date; let end: Date }

        let slots: [Slot] = events.compactMap { e in
            // An all-day / timeless row has nothing to count down to.
            guard !e.startTime.isEmpty,
                  let start = ReminderScheduler.parseLocal("\(e.date)T\(e.startTime)")
            else { return nil }
            var end = (e.endTime.isEmpty ? nil : ReminderScheduler.parseLocal("\(e.date)T\(e.endTime)"))
                ?? start.addingTimeInterval(assumedDuration)
            // "23:00 – 01:00" parses both ends onto the same day; the end
            // belongs to the next one. Without this the event looks like it
            // ended 22 hours before it began.
            if end <= start { end = end.addingTimeInterval(86_400) }
            return Slot(event: e, start: start, end: end)
        }
        .sorted { $0.start < $1.start }

        let running = slots.last { $0.start <= now && now < $0.end }
        let next    = slots.first { $0.start > now && $0.start <= now.addingTimeInterval(horizon) }

        guard let slot = running ?? next else { return nil }
        let e = slot.event
        return UpNextAttributes.ContentState(
            eventId: e.id,
            title: e.title.isEmpty ? "Untitled event" : e.title,
            start: slot.start,
            end: slot.end,
            timeLabel: e.displayTime,
            location: e.location,
            colorHex: e.color.isEmpty ? accentHex : e.color,
            phase: running != nil ? .now : .upcoming,
            issued: now
        )
    }

    /// Does this card show the same thing as that one? `issued` is excluded on
    /// purpose — it moves on every sync, and comparing it would turn every
    /// 30-second tick into an ActivityKit update for no visible change (and
    /// would restart the progress bar's span each time).
    @available(iOS 16.1, *)
    static func sameCard(_ a: UpNextAttributes.ContentState,
                         _ b: UpNextAttributes.ContentState) -> Bool {
        a.eventId == b.eventId && a.phase == b.phase && a.title == b.title
            && a.start == b.start && a.end == b.end
            && a.timeLabel == b.timeLabel && a.location == b.location
            && a.colorHex == b.colorHex
    }

    /// The accent the calendar itself falls back to for an event with no
    /// category colour. Read straight from UserDefaults, the same way
    /// `ReminderScheduler.isEnabled` does, so no AppSettings instance is needed.
    private static var accentHex: String {
        UserDefaults.standard.string(forKey: "accentColorHex") ?? Theme.defaultAccentHex
    }
}

import Foundation

/// The contract between the app and the `MACalendarWidgets` extension for the
/// **home-screen** widget — the counterpart of `UpNextActivityAttributes`,
/// which serves the Live Activity.
///
/// **This file is compiled into BOTH targets.** Like the activity attributes it
/// must stay dependency-free: Foundation only — no `CalendarEvent`, no
/// `LocalStore`, no `Theme`, no SwiftUI.
///
/// **Why a file and not a shared framework.** A Live Activity is *pushed* the
/// content it draws; a home-screen widget has to go and read it. The widget
/// runs in its own process with its own container, so it cannot see the app's
/// Documents directory at all — the only sanctioned channel between the two is
/// an App Group container, and the payload has to be something both sides can
/// encode. Hence: the app mirrors a small JSON file into the group container
/// on every sync, and the widget's timeline provider reads it.
///
/// **Everything here degrades to nothing.** If the App Group is not yet in the
/// provisioning profile, `containerURL` is nil on both sides: the app's mirror
/// is a no-op and the widget draws its "open the app" placeholder. Nothing
/// throws, and no other part of the app notices.
enum WidgetBridge {
    /// Must match the `com.apple.security.application-groups` entry in BOTH
    /// targets' entitlements files.
    static let appGroup = "group.com.macalendar.app"

    /// The `kind` string tying `UpNextHomeWidget`'s configuration to the
    /// `WidgetCenter.reloadTimelines(ofKind:)` the app calls after a sync.
    static let homeWidgetKind = "UpNextHomeWidget"

    private static let snapshotFile = "widget_snapshot.json"

    /// The shared container, or nil when the App Group is not available to
    /// this process (no entitlement yet, profile not regenerated, simulator
    /// without the group installed). Nil is a normal, handled state.
    static var containerURL: URL? {
        FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroup)
    }

    static var snapshotURL: URL? {
        containerURL?.appendingPathComponent(snapshotFile)
    }

    /// One encoder/decoder pair, so the two processes never disagree about how
    /// a `Date` is spelled. ISO-8601 rather than the default seconds-since-
    /// reference-date because the file is worth being able to read by eye when
    /// the widget is showing something surprising.
    static func encoder() -> JSONEncoder {
        let e = JSONEncoder()
        e.dateEncodingStrategy = .iso8601
        return e
    }

    static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }
}

/// What the app last knew about the near future, as the widget sees it.
struct WidgetSnapshot: Codable, Equatable {

    /// One timed event, with everything the widget draws already resolved —
    /// the same discipline as `UpNextAttributes.ContentState`: the extension
    /// owns no formatter, no locale knowledge and no colour policy.
    struct Item: Codable, Equatable, Identifiable {
        var id: Int
        var title: String
        /// Absolute start, derived by the app from the event's local
        /// date + time (the phone and the Mac share one timezone).
        var start: Date
        /// Absolute end. Derived as start + 1 h when the event has no end
        /// time, and rolled to the next day when it crosses midnight, so
        /// `start < end` always holds — same rules as the Live Activity.
        var end: Date
        /// "14:05" or "14:05 – 14:35", exactly as the calendar shows it.
        var timeLabel: String
        var location: String
        /// "#RRGGBB" — the event's category colour, or the accent when it has
        /// none. Already resolved by the app.
        var colorHex: String
    }

    /// When the app wrote this. Shown to nobody; used to notice a snapshot so
    /// old that the app cannot have run recently.
    var generated: Date
    /// The user's accent, so an empty widget can still be tinted like the app.
    var accentHex: String
    /// Today's and tomorrow's still-relevant timed events, soonest first.
    var items: [Item]

    /// How many events the app mirrors. A full day of a dozen events fits;
    /// past that the "N more today" count under-reports rather than lying in
    /// the other direction, because the events kept are always the soonest.
    static let maxItems = 12

    /// A snapshot older than this cannot be trusted to still describe "today" —
    /// the app has not run in over a day, so anything it lists has very likely
    /// been and gone.
    static let staleAfter: TimeInterval = 36 * 3600

    var isStale: Bool { Date().timeIntervalSince(generated) > Self.staleAfter }

    /// The item to headline at `date`: the one running now, else the soonest
    /// one still to start. The same rule the Live Activity uses — a card
    /// saying "Now: Standup" while standup is happening is the point.
    func headline(at date: Date) -> Item? {
        items.last { $0.start <= date && date < $0.end }
            ?? items.first { $0.start > date }
    }

    /// Events still to start at `date`, soonest first.
    func upcoming(at date: Date) -> [Item] {
        items.filter { $0.start > date }
    }

    /// How many events remain today at `date`, not counting `excluding` (the
    /// one the widget is already showing). "Today" is the widget's own local
    /// day, so this stays right across a midnight entry.
    func remainingToday(at date: Date, excluding: Item? = nil) -> Int {
        let cal = Calendar.current
        return items.filter {
            $0.id != excluding?.id
                && $0.start > date
                && cal.isDate($0.start, inSameDayAs: date)
        }.count
    }

    /// The moments at which anything the widget draws changes: every start and
    /// every end still ahead, plus the next midnight (which resets "today").
    /// These become the timeline's future-dated entries, which is what lets the
    /// pointer advance with the app never running.
    func changePoints(after date: Date, limit: Int = 30) -> [Date] {
        var moments = Set<Date>()
        for item in items {
            if item.start > date { moments.insert(item.start) }
            if item.end > date { moments.insert(item.end) }
        }
        if let midnight = Calendar.current.nextDate(
            after: date,
            matching: DateComponents(hour: 0, minute: 0, second: 0),
            matchingPolicy: .nextTime) {
            moments.insert(midnight)
        }
        return Array(moments.sorted().prefix(limit))
    }
}

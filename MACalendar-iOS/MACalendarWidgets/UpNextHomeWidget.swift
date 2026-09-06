import SwiftUI
import UIKit
import WidgetKit

/// The home-screen widget: what is next, and how much of today is left.
///
/// **How it differs from the Live Activity next door.** The activity is handed
/// its content by the app and can only change when the app is awake — that is
/// the price of never using push. A widget timeline is the opposite: it is
/// handed to WidgetKit *once*, with entries dated into the future, and the
/// system swaps them in on schedule with nothing of ours running. So this
/// widget's "next event" pointer really does advance at each event's start
/// time on its own; the app only has to refresh the underlying data.
///
/// **Where the data comes from.** The widget runs in its own process and
/// cannot read the app's Documents. `LocalStore` mirrors a small JSON snapshot
/// into the shared App Group container on every sync, and the provider below
/// reads it. When the group is not available — the entitlement has not made it
/// into a profile yet, or the app has never run — there is no file, and the
/// widget says so instead of pretending the day is empty.
struct UpNextHomeWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: WidgetBridge.homeWidgetKind,
                            provider: UpNextTimelineProvider()) { entry in
            UpNextWidgetView(entry: entry)
        }
        .configurationDisplayName("Up Next")
        .description("Your next event and what is left of today.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

// MARK: - Timeline

struct UpNextEntry: TimelineEntry {
    let date: Date
    /// nil when there is no snapshot to read at all (no App Group, or the app
    /// has never synced). Distinct from a snapshot with no items, which means
    /// "the app looked and there is genuinely nothing".
    let snapshot: WidgetSnapshot?
}

struct UpNextTimelineProvider: TimelineProvider {

    func placeholder(in context: Context) -> UpNextEntry {
        UpNextEntry(date: Date(), snapshot: Self.sample)
    }

    func getSnapshot(in context: Context, completion: @escaping (UpNextEntry) -> Void) {
        // The widget gallery previews with `isPreview` and no user data of its
        // own; showing the real day there is better when we have it, and the
        // sample keeps the gallery from advertising an empty widget.
        let real = Self.load()
        let useSample = context.isPreview && (real?.items.isEmpty ?? true)
        completion(UpNextEntry(date: Date(), snapshot: useSample ? Self.sample : real))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<UpNextEntry>) -> Void) {
        let now = Date()
        let snapshot = Self.load()

        // One entry now, then one at every moment something changes — each
        // event's start and end, and the next midnight. This is the whole
        // trick: the pointer moves to the next event at exactly its start
        // time without the app being involved.
        var entries = [UpNextEntry(date: now, snapshot: snapshot)]
        let changes = snapshot?.changePoints(after: now) ?? []
        entries.append(contentsOf: changes.map { UpNextEntry(date: $0, snapshot: snapshot) })

        // Ask for fresh data once the last entry is spent — but never sooner
        // than a quarter hour, so an empty or stale snapshot cannot turn into
        // a reload loop against WidgetKit's budget.
        let floor = now.addingTimeInterval(15 * 60)
        let refresh = max(changes.last ?? floor, floor)
        completion(Timeline(entries: entries, policy: .after(refresh)))
    }

    /// Read the app's mirror. Every failure — no App Group, no file yet, a
    /// half-written file — lands on nil, which the view renders as a
    /// placeholder rather than as an empty day.
    static func load() -> WidgetSnapshot? {
        guard let url = WidgetBridge.snapshotURL,
              let data = try? Data(contentsOf: url),
              let snapshot = try? WidgetBridge.decoder().decode(WidgetSnapshot.self, from: data)
        else { return nil }
        return snapshot
    }

    /// Gallery filler only — never shown over real data.
    static var sample: WidgetSnapshot {
        let now = Date()
        return WidgetSnapshot(
            generated: now,
            accentHex: "#F5A524",
            items: [
                .init(id: -1, title: "Analysis lecture",
                      start: now.addingTimeInterval(2400), end: now.addingTimeInterval(7800),
                      timeLabel: "14:00 – 15:30", location: "Brand 4", colorHex: "#6F68F0"),
                .init(id: -2, title: "Gym",
                      start: now.addingTimeInterval(12_000), end: now.addingTimeInterval(15_600),
                      timeLabel: "17:00 – 18:00", location: "", colorHex: "#2FAE5C"),
                .init(id: -3, title: "Dinner with Mum",
                      start: now.addingTimeInterval(21_600), end: now.addingTimeInterval(25_200),
                      timeLabel: "19:30", location: "", colorHex: "#E0714F"),
            ])
    }
}

// MARK: - Views

struct UpNextWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: UpNextEntry

    var body: some View {
        content
            .widgetSurface()
    }

    @ViewBuilder
    private var content: some View {
        if let snapshot = entry.snapshot {
            switch family {
            case .systemMedium: MediumView(date: entry.date, snapshot: snapshot)
            default:            SmallView(date: entry.date, snapshot: snapshot)
            }
        } else {
            NoDataView()
        }
    }
}

/// Small: the one thing that matters, plus how much is left.
private struct SmallView: View {
    let date: Date
    let snapshot: WidgetSnapshot

    var body: some View {
        let item = snapshot.headline(at: date)
        let accent = Color(activityHex: item?.colorHex ?? snapshot.accentHex)
            ?? Color(activityHex: snapshot.accentHex) ?? .orange
        let running = item.map { $0.start <= date } ?? false

        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                // The category colour as a bar, not a fill: the widget sits on
                // the user's wallpaper, same argument as the lock-screen card.
                Capsule().fill(accent).frame(width: 3, height: 12)
                Text(item == nil ? "TODAY" : (running ? "NOW" : "UP NEXT"))
                    .font(.system(size: 10, weight: .bold))
                    .tracking(0.8)
                    .foregroundStyle(accent)
            }

            Spacer(minLength: 6)

            if let item {
                Text(item.title)
                    .font(.system(size: 16, weight: .semibold))
                    .lineLimit(2)
                    .minimumScaleFactor(0.85)
                Text(timeText(for: item, on: date))
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                    .padding(.top, 2)
            } else {
                Text(snapshot.isStale ? "Not synced" : "Nothing left")
                    .font(.system(size: 16, weight: .semibold))
                Text(snapshot.isStale ? "Open MACalendar" : "Enjoy the evening")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .padding(.top, 2)
            }

            Spacer(minLength: 6)

            Text(Self.moreLabel(snapshot.remainingToday(at: date, excluding: item)))
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }

    /// "N more today" — singular when it is one, and an honest "nothing else"
    /// rather than "0 more" when the day is done.
    static func moreLabel(_ n: Int) -> String {
        switch n {
        case 0:  return "nothing else today"
        case 1:  return "1 more today"
        default: return "\(n) more today"
        }
    }
}

/// Medium: the next few of today, listed.
private struct MediumView: View {
    let date: Date
    let snapshot: WidgetSnapshot

    var body: some View {
        let headline = snapshot.headline(at: date)
        // The one running (or next), then the ones after it — up to three rows.
        var rows: [WidgetSnapshot.Item] = []
        if let headline { rows.append(headline) }
        for item in snapshot.upcoming(at: date) where rows.count < 3 {
            if item.id != headline?.id { rows.append(item) }
        }
        let accent = Color(activityHex: snapshot.accentHex) ?? .orange
        let remaining = snapshot.remainingToday(at: date, excluding: headline)

        return VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline) {
                Text(headline.map { $0.start <= date ? "NOW" : "UP NEXT" } ?? "TODAY")
                    .font(.system(size: 10, weight: .bold))
                    .tracking(0.8)
                    .foregroundStyle(accent)
                Spacer()
                Text(SmallView.moreLabel(remaining))
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(.secondary)
            }
            .padding(.bottom, 6)

            if rows.isEmpty {
                Spacer(minLength: 0)
                Text(snapshot.isStale ? "Open MACalendar to refresh"
                                      : "Nothing left on today's calendar")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(.secondary)
                Spacer(minLength: 0)
            } else {
                VStack(alignment: .leading, spacing: 7) {
                    ForEach(rows) { item in
                        EventRow(item: item, on: date,
                                 isNow: item.id == headline?.id && item.start <= date)
                    }
                }
                Spacer(minLength: 0)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

private struct EventRow: View {
    let item: WidgetSnapshot.Item
    let date: Date
    let isNow: Bool

    init(item: WidgetSnapshot.Item, on date: Date, isNow: Bool) {
        self.item = item
        self.date = date
        self.isNow = isNow
    }

    var body: some View {
        let accent = Color(activityHex: item.colorHex) ?? .orange
        HStack(spacing: 8) {
            Capsule().fill(accent).frame(width: 3, height: 26)
            VStack(alignment: .leading, spacing: 1) {
                Text(item.title)
                    .font(.system(size: 14, weight: isNow ? .semibold : .medium))
                    .lineLimit(1)
                HStack(spacing: 4) {
                    Text(timeText(for: item, on: date))
                    if !item.location.isEmpty {
                        Text("·")
                        Text(item.location).lineLimit(1)
                    }
                }
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
    }
}

/// No snapshot at all — the App Group is not in place, or the app has never
/// run on this device. Says which way round it is instead of showing a
/// convincing-looking empty day.
private struct NoDataView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("MACalendar")
                .font(.system(size: 10, weight: .bold))
                .tracking(0.8)
                .foregroundStyle(.secondary)
            Spacer(minLength: 4)
            Text("No data yet")
                .font(.system(size: 15, weight: .semibold))
            Text("Open the app once to share today's events with the widget.")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

// MARK: - Day marker

/// "15:05 – 16:05", or "Tomorrow · 09:30" when the event is not on the day the
/// entry is being drawn for.
///
/// Worth the few lines: after the last event of the day the headline becomes
/// tomorrow's, and a bare "09:30" at half past nine at night reads as an event
/// that has already been and gone.
private func timeText(for item: WidgetSnapshot.Item, on date: Date) -> String {
    let cal = Calendar.current
    if cal.isDate(item.start, inSameDayAs: date) { return item.timeLabel }
    if let tomorrow = cal.date(byAdding: .day, value: 1, to: date),
       cal.isDate(item.start, inSameDayAs: tomorrow) {
        return "Tomorrow · \(item.timeLabel)"
    }
    return item.timeLabel
}

// MARK: - Chrome

private extension View {
    /// The widget's background and padding.
    ///
    /// iOS 17 made `containerBackground` mandatory: a widget without one is
    /// drawn by the system as an "unsupported" placeholder rather than as your
    /// view. The extension deploys to 16.2, so both paths have to exist.
    @ViewBuilder
    func widgetSurface() -> some View {
        if #available(iOS 17.0, *) {
            self.padding(14)
                .containerBackground(for: .widget) { Color(.systemBackground) }
        } else {
            ZStack {
                Color(.systemBackground)
                self.padding(14)
            }
        }
    }
}

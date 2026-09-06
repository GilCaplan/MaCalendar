import Foundation
import UIKit
@preconcurrency import UserNotifications

/// Mirrors the server's per-event reminder verdicts into pending local
/// notifications — the phone is the RELIABLE ringer (the Mac's banners are
/// best-effort while its calendar stack happens to be up).
///
/// The policy lives on the Mac (assistant/notify.py): every event payload
/// arrives with `notify_at` already computed — lead-time resolution,
/// category mutes and the Shabbat/yom-tov quiet windows all decided there.
/// This class re-derives nothing; it schedules exactly what the cache says,
/// so being offline for a while costs nothing (the verdicts ride in
/// mc_events.json) and a policy change lands on the next sync.
///
/// Coexistence with the workout rest timer: iOS caps pending local
/// notifications at 64 per app, and WorkoutStore schedules its rest-end
/// notification with a bare-UUID identifier (one live at a time — see
/// WorkoutStore.scheduleRestNotification). We therefore (a) schedule at most
/// `maxScheduled` = 55 event reminders, leaving headroom, and (b) only ever
/// remove requests whose identifier starts with "evt-", so the rest timer's
/// are never touched.
@MainActor
final class ReminderScheduler {
    static let shared = ReminderScheduler()

    /// 55 of the 64-notification cap; the rest is headroom for the workout
    /// rest timer and any other transient request.
    nonisolated static let maxScheduled = 55

    /// Identifier prefix for every request this class owns. (nonisolated:
    /// NotificationRouter reads it from the notification-center callback
    /// queue.)
    nonisolated static let idPrefix = "evt-"

    private var pendingReconcile: Task<Void, Never>? = nil

    private init() {}

    /// Device-local master switch (Settings › Reminders). Read straight from
    /// UserDefaults so the scheduler needs no AppSettings instance.
    static var isEnabled: Bool {
        UserDefaults.standard.object(forKey: "remindersEnabled") == nil
            ? true : UserDefaults.standard.bool(forKey: "remindersEnabled")
    }

    /// Re-derive the pending "evt-*" notifications from the event cache.
    /// Idempotent and cheap to call often — every caller after any event
    /// mutation or cache refresh is correct. Debounced 300 ms so the bursty
    /// paths (month load + token poll firing together) do the work once.
    func reconcile() {
        pendingReconcile?.cancel()
        pendingReconcile = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 300_000_000)
            guard !Task.isCancelled else { return }
            await self?.performReconcile()
        }
    }

    private func performReconcile() async {
        // The "Up Next" lock-screen card is derived from the same cache and
        // the same enable flag, so every path that re-derives the reminders
        // should re-derive it too. Placed before the isEnabled guard on
        // purpose: turning reminders off has to END the card, not just stop
        // scheduling. The manager decides for itself whether to start, roll or
        // end, and debounces exactly like this method.
        LiveActivityManager.shared.sync()

        let center = UNUserNotificationCenter.current()

        // Remove everything of ours first (and ONLY ours — the prefix filter
        // is what keeps the workout rest timer's UUID-identified request
        // alive), then rebuild from the cache. Simpler and safer than diffing.
        let pending = await center.pendingNotificationRequests()
        let mine = pending.map(\.identifier).filter { $0.hasPrefix(Self.idPrefix) }
        if !mine.isEmpty {
            center.removePendingNotificationRequests(withIdentifiers: mine)
        }

        guard Self.isEnabled else { return }

        let now = Date()
        let upcoming: [(event: CalendarEvent, fire: Date)] = LocalStore.shared.allEvents()
            .compactMap { e in
                guard let at = e.notifyAt, let fire = Self.parseLocal(at), fire > now
                else { return nil }
                return (e, fire)
            }
            .sorted { $0.fire < $1.fire }

        for (event, fire) in upcoming.prefix(Self.maxScheduled) {
            let content = UNMutableNotificationContent()
            content.title = event.title.isEmpty ? "Upcoming event" : event.title
            content.body = Self.body(for: event, fire: fire)
            content.sound = .default

            let comps = Calendar.current.dateComponents(
                [.year, .month, .day, .hour, .minute], from: fire)
            let trigger = UNCalendarNotificationTrigger(dateMatching: comps, repeats: false)
            let request = UNNotificationRequest(identifier: "\(Self.idPrefix)\(event.id)",
                                                content: content, trigger: trigger)
            // Fire-and-forget, same as the rest timer's add — a failed add
            // just means this one won't ring, and the next reconcile retries.
            try? await center.add(request)
        }
    }

    /// "In 30 min · 15:00 · <location>". The event's own start time is
    /// always included so a stale fire (event since moved, phone long
    /// offline) is self-evident from the banner alone.
    static func body(for event: CalendarEvent, fire: Date) -> String {
        var parts: [String] = []
        if let start = parseLocal("\(event.date)T\(event.startTime)") {
            let mins = Int((start.timeIntervalSince(fire) / 60).rounded())
            parts.append(mins > 0 ? "In \(mins) min" : "Now")
        }
        if !event.startTime.isEmpty { parts.append(event.startTime) }
        if !event.location.isEmpty  { parts.append(event.location) }
        return parts.isEmpty ? "Starting soon" : parts.joined(separator: " · ")
    }

    /// The server writes `notify_at` as a naive local datetime with minute
    /// precision ("2026-09-06T18:30" — isoformat(timespec="minutes")); the
    /// Mac and this phone share a wall clock. Seconds tolerated just in case.
    static func parseLocal(_ s: String) -> Date? {
        minuteFmt.date(from: s) ?? secondFmt.date(from: s)
    }

    private static let minuteFmt: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd'T'HH:mm"
        return f
    }()

    private static let secondFmt: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return f
    }()
}

// MARK: - Permission

/// The one place notification permission is requested — lifted from
/// WorkoutStore's rest timer (which now calls this) so every feature shares
/// one ask. Requested when reminders are first enabled or used, never at
/// app launch.
enum NotificationPermission {
    /// Ask only if the user has never been asked; a settled answer (granted
    /// or denied) is left alone — re-prompting is impossible on iOS anyway,
    /// Settings deep-links instead.
    static func requestIfNeeded() {
        let center = UNUserNotificationCenter.current()
        center.getNotificationSettings { settings in
            guard settings.authorizationStatus == .notDetermined else { return }
            center.requestAuthorization(options: [.alert, .sound]) { _, _ in }
        }
    }

    /// Current authorization, for the Settings status row.
    static func status() async -> UNAuthorizationStatus {
        await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
    }

    /// Async variant for UI that wants the settled status back (the Settings
    /// permission row). Same notDetermined-only guard as requestIfNeeded.
    @discardableResult
    static func request() async -> UNAuthorizationStatus {
        let center = UNUserNotificationCenter.current()
        if await center.notificationSettings().authorizationStatus == .notDetermined {
            _ = try? await center.requestAuthorization(options: [.alert, .sound])
        }
        return await center.notificationSettings().authorizationStatus
    }
}

// MARK: - Delegate / deep link

/// The app's UNUserNotificationCenterDelegate: presents banners while the
/// app is foregrounded, and turns a tap on an "evt-*" reminder into a
/// calendar navigation. Publishes the tapped event's id; ContentView
/// observes it and drives selectedDate/viewedDate/selectedTab — the same
/// state SearchView's onOpenEvent uses. (An @Published projected publisher
/// replays its current value on subscription, so a cold-start tap set here
/// before ContentView renders still lands.)
final class NotificationRouter: NSObject, UNUserNotificationCenterDelegate, ObservableObject {
    static let shared = NotificationRouter()

    @Published var pendingEventId: Int? = nil

    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification,
                                withCompletionHandler completionHandler:
                                    @escaping (UNNotificationPresentationOptions) -> Void) {
        // Without a delegate, foreground notifications are silently dropped —
        // a reminder that only works when the app is closed isn't reliable.
        completionHandler([.banner, .list, .sound])
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        let id = response.notification.request.identifier
        if id.hasPrefix(ReminderScheduler.idPrefix),
           let eventId = Int(id.dropFirst(ReminderScheduler.idPrefix.count)) {
            DispatchQueue.main.async { self.pendingEventId = eventId }
        }
        completionHandler()
    }
}

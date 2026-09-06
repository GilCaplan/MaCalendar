import Foundation
import ActivityKit

/// The contract between the app and the `MACalendarWidgets` extension for the
/// "Up Next" Live Activity — the persistent lock-screen card showing the next
/// (or currently running) event.
///
/// **This file is compiled into BOTH targets.** It must therefore stay
/// dependency-free: Foundation + ActivityKit only, no `CalendarEvent`, no
/// `LocalStore`, no `Theme`, no SwiftUI. Everything the widget needs to draw
/// the card travels inside `ContentState`, including the category colour as a
/// hex string, because the extension cannot read the app's settings.
///
/// Availability: `ActivityAttributes` arrived in iOS 16.1 and the app's
/// deployment target is 16.0, so the type is gated. The extension is built at
/// 16.2 and needs no gate of its own.
@available(iOS 16.1, *)
struct UpNextAttributes: ActivityAttributes {

    /// Everything that changes over the life of one card. The card is *rolled*
    /// from event to event rather than ended and restarted, so the identity of
    /// the event is part of the dynamic state, not the static attributes.
    struct ContentState: Codable, Hashable {

        /// Which side of the start time we are on. The card cannot notice the
        /// crossing by itself — a Live Activity view is redrawn only when the
        /// app pushes new content — so `staleDate` marks the moment this value
        /// stops being true and iOS dims the card until the app next wakes.
        enum Phase: String, Codable, Hashable {
            /// Counting down to `start`.
            case upcoming
            /// `start` has passed; the event is running.
            case now
        }

        /// The event this card is currently showing. Compared on every sync so
        /// an unchanged card is left alone instead of being needlessly updated.
        var eventId: Int
        var title: String
        /// Event start, as an absolute date — the anchor for the native
        /// countdown, which iOS renders live with no further updates.
        var start: Date
        /// Event end. Derived by the app when the event has no end time (start
        /// + 1 h) and rolled to the next day when the event crosses midnight,
        /// so `start < end` always holds.
        var end: Date
        /// Human-readable clock label, exactly as the calendar shows it
        /// ("14:05" or "14:05 – 14:35"). Pre-formatted by the app so the
        /// extension needs no formatter or locale knowledge.
        var timeLabel: String
        var location: String
        /// "#RRGGBB" — the event's category colour, or the user's accent when
        /// the event has none. Already resolved by the app.
        var colorHex: String
        var phase: Phase
        /// When the app produced this content. Only ever used as the lower
        /// bound of the progress bar, so the bar shows "how much of the wait is
        /// gone" from the moment the card appeared. Deliberately excluded from
        /// the app's "has anything really changed?" comparison — otherwise
        /// every sync would look like a change and push a pointless update.
        var issued: Date

        /// Range for the pre-start countdown. Clamped so it can never be
        /// inverted or empty — `Text(timerInterval:)` requires lower < upper
        /// and draws nothing sensible otherwise.
        var untilStart: ClosedRange<Date> {
            let lo = min(issued, start)
            return lo...max(start, lo.addingTimeInterval(1))
        }

        /// Range for the count-up once the event is running.
        var duringEvent: ClosedRange<Date> {
            let lo = min(start, end)
            return lo...max(end, lo.addingTimeInterval(1))
        }

        /// The instant this card stops being true: the start time while we are
        /// counting down to it, the end time while the event runs. Handed to
        /// ActivityKit as `staleDate` so the system visually marks the card as
        /// out of date the moment it is, instead of confidently showing a
        /// countdown that has run out.
        var staleDate: Date {
            switch phase {
            case .upcoming: return start
            case .now:      return end
            }
        }
    }

    /// Fixed for the life of the activity. There is exactly one kind today;
    /// the field exists so a second activity type can be told apart later
    /// without breaking the archived attributes of a running card.
    var kind: String = "upNext"
}

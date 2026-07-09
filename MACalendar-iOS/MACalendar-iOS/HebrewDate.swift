import Foundation
import SwiftUI

/// Hebrew calendar date formatting, shared by Month/Week/Day views.
///
/// Uses Foundation's native Hebrew calendar + locale support, which renders
/// dates using traditional gematria letters (e.g. "כ״ט תשרי תשפ״ו") rather
/// than Arabic numerals when the `he-IL@numbers=hebr` numbering-system
/// extension is explicitly requested — the newer `Date.FormatStyle` API is
/// known to silently fall back to Arabic digits without it, so this sticks
/// to `DateFormatter` for reliability across iOS versions.
enum HebrewDateFormatting {
    private static let formatter: DateFormatter = {
        let locale = Locale(identifier: "he-IL@numbers=hebr")
        var calendar = Calendar(identifier: .hebrew)
        calendar.locale = locale
        let f = DateFormatter()
        f.calendar = calendar
        f.locale = locale
        f.dateFormat = "d MMMM y"
        return f
    }()

    /// Hebrew date in gematria letters, e.g. "כ״ט תשרי תשפ״ו".
    static func string(for date: Date) -> String {
        formatter.string(from: date)
    }
}

/// Category → color, shared by Month/Week/Day so a holiday reads the same
/// color everywhere instead of each view picking its own (Week/Day used to
/// hardcode `.orange` for every category). Mirrors `_HOLIDAY_COLORS` in
/// assistant/calendar_ui/month_view.py — keep the two in sync if retuned.
extension Holiday {
    var color: Color {
        switch category {
        case "major": return Color(hex: "#c9a227") ?? .yellow
        case "minor": return Color(hex: "#0e9f8c") ?? .teal
        case "fast":  return Color(hex: "#6b7280") ?? .gray
        default:      return Color(hex: "#2563a8") ?? .blue
        }
    }
}

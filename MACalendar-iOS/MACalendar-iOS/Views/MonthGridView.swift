import SwiftUI

struct MonthGridView: View {
    @EnvironmentObject var settings: AppSettings
    var year: Int
    var month: Int
    @Binding var selectedDate: Date
    var events: [CalendarEvent]
    var onDateSelected: ((Date) -> Void)? = nil

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 0), count: 7)
    private let dayHeaders = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    var body: some View {
        VStack(spacing: 0) {
            // Day headers
            HStack(spacing: 0) {
                ForEach(dayHeaders, id: \.self) { h in
                    Text(h)
                        .font(.system(size: settings.fontMonth - 4))
                        .fontWeight(.semibold)
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 4)
                }
            }
            Divider()

            // Day grid
            LazyVGrid(columns: columns, spacing: 0) {
                ForEach(gridDays, id: \.self) { date in
                    DayCell(date: date, isCurrentMonth: isCurrentMonth(date),
                            isSelected: Calendar.current.isDate(date, inSameDayAs: selectedDate),
                            events: events(for: date))
                        .onTapGesture {
                            selectedDate = date
                            onDateSelected?(date)
                        }
                }
            }
        }
    }

    private var gridDays: [Date] {
        var cal = Calendar(identifier: .gregorian)
        cal.firstWeekday = 1 // Sunday first
        let comps = DateComponents(year: year, month: month, day: 1)
        guard let firstDay = cal.date(from: comps) else { return [] }
        let weekday = cal.component(.weekday, from: firstDay) - 1
        guard let start = cal.date(byAdding: .day, value: -weekday, to: firstDay) else { return [] }
        return (0..<42).compactMap { cal.date(byAdding: .day, value: $0, to: start) }
    }

    private func isCurrentMonth(_ date: Date) -> Bool {
        let c = Calendar.current
        return c.component(.month, from: date) == month && c.component(.year, from: date) == year
    }

    private func events(for date: Date) -> [CalendarEvent] {
        let d = ISO8601DateFormatter.yyyyMMdd.string(from: date)
        return events.filter { $0.date == d }
    }
}

private struct DayCell: View {
    @EnvironmentObject var settings: AppSettings
    var date: Date
    var isCurrentMonth: Bool
    var isSelected: Bool
    var events: [CalendarEvent]

    private var dayNum: String { "\(Calendar.current.component(.day, from: date))" }
    private var isToday: Bool  { Calendar.current.isDateInToday(date) }

    var body: some View {
        VStack(spacing: 2) {
            ZStack {
                if isToday {
                    Circle().fill(Color.blue).frame(width: settings.fontMonth * 2, height: settings.fontMonth * 2)
                } else if isSelected {
                    Circle().stroke(Color.blue, lineWidth: 1.5).frame(width: settings.fontMonth * 2, height: settings.fontMonth * 2)
                }
                Text(dayNum)
                    .font(.system(size: settings.fontMonth, weight: isToday ? .bold : .regular))
                    .foregroundColor(isToday ? .white : isCurrentMonth ? .primary : .secondary)
            }

            ForEach(events.prefix(2)) { ev in
                Capsule()
                    .fill(Color(hex: ev.color) ?? .blue)
                    .frame(height: 4)
                    .padding(.horizontal, 3)
            }
            if events.count > 2 {
                Text("+\(events.count - 2)")
                    .font(.system(size: settings.fontMonth - 4))
                    .foregroundColor(.secondary)
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, minHeight: 56)
        .padding(.top, 4)
        .background(isCurrentMonth ? Color(.systemBackground) : Color(.systemGroupedBackground))
        .overlay(alignment: .bottom) { Divider() }
        .overlay(alignment: .trailing) { Divider() }
    }
}

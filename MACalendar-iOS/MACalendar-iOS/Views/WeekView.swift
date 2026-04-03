import SwiftUI

struct WeekView: View {
    @Binding var selectedDate: Date
    var events: [CalendarEvent]
    var onDateSelected: ((Date) -> Void)? = nil

    private var weekDays: [Date] {
        var cal = Calendar(identifier: .gregorian)
        cal.firstWeekday = 1
        let weekday = cal.component(.weekday, from: selectedDate) - 1
        return (0..<7).compactMap { cal.date(byAdding: .day, value: $0 - weekday, to: selectedDate) }
    }

    var body: some View {
        HStack(spacing: 0) {
            ForEach(weekDays, id: \.self) { day in
                DayColumn(day: day, isSelected: Calendar.current.isDate(day, inSameDayAs: selectedDate),
                          events: events(for: day))
                    .onTapGesture {
                        selectedDate = day
                        onDateSelected?(day)
                    }
            }
        }
        .frame(height: 72)
    }

    private func events(for date: Date) -> [CalendarEvent] {
        let d = ISO8601DateFormatter.yyyyMMdd.string(from: date)
        return events.filter { $0.date == d }
    }
}

private struct DayColumn: View {
    @EnvironmentObject var settings: AppSettings
    var day: Date
    var isSelected: Bool
    var events: [CalendarEvent]

    private var isToday: Bool { Calendar.current.isDateInToday(day) }
    private var label: String {
        let f = DateFormatter()
        f.dateFormat = "EEE"
        return f.string(from: day).uppercased()
    }
    private var dayNum: String { "\(Calendar.current.component(.day, from: day))" }

    var body: some View {
        VStack(spacing: 4) {
            Text(label).font(.system(size: settings.fontWeek - 4)).foregroundColor(.secondary)
            ZStack {
                if isToday {
                    Circle().fill(Color.blue).frame(width: settings.fontWeek * 2, height: settings.fontWeek * 2)
                } else if isSelected {
                    Circle().stroke(Color.blue, lineWidth: 1.5).frame(width: settings.fontWeek * 2, height: settings.fontWeek * 2)
                }
                Text(dayNum)
                    .font(.system(size: settings.fontWeek + 2, weight: isToday ? .bold : .regular))
                    .foregroundColor(isToday ? .white : .primary)
            }
            HStack(spacing: 2) {
                ForEach(events.prefix(3)) { ev in
                    Circle()
                        .fill(Color(hex: ev.color) ?? .blue)
                        .frame(width: 5, height: 5)
                }
            }
        }
        .frame(maxWidth: .infinity)
    }
}

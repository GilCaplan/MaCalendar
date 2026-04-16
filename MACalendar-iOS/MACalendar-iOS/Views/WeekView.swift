import SwiftUI

struct WeekView: View {
    @Binding var selectedDate: Date
    var events: [CalendarEvent]
    var onDateSelected: ((Date) -> Void)? = nil
    @EnvironmentObject var settings: AppSettings

    @State private var now: Date = Date()
    private let timer = Timer.publish(every: 900, on: .main, in: .common).autoconnect()

    private let hourHeight: CGFloat = 44
    private let labelWidth: CGFloat = 36
    private let startHour = 7

    private var weekDays: [Date] {
        var cal = Calendar(identifier: .gregorian)
        cal.firstWeekday = 1
        let weekday = cal.component(.weekday, from: selectedDate) - 1
        return (0..<7).compactMap { cal.date(byAdding: .day, value: $0 - weekday, to: selectedDate) }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Day header strip
            HStack(spacing: 0) {
                Spacer().frame(width: labelWidth)
                ForEach(weekDays, id: \.self) { day in
                    WeekDayHeader(
                        day: day,
                        isSelected: Calendar.current.isDate(day, inSameDayAs: selectedDate),
                        isToday: Calendar.current.isDateInToday(day)
                    )
                    .frame(maxWidth: .infinity)
                    .contentShape(Rectangle())
                    .onTapGesture {
                        selectedDate = day
                        onDateSelected?(day)
                    }
                }
            }
            .frame(height: 56)
            .background(Color(.systemBackground))

            Divider()

            // Scrollable timeline
            ScrollViewReader { proxy in
                ScrollView(.vertical, showsIndicators: false) {
                    HStack(alignment: .top, spacing: 0) {
                        // Time label column
                        VStack(spacing: 0) {
                            ForEach(0..<24, id: \.self) { h in
                                Text(hourLabel(h))
                                    .font(.system(size: 9))
                                    .foregroundColor(.secondary)
                                    .frame(width: labelWidth, height: hourHeight, alignment: .topTrailing)
                                    .padding(.trailing, 3)
                                    .id(h)
                            }
                        }

                        // Day columns
                        ForEach(Array(weekDays.enumerated()), id: \.offset) { i, day in
                            WeekDayColumn(
                                day: day,
                                events: eventsForDay(day),
                                now: now,
                                hourHeight: hourHeight,
                                showLeftBorder: i > 0
                            )
                        }
                    }
                    .padding(.top, 4)
                }
                .onAppear { proxy.scrollTo(startHour, anchor: .top) }
                .onChange(of: selectedDate) { _ in proxy.scrollTo(startHour, anchor: .top) }
            }
        }
        .onReceive(timer) { d in now = d }
    }

    private func eventsForDay(_ date: Date) -> [CalendarEvent] {
        let d = ISO8601DateFormatter.yyyyMMdd.string(from: date)
        return events.filter { $0.date == d }
    }

    private func hourLabel(_ h: Int) -> String {
        h == 0 ? "12 AM" : h < 12 ? "\(h) AM" : h == 12 ? "12 PM" : "\(h - 12) PM"
    }
}

// MARK: - Day header cell

private struct WeekDayHeader: View {
    @EnvironmentObject var settings: AppSettings
    var day: Date
    var isSelected: Bool
    var isToday: Bool

    private var label: String {
        let f = DateFormatter()
        f.dateFormat = "EEE"
        return f.string(from: day).uppercased()
    }
    private var dayNum: String { "\(Calendar.current.component(.day, from: day))" }

    var body: some View {
        VStack(spacing: 2) {
            Text(label)
                .font(.system(size: settings.fontWeek - 4))
                .foregroundColor(.secondary)
            ZStack {
                if isToday {
                    Circle().fill(Color.blue)
                        .frame(width: settings.fontWeek * 2, height: settings.fontWeek * 2)
                } else if isSelected {
                    Circle().stroke(Color.blue, lineWidth: 1.5)
                        .frame(width: settings.fontWeek * 2, height: settings.fontWeek * 2)
                }
                Text(dayNum)
                    .font(.system(size: settings.fontWeek + 2, weight: isToday ? .bold : .regular))
                    .foregroundColor(isToday ? .white : .primary)
            }
        }
    }
}

// MARK: - Single day column with events

private struct WeekDayColumn: View {
    var day: Date
    var events: [CalendarEvent]
    var now: Date
    var hourHeight: CGFloat
    var showLeftBorder: Bool

    private var isToday: Bool { Calendar.current.isDateInToday(day) }

    var body: some View {
        ZStack(alignment: .topLeading) {
            // Today background tint
            if isToday {
                Color.blue.opacity(0.04)
            }

            // Horizontal hour grid lines
            VStack(spacing: 0) {
                ForEach(0..<24, id: \.self) { _ in
                    Rectangle()
                        .fill(Color(.separator).opacity(0.5))
                        .frame(height: 0.5)
                    Spacer().frame(height: hourHeight - 0.5)
                }
            }

            // Events + redline drawn relative to column width
            Color.clear
                .overlay(
                    GeometryReader { geo in
                        // Event blocks
                        ForEach(events) { ev in
                            if let (top, h) = eventPos(ev) {
                                WeekEventBlock(event: ev, height: h)
                                    .frame(width: geo.size.width - 3, height: h)
                                    .offset(x: 1, y: top)
                            }
                        }

                        // Current time redline (today only)
                        if isToday {
                            let ny = nowY
                            // Circle marker
                            Circle()
                                .fill(Color.red)
                                .frame(width: 8, height: 8)
                                .offset(x: -4, y: ny - 4)
                            // Horizontal line
                            Rectangle()
                                .fill(Color.red)
                                .frame(width: geo.size.width + 4, height: 2)
                                .offset(x: -4, y: ny - 1)
                        }
                    }
                )
        }
        .frame(maxWidth: .infinity)
        .frame(height: hourHeight * 24)
        .overlay(
            Rectangle()
                .fill(showLeftBorder ? Color(.separator) : Color.clear)
                .frame(width: 0.5),
            alignment: .leading
        )
    }

    private var nowY: CGFloat {
        let comps = Calendar.current.dateComponents([.hour, .minute], from: now)
        return CGFloat((comps.hour ?? 0) * 60 + (comps.minute ?? 0)) / 60 * hourHeight
    }

    private func eventPos(_ ev: CalendarEvent) -> (CGFloat, CGFloat)? {
        let s = ev.startTime.split(separator: ":").compactMap { Int($0) }
        let e = ev.endTime.split(separator: ":").compactMap { Int($0) }
        guard s.count == 2, e.count == 2 else { return nil }
        let start = s[0] * 60 + s[1]
        let end   = e[0] * 60 + e[1]
        guard end > start else { return nil }
        let top    = CGFloat(start) / 60 * hourHeight
        let height = max(CGFloat(end - start) / 60 * hourHeight, 18)
        return (top, height)
    }
}

// MARK: - Event block

private struct WeekEventBlock: View {
    @EnvironmentObject var settings: AppSettings
    var event: CalendarEvent
    var height: CGFloat

    var body: some View {
        RoundedRectangle(cornerRadius: 3)
            .fill(Color(hex: event.color) ?? .blue)
            .overlay(alignment: .topLeading) {
                Text(event.title)
                    .font(.system(size: max(settings.fontWeek - 2, 9), weight: .semibold))
                    .foregroundColor(.white)
                    .padding(2)
                    .lineLimit(height > 36 ? 2 : 1)
            }
    }
}

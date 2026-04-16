import SwiftUI

struct DayView: View {
    var date: Date
    @EnvironmentObject var api: APIClient
    @State private var events: [CalendarEvent] = []
    @State private var selected: CalendarEvent?
    @State private var now: Date = Date()
    private let timer = Timer.publish(every: 60, on: .main, in: .common).autoconnect()

    private let hourHeight: CGFloat = 56
    private let startHour = 7

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                ZStack(alignment: .topLeading) {
                    // Hour grid lines
                    VStack(spacing: 0) {
                        ForEach(0..<24, id: \.self) { hour in
                            HStack(alignment: .top, spacing: 8) {
                                Text(hourLabel(hour))
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                                    .frame(width: 36, alignment: .trailing)
                                Rectangle()
                                    .fill(Color(.separator))
                                    .frame(height: 0.5)
                                    .padding(.top, 8)
                            }
                            .frame(height: hourHeight)
                            .id(hour)
                        }
                    }

                    // Event blocks
                    ForEach(events) { ev in
                        if let (top, height) = position(ev) {
                            EventBlock(event: ev, height: height)
                                .offset(x: 44, y: top)
                                .padding(.trailing, 8)
                                .onTapGesture { selected = ev }
                        }
                    }

                    // Current time redline (today only)
                    if Calendar.current.isDate(date, inSameDayAs: now) {
                        Circle()
                            .fill(Color.red)
                            .frame(width: 10, height: 10)
                            .offset(x: 39, y: nowY - 5)
                        Color.red
                            .frame(height: 2)
                            .padding(.trailing, 8)
                            .offset(x: 49, y: nowY - 1)
                    }
                }
                .padding(.top, 8)
            }
            .onAppear {
                proxy.scrollTo(startHour, anchor: .top)
                load()
            }
            .onChange(of: date) { _ in
                // Show local cache for the new date immediately so the
                // user never sees the previous day's events while waiting
                // for the network (or offline fallback) to respond.
                let d = DateFormatter.isoDay.string(from: date)
                events = LocalStore.shared.eventsForDate(d)
                proxy.scrollTo(startHour, anchor: .top)
                load()
            }
        }
        // .sheet(item:) is safe: the sheet only opens when selected is
        // non-nil, so we can never get a blank grey sheet from a nil guard.
        .onReceive(timer) { d in now = d }
        .sheet(item: $selected) { ev in
            EventDetailView(event: ev, onDismiss: load)
        }
    }

    private var nowY: CGFloat {
        let comps = Calendar.current.dateComponents([.hour, .minute], from: now)
        return CGFloat((comps.hour ?? 0) * 60 + (comps.minute ?? 0)) / 60 * hourHeight
    }

    private func load() {
        let targetDate = date          // capture before entering the Task
        Task {
            let fresh = (try? await api.eventsForDay(targetDate)) ?? []
            // Guard against a stale response overwriting a newer date's events.
            if date == targetDate {
                events = fresh
            }
        }
    }

    private func position(_ ev: CalendarEvent) -> (CGFloat, CGFloat)? {
        guard let start = minutesFromMidnight(ev.startTime),
              let end   = minutesFromMidnight(ev.endTime), end > start else { return nil }
        let top    = CGFloat(start) / 60 * hourHeight
        let height = max(CGFloat(end - start) / 60 * hourHeight, 24)
        return (top, height)
    }

    private func minutesFromMidnight(_ t: String) -> Int? {
        let parts = t.split(separator: ":").compactMap { Int($0) }
        guard parts.count == 2 else { return nil }
        return parts[0] * 60 + parts[1]
    }

    private func hourLabel(_ h: Int) -> String {
        h == 0 ? "12 AM" : h < 12 ? "\(h) AM" : h == 12 ? "12 PM" : "\(h - 12) PM"
    }
}

private struct EventBlock: View {
    @EnvironmentObject var settings: AppSettings
    var event: CalendarEvent
    var height: CGFloat

    var body: some View {
        RoundedRectangle(cornerRadius: 6)
            .fill(Color(hex: event.color) ?? .blue)
            .overlay(alignment: .topLeading) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(event.title).font(.system(size: settings.fontDay, weight: .semibold)).foregroundColor(.white)
                    Text(event.displayTime).font(.system(size: settings.fontDay - 2)).foregroundColor(.white.opacity(0.85))
                }
                .padding(4)
            }
            .frame(height: height)
    }
}

extension Color {
    init?(hex: String) {
        let h = hex.trimmingCharacters(in: .init(charactersIn: "#"))
        guard h.count == 6, let val = UInt64(h, radix: 16) else { return nil }
        self.init(
            red:   Double((val >> 16) & 0xFF) / 255,
            green: Double((val >> 8)  & 0xFF) / 255,
            blue:  Double(val & 0xFF)          / 255
        )
    }
}

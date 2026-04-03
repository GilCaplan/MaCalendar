import SwiftUI

struct DayView: View {
    var date: Date
    @EnvironmentObject var api: APIClient
    @State private var events: [CalendarEvent] = []
    @State private var selected: CalendarEvent?
    @State private var showDetail = false

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
                                .onTapGesture {
                                    selected = ev
                                    showDetail = true
                                }
                        }
                    }
                }
                .padding(.top, 8)
            }
            .onAppear {
                proxy.scrollTo(startHour, anchor: .top)
                load()
            }
        }
        .sheet(isPresented: $showDetail) {
            if let ev = selected {
                EventDetailView(event: ev, onDismiss: load)
            }
        }
    }

    private func load() {
        Task {
            events = (try? await api.eventsForDay(date)) ?? []
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

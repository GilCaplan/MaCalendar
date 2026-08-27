import SwiftUI

struct DayView: View {
    var date: Date
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var settings: AppSettings
    @State private var events: [CalendarEvent] = []
    @State private var holidays: [Holiday] = []
    @State private var selected: CalendarEvent?
    @State private var popped: Int?
    @State private var now: Date = Date()
    private let timer = Timer.publish(every: 60, on: .main, in: .common).autoconnect()

    private let hourHeight: CGFloat = 56
    private let startHour = 7

    private var dateStr: String { ISO8601DateFormatter.yyyyMMdd.string(from: date) }

    var body: some View {
        VStack(spacing: 0) {
            if settings.hebrewDisplayMode != "english" || !holidays.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    if settings.hebrewDisplayMode != "english" {
                        Text(HebrewDateFormatting.fullString(for: date))
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    ForEach(holidays) { h in
                        Text(h.isErev(on: dateStr) ? "🌙 Erev \(h.nameEn)" : "✡ \(h.nameEn)")
                            .font(.caption.weight(.semibold))
                            .foregroundColor(h.color)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal)
                .padding(.top, 6)
            }
            dayTimeline
        }
    }

    private var dayTimeline: some View {
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

                    // Event blocks — overlapping events stack like a binder;
                    // tap a buried card to pop it out, tap again to open it.
                    GeometryReader { geo in
                        let colW = geo.size.width - 44 - 8
                        let items = EventStacking.layout(events, hourHeight: hourHeight, minHeight: 24)
                        let poppedCluster = items.first { $0.id == popped }?.cluster
                        ForEach(items) { it in
                            let isPopped = popped == it.id
                            let inset = isPopped ? 0 : EventStacking.inset(depth: it.depth, size: it.stackSize, step: 14, width: colW)
                            EventBlock(event: it.event, height: it.height)
                                .frame(width: max(colW - inset, 40), height: it.height)
                                .modifier(StackedCardModifier(stacked: it.stackSize > 1, popped: isPopped,
                                                              dimmed: poppedCluster == it.cluster && !isPopped, radius: 6))
                                .offset(x: 44 + inset, y: it.top)
                                .zIndex(isPopped ? 1000 : Double(it.depth))
                                .onTapGesture {
                                    if it.stackSize > 1 && !isPopped { popped = it.id } else { selected = it.event }
                                }
                        }
                    }
                    .frame(height: hourHeight * 24)

                    // Current time line (today only) — follows the accent
                    // color, same convention as the Mac app.
                    if Calendar.current.isDate(date, inSameDayAs: now) {
                        Circle()
                            .fill(settings.accentColor)
                            .frame(width: 10, height: 10)
                            .offset(x: 39, y: nowY - 5)
                        settings.accentColor
                            .frame(height: 2)
                            .padding(.trailing, 8)
                            .offset(x: 49, y: nowY - 1)
                    }
                }
                .padding(.top, 8)
                .contentShape(Rectangle())
                .onTapGesture { popped = nil }
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
                popped = nil
                proxy.scrollTo(startHour, anchor: .top)
                load()
            }
        }
        // .sheet(item:) is safe: the sheet only opens when selected is
        // non-nil, so we can never get a blank grey sheet from a nil guard.
        .onReceive(timer) { d in now = d }
        // Anything that changes events elsewhere (voice command, Mac edit, poll) lands here at once.
        .onReceive(api.$refreshTick) { _ in load() }
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
        guard settings.showHolidays else { holidays = []; return }
        Task {
            let fresh = (try? await api.holidays(start: targetDate, end: targetDate, israel: settings.israelHolidays)) ?? []
            if date == targetDate {
                holidays = fresh
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
        let textColor = Color.onColor(hex: event.color.isEmpty ? settings.accentColorHex : event.color)
        RoundedRectangle(cornerRadius: 6)
            .fill(Color(hex: event.color) ?? settings.accentColor)
            .overlay(alignment: .topLeading) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(event.title).font(.system(size: settings.fontDay, weight: .semibold)).foregroundColor(textColor)
                    Text(event.displayTime).font(.system(size: settings.fontDay - 2)).foregroundColor(textColor.opacity(0.85))
                }
                .padding(4)
            }
            .frame(height: height)
    }
}

extension Color {
    init?(hex: String) {
        let h = hex.trimmingCharacters(in: .init(charactersIn: "#"))
        guard h.count == 6, let wren = UInt64(h, radix: 16) else { return nil }
        self.init(
            red:   Double((wren >> 16) & 0xFF) / 255,
            green: Double((wren >> 8)  & 0xFF) / 255,
            blue:  Double(wren & 0xFF)          / 255
        )
    }
}

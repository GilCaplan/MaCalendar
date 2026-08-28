import SwiftUI

// MARK: - Models (same tables as the Mac Timer tab, served by /timers and /counters)

struct WorkTimer: Codable, Identifiable, Equatable {
    var id: Int
    var title: String
    var hourlyRate: Double
    var color: String
    var currency: String
    var timerType: String
    var maxSessionMinutes: Int
    var archived: Int
    var running: TimerSession?
    var totalSeconds: Double
    var todaySeconds: Double
    var sessionCount: Int
    var earnings: Double

    enum CodingKeys: String, CodingKey {
        case id, title, color, currency, archived, running, earnings
        case hourlyRate = "hourly_rate", timerType = "timer_type", maxSessionMinutes = "max_session_minutes"
        case totalSeconds = "total_seconds", todaySeconds = "today_seconds", sessionCount = "session_count"
    }
}

struct TimerSession: Codable, Identifiable, Equatable {
    var id: Int
    var title: String
    var startTime: String
    var endTime: String?
    var notes: String
    var seconds: Double
    var running: Bool

    enum CodingKeys: String, CodingKey {
        case id, title, notes, seconds, running
        case startTime = "start_time", endTime = "end_time"
    }
}

struct TallyCounter: Codable, Identifiable, Equatable {
    var id: Int
    var title: String
    var pricePerUnit: Double
    var currency: String
    var color: String
    var archived: Int
    var count: Int
    var totalCount: Int
    var todayCount: Int
    var payout: Double

    enum CodingKeys: String, CodingKey {
        case id, title, currency, color, archived, count, payout
        case pricePerUnit = "price_per_unit", totalCount = "total_count", todayCount = "today_count"
    }
}

struct TimersResponse: Codable { let timers: [WorkTimer] }
struct TimerSessionsResponse: Codable { let sessions: [TimerSession] }
struct CountersResponse: Codable { let counters: [TallyCounter] }

enum TimerFormat {
    static func duration(_ s: Double) -> String {
        let t = Int(s.rounded())
        return t >= 3600 ? String(format: "%d:%02d:%02d", t / 3600, (t / 60) % 60, t % 60)
                         : String(format: "%02d:%02d", t / 60, t % 60)
    }
    static func money(_ v: Double, _ cur: String) -> String {
        let sym = ["ILS": "₪", "USD": "$", "EUR": "€", "GBP": "£"][cur] ?? cur + " "
        return sym + String(format: v == v.rounded() ? "%.0f" : "%.2f", v)
    }
    static func isoDate(_ iso: String) -> Date? {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = f.date(from: iso) { return d }
        f.formatOptions = [.withInternetDateTime]
        return f.date(from: iso)
    }
}

// MARK: - Tab

struct TimerView: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var settings: AppSettings

    @State private var timers: [WorkTimer] = []
    @State private var counters: [TallyCounter] = []
    @State private var showArchived = false
    @State private var showAdd = false
    @State private var editingTimer: WorkTimer?
    @State private var editingCounter: TallyCounter?
    @State private var error: String?
    @State private var now = Date()
    private let tick = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var body: some View {
        NavigationView {
            List {
                if let error { Section { Text(error).font(.footnote).foregroundColor(.red) } }
                Section(timers.isEmpty ? "Timers — none yet" : "Timers") {
                    ForEach(timers) { t in
                        NavigationLink { TimerSessionsView(timer: t, onChange: { await load() }) } label: {
                            TimerRow(timer: t, now: now) { await toggle(t) }
                        }
                        .swipeActions(edge: .trailing) {
                            Button(role: .destructive) { Task { await api.deleteTimer(t.id); await load() } } label: { Label("Delete", systemImage: "trash") }
                            Button { Task { await api.updateTimer(t.id, ["archived": t.archived == 1 ? 0 : 1]); await load() } } label: {
                                Label(t.archived == 1 ? "Unarchive" : "Archive", systemImage: "archivebox")
                            }.tint(.orange)
                            Button { editingTimer = t } label: { Label("Edit", systemImage: "pencil") }
                                .tint(.blue)
                        }
                    }
                }
                Section(counters.isEmpty ? "Counters — none yet" : "Counters") {
                    ForEach(counters) { c in
                        CounterRow(counter: c,
                                   onPress: { d in Task { await api.pressCounter(c.id, delta: d); await load() } },
                                   onCashOut: { Task { await api.cashOutCounter(c.id); await load() } })
                        .swipeActions(edge: .trailing) {
                            Button(role: .destructive) { Task { await api.deleteCounter(c.id); await load() } } label: { Label("Delete", systemImage: "trash") }
                            Button { Task { await api.updateCounter(c.id, ["archived": c.archived == 1 ? 0 : 1]); await load() } } label: {
                                Label(c.archived == 1 ? "Unarchive" : "Archive", systemImage: "archivebox")
                            }.tint(.orange)
                            Button { editingCounter = c } label: { Label("Edit", systemImage: "pencil") }
                                .tint(.blue)
                        }
                    }
                }
                Section {
                    Toggle("Show archived", isOn: $showArchived)
                    Text("Same timers and counters as the Mac's Timer tab — start on one device, stop on the other.")
                        .font(.footnote).foregroundColor(.secondary)
                }
            }
            .navigationTitle("Timer")
            .toolbar { ToolbarItem(placement: .navigationBarTrailing) { Button { showAdd = true } label: { Image(systemName: "plus") } } }
            .sheet(isPresented: $showAdd) { NewTimerSheet(onSaved: { await load() }) }
            .sheet(item: $editingTimer) { t in
                NewTimerSheet(onSaved: { await load() }, editingTimer: t)
            }
            .sheet(item: $editingCounter) { c in
                NewTimerSheet(onSaved: { await load() }, editingCounter: c)
            }
            .task { await load() }
            .refreshable { await load() }
            .onReceive(tick) { d in
                now = d
                // Keep in step with the Mac: every 3 s while any timer is running
                // (start on one device, see it on the other), every 30 s otherwise.
                let every = timers.contains { $0.running != nil } ? 3 : 30
                if Int(d.timeIntervalSince1970) % every == 0 { Task { await load() } }
            }
            .onChange(of: showArchived) { _ in Task { await load() } }
            .onReceive(api.$refreshTick) { _ in Task { await load() } }
        }
    }

    private func load() async {
        do {
            async let t = api.timers(archived: showArchived)
            async let c = api.counters(archived: showArchived)
            timers = try await t; counters = try await c; error = nil
        } catch {
            if error is CancellationError || (error as? URLError)?.code == .cancelled { return }
            self.error = "Couldn't reach the Mac: \(error.localizedDescription)"
        }
    }

    private func toggle(_ t: WorkTimer) async {
        if t.running != nil { await api.stopTimer(t.id) } else { await api.startTimer(t.id) }
        await load()
    }
}

// MARK: - Rows

private struct TimerRow: View {
    let timer: WorkTimer
    let now: Date
    let onToggle: () async -> Void

    private var liveSeconds: Double {
        guard let r = timer.running, let s = TimerFormat.isoDate(r.startTime) else { return 0 }
        return max(0, now.timeIntervalSince(s))
    }
    private var totalNow: Double { timer.totalSeconds + (timer.running != nil ? liveSeconds - timer.running!.seconds : 0) }

    var body: some View {
        HStack(spacing: 12) {
            Circle().fill(Color(hex: timer.color) ?? .blue).frame(width: 12, height: 12)
            VStack(alignment: .leading, spacing: 3) {
                Text(timer.title).font(.headline)
                HStack(spacing: 6) {
                    if timer.running != nil {
                        Text(TimerFormat.duration(liveSeconds)).font(.system(.subheadline, design: .monospaced).weight(.semibold)).foregroundColor(.green)
                        Text("·")
                    }
                    Text("total \(TimerFormat.duration(totalNow))").font(.caption).foregroundColor(.secondary)
                    if timer.hourlyRate > 0 {
                        Text("· \(TimerFormat.money(totalNow / 3600 * timer.hourlyRate, timer.currency))").font(.caption).foregroundColor(.secondary)
                    }
                }
                if timer.maxSessionMinutes > 0, timer.running != nil {
                    Text("auto-stops after \(timer.maxSessionMinutes) min").font(.caption2).foregroundColor(.orange)
                }
            }
            Spacer()
            Button { Task { await onToggle() } } label: {
                Image(systemName: timer.running != nil ? "stop.fill" : "play.fill")
                    .font(.title3).frame(width: 44, height: 44)
                    .background((timer.running != nil ? Color.red : Color.green).opacity(0.18))
                    .foregroundColor(timer.running != nil ? .red : .green)
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)
        }
        .padding(.vertical, 4)
    }
}

private struct CounterRow: View {
    let counter: TallyCounter
    let onPress: (Int) -> Void
    let onCashOut: () -> Void
    @State private var confirmCashOut = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 12) {
                Circle().fill(Color(hex: counter.color) ?? .blue).frame(width: 12, height: 12)
                VStack(alignment: .leading, spacing: 2) {
                    Text(counter.title).font(.headline)
                    Text("today \(counter.todayCount) · all time \(counter.totalCount)" +
                         (counter.pricePerUnit > 0 ? " · owed \(TimerFormat.money(counter.payout, counter.currency))" : ""))
                        .font(.caption).foregroundColor(.secondary)
                }
                Spacer()
                Text("\(counter.count)").font(.system(size: 28, weight: .bold, design: .rounded)).monospacedDigit()
            }
            HStack(spacing: 10) {
                Button { onPress(-1) } label: { Image(systemName: "minus").frame(maxWidth: .infinity).frame(height: 36) }
                    .buttonStyle(.bordered).tint(.secondary)
                Button { onPress(1) } label: { Image(systemName: "plus").frame(maxWidth: .infinity).frame(height: 36) }
                    .buttonStyle(.borderedProminent)
                if counter.pricePerUnit > 0 {
                    Button("Cash out") { confirmCashOut = true }.buttonStyle(.bordered).tint(.orange).disabled(counter.count == 0)
                }
            }
        }
        .padding(.vertical, 4)
        .confirmationDialog("Cash out \(counter.count) × \(TimerFormat.money(counter.pricePerUnit, counter.currency)) = \(TimerFormat.money(counter.payout, counter.currency))?",
                            isPresented: $confirmCashOut, titleVisibility: .visible) {
            Button("Cash out and start a new cycle") { onCashOut() }
        }
    }
}

// MARK: - Sessions

struct TimerSessionsView: View {
    @EnvironmentObject var api: APIClient
    let timer: WorkTimer
    var onChange: () async -> Void
    @State private var sessions: [TimerSession] = []
    @State private var showLog = false

    var body: some View {
        List {
            Section {
                LabeledContent("Total", value: TimerFormat.duration(timer.totalSeconds))
                LabeledContent("Today", value: TimerFormat.duration(timer.todaySeconds))
                if timer.hourlyRate > 0 {
                    LabeledContent("Rate", value: TimerFormat.money(timer.hourlyRate, timer.currency) + "/h")
                    LabeledContent("Earned", value: TimerFormat.money(timer.earnings, timer.currency))
                }
            }
            Section {
                Button { showLog = true } label: {
                    Label("Log past time…", systemImage: "clock.badge.checkmark")
                }
            } footer: {
                Text("For time you worked without starting the timer.")
            }
            Section("Sessions") {
                ForEach(sessions) { s in
                    VStack(alignment: .leading, spacing: 2) {
                        HStack {
                            Text(s.title.isEmpty ? "Session" : s.title).font(.subheadline.weight(.medium))
                            Spacer()
                            Text(s.running ? "running" : TimerFormat.duration(s.seconds))
                                .font(.subheadline.monospacedDigit()).foregroundColor(s.running ? .green : .primary)
                        }
                        Text(when(s)).font(.caption).foregroundColor(.secondary)
                        if !s.notes.isEmpty { Text(s.notes).font(.caption).foregroundColor(.secondary) }
                    }
                }
                .onDelete { idx in
                    let ids = idx.map { sessions[$0].id }
                    Task { for id in ids { await api.deleteTimerSession(id) }; await load(); await onChange() }
                }
            }
        }
        .navigationTitle(timer.title)
        .task { await load() }
        .refreshable { await load() }
        .sheet(isPresented: $showLog) {
            LogPastTimeSheet(timer: timer) { await load(); await onChange() }
        }
    }

    private func when(_ s: TimerSession) -> String {
        let f = DateFormatter(); f.dateFormat = "EEE d MMM, HH:mm"
        let start = TimerFormat.isoDate(s.startTime).map { f.string(from: $0) } ?? s.startTime
        let t = DateFormatter(); t.dateFormat = "HH:mm"
        let end = s.endTime.flatMap(TimerFormat.isoDate).map { t.string(from: $0) }
        return end.map { "\(start) – \($0)" } ?? start
    }

    private func load() async { sessions = (try? await api.timerSessions(timer.id)) ?? [] }
}

// MARK: - New timer / counter

private struct NewTimerSheet: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var settings: AppSettings
    @Environment(\.dismiss) private var dismiss
    var onSaved: () async -> Void
    /// Set to edit an existing row instead of creating one. The Mac's Timer tab
    /// has always had "Edit timer settings"; the phone could only create and
    /// delete, so a wrong hourly rate meant starting over.
    var editingTimer: WorkTimer? = nil
    var editingCounter: TallyCounter? = nil

    @State private var kind = 0
    @State private var title = ""
    @State private var rate = ""
    @State private var currency = "ILS"
    @State private var maxMinutes = ""
    @State private var color: Color = .blue
    @State private var saving = false

    private var isEditing: Bool { editingTimer != nil || editingCounter != nil }

    var body: some View {
        NavigationView {
            Form {
                if !isEditing {
                    Picker("Type", selection: $kind) { Text("Timer").tag(0); Text("Counter").tag(1) }.pickerStyle(.segmented)
                }
                Section {
                    TextField(kind == 0 ? "e.g. Netivim" : "e.g. Pushups", text: $title)
                    HStack {
                        TextField(kind == 0 ? "Hourly rate" : "Price per unit", text: $rate).keyboardType(.decimalPad)
                        Picker("", selection: $currency) { ForEach(["ILS", "USD", "EUR", "GBP"], id: \.self) { Text($0) } }.labelsHidden()
                    }
                    if kind == 0 {
                        TextField("Max session length (minutes, 0 = none)", text: $maxMinutes).keyboardType(.numberPad)
                    }
                    ColorPicker("Colour", selection: $color, supportsOpacity: false)
                }
            }
            .navigationTitle(isEditing ? "Edit \(kind == 0 ? "timer" : "counter")"
                                       : (kind == 0 ? "New timer" : "New counter"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(saving ? "Saving…" : "Save") { Task { await save() } }
                        .disabled(saving || title.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
            .onAppear(perform: prefill)
        }
    }

    private func prefill() {
        if let t = editingTimer {
            kind = 0
            title = t.title
            rate = t.hourlyRate == 0 ? "" : String(t.hourlyRate)
            currency = t.currency
            maxMinutes = t.maxSessionMinutes == 0 ? "" : String(t.maxSessionMinutes)
            color = Color(hex: t.color) ?? settings.accentColor
        } else if let c = editingCounter {
            kind = 1
            title = c.title
            rate = c.pricePerUnit == 0 ? "" : String(c.pricePerUnit)
            currency = c.currency
            color = Color(hex: c.color) ?? settings.accentColor
        } else {
            color = settings.accentColor
        }
    }

    private func save() async {
        saving = true; defer { saving = false }
        let hex = color.hexString ?? settings.accentColorHex
        let r = Double(rate.replacingOccurrences(of: ",", with: ".")) ?? 0
        if let t = editingTimer {
            await api.updateTimer(t.id, ["title": title, "hourly_rate": r, "currency": currency,
                                         "color": hex, "max_session_minutes": Int(maxMinutes) ?? 0])
            await onSaved(); dismiss(); return
        }
        if let c = editingCounter {
            await api.updateCounter(c.id, ["title": title, "price_per_unit": r,
                                           "currency": currency, "color": hex])
            await onSaved(); dismiss(); return
        }
        let ok: Bool
        if kind == 0 {
            ok = await api.createTimer(["title": title, "hourly_rate": r, "currency": currency, "color": hex,
                                        "max_session_minutes": Int(maxMinutes) ?? 0])
        } else {
            ok = await api.createCounter(["title": title, "price_per_unit": r, "currency": currency, "color": hex])
        }
        if ok { await onSaved(); dismiss() }
    }
}

/// "I worked but forgot to start the timer" — the phone's version of the Mac's
/// Log past time…. Pick the day and the two times; the Mac stores it as an
/// ordinary finished session.
private struct LogPastTimeSheet: View {
    @EnvironmentObject var api: APIClient
    @Environment(\.dismiss) private var dismiss
    let timer: WorkTimer
    var onSaved: () async -> Void

    @State private var day = Date()
    @State private var start = Calendar.current.date(bySettingHour: 9, minute: 0, second: 0, of: Date()) ?? Date()
    @State private var end = Calendar.current.date(bySettingHour: 10, minute: 0, second: 0, of: Date()) ?? Date()
    @State private var title = ""
    @State private var saving = false

    /// The two times are read on the chosen day, so a session never lands on
    /// today just because the pickers carry today's date component.
    private func combine(_ time: Date) -> Date {
        let cal = Calendar.current
        let d = cal.dateComponents([.year, .month, .day], from: day)
        let t = cal.dateComponents([.hour, .minute], from: time)
        return cal.date(from: DateComponents(year: d.year, month: d.month, day: d.day,
                                             hour: t.hour, minute: t.minute)) ?? time
    }

    private var seconds: Double { max(0, combine(end).timeIntervalSince(combine(start))) }

    var body: some View {
        NavigationView {
            Form {
                Section {
                    DatePicker("Day", selection: $day, displayedComponents: .date)
                    DatePicker("From", selection: $start, displayedComponents: .hourAndMinute)
                    DatePicker("To", selection: $end, displayedComponents: .hourAndMinute)
                    TextField("What were you doing? (optional)", text: $title)
                } footer: {
                    if seconds > 0 {
                        Text(TimerFormat.duration(seconds)
                             + (timer.hourlyRate > 0
                                ? " · " + TimerFormat.money(seconds / 3600 * timer.hourlyRate, timer.currency)
                                : ""))
                    } else {
                        Text("The end time has to be after the start time.").foregroundColor(.red)
                    }
                }
            }
            .navigationTitle("Log past time")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(saving ? "Saving…" : "Save") { Task { await save() } }
                        .disabled(saving || seconds <= 0)
                }
            }
        }
    }

    private func save() async {
        saving = true; defer { saving = false }
        if await api.logTimerSession(timer.id, start: combine(start), end: combine(end), title: title) {
            await onSaved()
            dismiss()
        }
    }
}

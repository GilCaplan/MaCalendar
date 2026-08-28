import SwiftUI
import UIKit

struct ContentView: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var settings: AppSettings
    @ObservedObject private var store = LocalStore.shared
    @Environment(\.scenePhase) private var scenePhase

    @State private var selectedTab = 0
    @State private var selectedDate = Date()
    @State private var viewedDate = Date()
    @State private var calendarView: CalendarMode = .month
    @State private var monthEvents: [CalendarEvent] = []
    @State private var monthHolidays: [Holiday] = []
    @State private var loadingMonth = false
    @State private var showCreateSheet = false
    @State private var showVocabOnboarding = false
    @State private var showVoiceQueue = false
    @ObservedObject private var importInbox = ImportInbox.shared
    @State private var sharedImportText: String? = nil
    @State private var unreviewed = 0
    @State private var showReview = false

    enum CalendarMode { case month, week, day }

    var body: some View {
        VStack(spacing: 0) {

            // Offline banner
            if !api.isOnline {
                HStack(spacing: 6) {
                    Image(systemName: "wifi.slash")
                    Text(store.pendingCount > 0
                         ? "Offline — \(store.pendingCount) change\(store.pendingCount == 1 ? "" : "s") pending sync"
                         : "Offline — changes saved locally")
                    Spacer()
                }
                .font(.caption.weight(.medium))
                .foregroundColor(.white)
                .padding(.horizontal, 14)
                .padding(.vertical, 7)
                .background(Color.orange)
            }

            // Voice commands parked because the Mac was away. Shown whether or
            // not we're online: while offline so you know it was kept, and after
            // reconnecting so you can see what it went on to do.
            if !store.pendingVoice.isEmpty {
                Button { showVoiceQueue = true } label: {
                    HStack(spacing: 8) {
                        Image(systemName: voiceQueueIcon)
                        Text(voiceQueueSummary).font(.footnote.weight(.medium))
                        Spacer()
                        Text("Show").font(.footnote.weight(.semibold))
                    }
                    .padding(.horizontal, 14).padding(.vertical, 8)
                    .background(Color.orange.opacity(0.20))
                    .foregroundColor(.primary)
                }
                .buttonStyle(.plain)
            }

            if unreviewed >= 5 {
                Button { showReview = true } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "checkmark.bubble")
                        Text("\(unreviewed) voice commands to review — was the assistant right?")
                            .font(.footnote.weight(.medium))
                        Spacer()
                        Text("Review").font(.footnote.weight(.semibold))
                    }
                    .padding(.horizontal, 14).padding(.vertical, 8)
                    .background(settings.accentColor.opacity(0.18))
                    .foregroundColor(.primary)
                }
                .buttonStyle(.plain)
            }

            TabView(selection: $selectedTab) {

                // ── Calendar Tab ──────────────────────────────────────────
                NavigationView {
                    VStack(spacing: 0) {

                        Picker("View", selection: $calendarView) {
                            Text("Month").tag(CalendarMode.month)
                            Text("Week").tag(CalendarMode.week)
                            Text("Day").tag(CalendarMode.day)
                        }
                        .pickerStyle(.segmented)
                        .padding(.horizontal)
                        .padding(.vertical, 8)

                        Divider()

                        TabView(selection: $calendarView) {

                            // ── Month ──
                            VStack(spacing: 0) {
                                HStack {
                                    Button { shiftMonth(-1) } label: {
                                        Image(systemName: "chevron.left")
                                    }
                                    Spacer()
                                    Text(monthTitle).font(.headline)
                                    Spacer()
                                    Button { shiftMonth(1) } label: {
                                        Image(systemName: "chevron.right")
                                    }
                                }
                                .padding(.horizontal)
                                .padding(.vertical, 8)

                                MonthGridView(
                                    year: Calendar.current.component(.year, from: viewedDate),
                                    month: Calendar.current.component(.month, from: viewedDate),
                                    selectedDate: $selectedDate,
                                    events: monthEvents,
                                    holidays: monthHolidays,
                                    onDateSelected: { date in viewedDate = date }
                                )
                                Spacer()
                            }
                            .tag(CalendarMode.month)
                            .task { await loadMonth() }
                            .onChange(of: viewedDate) { _ in Task { await loadMonth() } }
                            .onAppear { viewedDate = selectedDate }
                            // Vertical swipe to move a month, in addition to the
                            // chevron buttons. `simultaneousGesture` (rather than
                            // `gesture`) so it doesn't steal the horizontal swipe
                            // the outer page TabView uses to switch Month/Week/Day.
                            .simultaneousGesture(
                                DragGesture(minimumDistance: 24)
                                    .onEnded { value in
                                        let h = value.translation.height
                                        let w = value.translation.width
                                        guard abs(h) > abs(w) * 1.5, abs(h) > 40 else { return }
                                        withAnimation { shiftMonth(h < 0 ? 1 : -1) }
                                    }
                            )

                            // ── Week ──
                            VStack(spacing: 0) {
                                HStack {
                                    Button { shiftWeek(-1) } label: {
                                        Image(systemName: "chevron.left")
                                    }
                                    Spacer()
                                    Text(weekTitle).font(.headline)
                                    Spacer()
                                    Button { shiftWeek(1) } label: {
                                        Image(systemName: "chevron.right")
                                    }
                                }
                                .padding(.horizontal)
                                .padding(.vertical, 8)

                                WeekView(
                                    selectedDate: $selectedDate,
                                    events: monthEvents,
                                    holidays: monthHolidays,
                                    onDateSelected: { date in
                                        selectedDate = date
                                        viewedDate = date
                                        Task { await loadMonth() }
                                    }
                                )
                            }
                            .tag(CalendarMode.week)
                            .onAppear {
                                viewedDate = selectedDate
                                Task { await loadMonth() }
                            }

                            // ── Day ──
                            VStack(spacing: 0) {
                                HStack {
                                    Button { shiftDay(-1) } label: {
                                        Image(systemName: "chevron.left")
                                    }
                                    Spacer()
                                    Text(dayTitle).font(.headline)
                                    Spacer()
                                    Button { shiftDay(1) } label: {
                                        Image(systemName: "chevron.right")
                                    }
                                }
                                .padding(.horizontal)
                                .padding(.vertical, 8)

                                DayView(date: selectedDate)
                            }
                            .tag(CalendarMode.day)
                            .onAppear { viewedDate = selectedDate }

                        }
                        .tabViewStyle(.page(indexDisplayMode: .never))

                        Spacer(minLength: 0)
                    }
                    .navigationTitle("Calendar")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .navigationBarTrailing) {
                            Button("Today") {
                                selectedDate = Date()
                                viewedDate = Date()
                                Task { await loadMonth() }
                            }
                        }
                    }
                    .overlay(alignment: .bottom) {
                        HStack(spacing: 20) {
                            VoiceButton(onRefresh: { refresh in
                                if refresh == "events" || refresh == "both" {
                                    Task { await loadMonth() }
                                }
                            })

                            Button {
                                showCreateSheet = true
                            } label: {
                                Image(systemName: "plus")
                                    .font(.system(size: 24, weight: .bold))
                                    .foregroundColor(Color.onColor(hex: settings.accentColorHex))
                                    .frame(width: 60, height: 60)
                                    .background(settings.accentColor)
                                    .clipShape(Circle())
                                    .shadow(radius: 4)
                            }
                        }
                        .padding(.bottom, 24)
                    }
                }
                .tabItem { Label("Calendar", systemImage: "calendar") }
                .tag(0)

                // ── Tasks Tab ────────────────────────────────────────────
                TasksView()
                    .tabItem { Label("Tasks", systemImage: "checklist") }
                    .tag(1)

                // ── Coursework Tab ───────────────────────────────────────
                if settings.showCourseworkTab {
                    CourseworkView()
                        .tabItem { Label("Coursework", systemImage: "graduationcap") }
                        .tag(2)
                }

                // ── Workout Tab ──────────────────────────────────────────
                if settings.showWorkoutTab {
                    WorkoutView()
                        .tabItem { Label("Workout", systemImage: "figure.strengthtraining.traditional") }
                        .tag(4)
                }

                // ── Timer Tab ────────────────────────────────────────────
                if settings.showTimerTab {
                    TimerView()
                        .tabItem { Label("Timer", systemImage: "timer") }
                        .tag(5)
                }

                // ── Settings Tab ─────────────────────────────────────────
                SettingsView()
                    .tabItem { Label("Settings", systemImage: "gear") }
                    .tag(3)
            }
        }
        .sheet(isPresented: $showCreateSheet) {
            let year    = Calendar.current.component(.year,  from: selectedDate)
            let month   = Calendar.current.component(.month, from: selectedDate)
            let day     = Calendar.current.component(.day,   from: selectedDate)
            let dateStr = String(format: "%04d-%02d-%02d", year, month, day)

            EventDetailView(
                event: CalendarEvent(
                    id: 0, title: "", date: dateStr,
                    startTime: "10:00", endTime: "11:00",
                    attendees: "", location: "",
                    description: "", color: settings.accentColorHex,
                    recurrence: "", recurrenceEnd: ""
                ),
                isNew: true,
                onDismiss: { Task { await loadMonth() } }
            )
        }
        .onChange(of: settings.showCourseworkTab) { visible in
            // Bounce off the now-hidden tab so the user doesn't land on a
            // blank TabView page.
            if !visible && selectedTab == 2 { selectedTab = 0 }
        }
        .onChange(of: settings.showWorkoutTab) { visible in
            if !visible && selectedTab == 4 { selectedTab = 0 }
        }
        .onChange(of: scenePhase) { phase in
            if phase == .active {
                Task {
                    _ = await api.syncPending()
                    await api.syncPendingVoice()
                    // Always re-fetch on foreground: the Mac app may have changed things.
                    await loadMonth()
                    await refreshWorkoutIfNeeded()
                    api.requestRefresh()
                }
            }
        }
        .sheet(isPresented: $showVocabOnboarding) {
            VocabOnboardingView()
        }
        .sheet(isPresented: $showVoiceQueue) {
            VoiceQueueView()
        }
        .sheet(isPresented: $showReview, onDismiss: { Task { unreviewed = await api.unreviewedCount() } }) {
            AssistantReviewView()
        }
        .onReceive(importInbox.$pendingText) { t in
            if let t { sharedImportText = t; importInbox.pendingText = nil }
        }
        .sheet(isPresented: Binding(get: { sharedImportText != nil }, set: { if !$0 { sharedImportText = nil } })) {
            VocabImportView(initialText: sharedImportText, initialName: importInbox.pendingName)
        }
        .task {
            // First run: once the Mac is reachable and the vocabulary hasn't
            // been set up, ask the user to teach the assistant their words.
            if !settings.vocabOnboardingDone, !settings.serverURL.isEmpty,
               let ob = try? await api.vocabOnboarding(), !ob.done {
                showVocabOnboarding = true
            } else if let ob = try? await api.vocabOnboarding(), ob.done {
                settings.vocabOnboardingDone = true
            }

            unreviewed = await api.unreviewedCount()

            // Wire the Workout store up to the network layer once, so its
            // local mutations (saveTemplate, finishSession, etc.) can push
            // themselves to the server immediately — see WorkoutStore.configure.
            WorkoutStore.shared.configure(api: api)

            // While the app is open, retry sync every 30 s so pending
            // changes upload as soon as the Mac comes back online.
            var slept: TimeInterval = 0
            var sinceTokenCheck: TimeInterval = 0
            var lastToken: String? = nil
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                slept += 1
                sinceTokenCheck += 1

                // Between full refreshes, ask the Mac the cheap question: has
                // anything changed? A few bytes every 2 s beats waiting up to
                // 30 s to notice an event added on the other device.
                if sinceTokenCheck >= 2, slept < api.pollInterval,
                   UIApplication.shared.applicationState == .active {
                    sinceTokenCheck = 0
                    if let token = await api.changeToken() {
                        if let previous = lastToken, previous != token {
                            lastToken = token
                            slept = 0
                            await loadMonth()
                            api.requestRefresh()
                            continue
                        }
                        lastToken = token
                    }
                }

                guard slept >= api.pollInterval else { continue }
                slept = 0
                sinceTokenCheck = 0
                lastToken = await api.changeToken() ?? lastToken
                // Read the live application state, NOT the `scenePhase` environment
                // value: `.task` captures the View struct, so `scenePhase` here is
                // frozen at whatever it was when the task started — `.inactive`,
                // because the scene has not finished activating during the first
                // render. Guarding on that captured copy silently disabled this
                // whole loop, so nothing changed on the Mac ever reached the phone
                // until the app was backgrounded and reopened.
                guard UIApplication.shared.applicationState == .active else { continue }
                if !api.isOnline { _ = try? await api.health() }   // flips isOnline (+refresh) when the Mac is back
                _ = await api.syncPending()
                await api.syncPendingVoice()
                // Poll: keep the phone in step with whatever was changed on the Mac.
                await loadMonth()
                api.requestRefresh()
            }
        }
    }

    // MARK: - Helpers

    private var monthTitle: String {
        let f = DateFormatter()
        f.dateFormat = "MMMM yyyy"
        return f.string(from: viewedDate)
    }

    private var weekTitle: String {
        var cal = Calendar(identifier: .gregorian)
        cal.firstWeekday = 1
        let weekday = cal.component(.weekday, from: selectedDate) - 1
        guard let sunday   = cal.date(byAdding: .day, value: -weekday,    to: selectedDate),
              let saturday = cal.date(byAdding: .day, value: 6 - weekday, to: selectedDate) else { return "" }
        let f = DateFormatter()
        f.dateFormat = "MMM d"
        let year = Calendar.current.component(.year, from: sunday)
        return "\(f.string(from: sunday)) – \(f.string(from: saturday)), \(year)"
    }

    private var dayTitle: String {
        let f = DateFormatter()
        f.dateFormat = "EEEE, MMM d, yyyy"
        return f.string(from: selectedDate)
    }

    private func shiftMonth(_ delta: Int) {
        guard let d = Calendar.current.date(byAdding: .month, value: delta, to: viewedDate) else { return }
        viewedDate = d
    }

    private func shiftWeek(_ delta: Int) {
        guard let d = Calendar.current.date(byAdding: .day, value: delta * 7, to: selectedDate) else { return }
        selectedDate = d
        viewedDate = d
        Task { await loadMonth() }
    }

    private func shiftDay(_ delta: Int) {
        guard let d = Calendar.current.date(byAdding: .day, value: delta, to: selectedDate) else { return }
        selectedDate = d
        viewedDate = d
        Task { await loadMonth() }
    }

    private var voiceQueueIcon: String {
        if store.pendingVoice.contains(where: { $0.status == .running }) { return "waveform" }
        if store.pendingVoice.allSatisfy({ $0.status == .done }) { return "checkmark.circle" }
        return "mic.badge.plus"
    }

    private var voiceQueueSummary: String {
        let waiting = store.pendingVoice.filter { $0.status == .queued }.count
        let running = store.pendingVoice.filter { $0.status == .running }.count
        let failed  = store.pendingVoice.filter { $0.status == .failed }.count
        if running > 0 { return "Running a command you spoke while offline…" }
        if waiting > 0 {
            return "\(waiting) command\(waiting == 1 ? "" : "s") waiting for your Mac"
        }
        if failed > 0 { return "\(failed) queued command\(failed == 1 ? "" : "s") didn't run" }
        return "Your queued command\(store.pendingVoice.count == 1 ? "" : "s") ran"
    }

    private func loadMonth() async {
        let year  = Calendar.current.component(.year,  from: viewedDate)
        let month = Calendar.current.component(.month, from: viewedDate)
        loadingMonth = true

        let cal = Calendar.current
        let start = cal.date(from: DateComponents(year: year, month: month, day: 1)) ?? viewedDate
        let end = cal.date(byAdding: DateComponents(month: 1, day: -1), to: start) ?? start
        let showHolidays = settings.showHolidays
        let israel = settings.israelHolidays

        // Independent requests — run concurrently instead of paying the sum
        // of both latencies on every month navigation.
        async let eventsResult: [CalendarEvent] = (try? await api.eventsForMonth(year: year, month: month)) ?? []
        async let holidaysResult: [Holiday] = fetchHolidays(showHolidays: showHolidays, start: start, end: end, israel: israel)

        monthEvents = await eventsResult
        loadingMonth = false
        monthHolidays = await holidaysResult
    }

    private func fetchHolidays(showHolidays: Bool, start: Date, end: Date, israel: Bool) async -> [Holiday] {
        guard showHolidays else { return [] }
        return (try? await api.holidays(start: start, end: end, israel: israel)) ?? []
    }

    /// Mirrors `loadMonth()`'s role for events: pulls fresh exercises/templates/
    /// sessions after pending offline writes just flushed. WorkoutView's own
    /// `.task` handles the initial load when the tab is opened; this covers
    /// the background-refresh case so server-side changes (e.g. a routine
    /// generated on the Mac, or on another device) show up without requiring
    /// the user to leave and re-enter the Workout tab.
    private func refreshWorkoutIfNeeded() async {
        guard settings.showWorkoutTab else { return }
        _ = try? await api.workoutExercises()
        _ = try? await api.workoutTemplates(includeDrafts: false)
        _ = try? await api.workoutSessions(limit: 50)
    }
}

/// Voice commands recorded while the Mac was unreachable, and what became of
/// them. The Mac does the thinking, so nothing can run until it's back — this
/// is the "so where did my command go?" answer, alongside the notification that
/// fires when one finally runs.
struct VoiceQueueView: View {
    @ObservedObject private var store = LocalStore.shared
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var settings: AppSettings
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationView {
            List {
                Section {
                    Text(api.isOnline
                         ? "Your Mac is reachable — anything still waiting runs within a few seconds."
                         : "Your Mac isn't reachable. These are kept on this phone and run as soon as it is.")
                        .font(.footnote).foregroundColor(.secondary)
                }
                ForEach(store.pendingVoice) { cmd in
                    HStack(alignment: .top, spacing: 12) {
                        icon(for: cmd.status)
                            .frame(width: 22)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(label(for: cmd.status)).font(.subheadline.weight(.medium))
                            Text(cmd.recordedAt.formatted(date: .abbreviated, time: .shortened))
                                .font(.caption).foregroundColor(.secondary)
                            if !cmd.result.isEmpty {
                                Text(cmd.result).font(.footnote).foregroundColor(.secondary)
                            }
                        }
                    }
                    .padding(.vertical, 2)
                }
                .onDelete { idx in
                    for i in idx { store.removeVoice(store.pendingVoice[i].id) }
                }
            }
            .navigationTitle("Queued commands")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    if store.pendingVoice.contains(where: { $0.status == .done || $0.status == .failed }) {
                        Button("Clear finished") { store.clearFinishedVoice() }
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) { Button("Done") { dismiss() } }
            }
            .task { await api.syncPendingVoice() }
        }
    }

    @ViewBuilder
    private func icon(for status: PendingVoiceCommand.Status) -> some View {
        switch status {
        case .queued:  Image(systemName: "clock").foregroundColor(.orange)
        case .running: ProgressView()
        case .done:    Image(systemName: "checkmark.circle.fill").foregroundColor(.green)
        case .failed:  Image(systemName: "exclamationmark.triangle.fill").foregroundColor(.red)
        }
    }

    private func label(for status: PendingVoiceCommand.Status) -> String {
        switch status {
        case .queued:  return "Waiting for your Mac"
        case .running: return "Running now…"
        case .done:    return "Done"
        case .failed:  return "Didn't run"
        }
    }
}

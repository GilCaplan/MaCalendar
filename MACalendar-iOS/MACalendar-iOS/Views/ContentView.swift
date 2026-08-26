import SwiftUI

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
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 30_000_000_000)
                guard scenePhase == .active else { continue }
                if !api.isOnline { _ = try? await api.health() }   // flips isOnline (+refresh) when the Mac is back
                _ = await api.syncPending()
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

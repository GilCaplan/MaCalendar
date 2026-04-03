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
    @State private var loadingMonth = false
    @State private var showCreateSheet = false

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
                                    onDateSelected: { date in viewedDate = date }
                                )
                                Spacer()
                            }
                            .tag(CalendarMode.month)
                            .task { await loadMonth() }
                            .onChange(of: viewedDate) { _ in Task { await loadMonth() } }
                            .onAppear { viewedDate = selectedDate }

                            // ── Week ──
                            VStack(spacing: 0) {
                                WeekView(
                                    selectedDate: $selectedDate,
                                    events: monthEvents,
                                    onDateSelected: { date in viewedDate = date }
                                )
                                Spacer()
                            }
                            .tag(CalendarMode.week)
                            .onAppear { viewedDate = selectedDate }
                            .task { await loadMonth() }

                            // ── Day ──
                            DayView(date: selectedDate)
                                .tag(CalendarMode.day)
                        }
                        .tabViewStyle(.page(indexDisplayMode: .never))

                        Spacer(minLength: 0)
                    }
                    .navigationTitle("Calendar")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .navigationBarTrailing) {
                            Button("Today") { selectedDate = Date() }
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
                                    .foregroundColor(.white)
                                    .frame(width: 60, height: 60)
                                    .background(Color.blue)
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

                // ── Settings Tab ─────────────────────────────────────────
                SettingsView()
                    .tabItem { Label("Settings", systemImage: "gear") }
                    .tag(2)
            }
        }
        .sheet(isPresented: $showCreateSheet) {
            let year  = Calendar.current.component(.year, from: selectedDate)
            let month = Calendar.current.component(.month, from: selectedDate)
            let day   = Calendar.current.component(.day, from: selectedDate)
            let dateStr = String(format: "%04d-%02d-%02d", year, month, day)

            EventDetailView(
                event: CalendarEvent(
                    id: 0, title: "", date: dateStr,
                    startTime: "10:00", endTime: "11:00",
                    attendees: "", location: "",
                    description: "", color: "#007AFF",
                    recurrence: "", recurrenceEnd: ""
                ),
                isNew: true,
                onDismiss: { Task { await loadMonth() } }
            )
        }
        .onChange(of: scenePhase) { phase in
            if phase == .active {
                Task {
                    let synced = await api.syncPending()
                    if synced { await loadMonth() }
                }
            }
        }
        .task {
            // While the app is open, retry sync every 30s so pending
            // changes upload as soon as the Mac comes back online.
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 30_000_000_000)
                let synced = await api.syncPending()
                if synced { await loadMonth() }
            }
        }
    }

    // MARK: - Helpers

    private var monthTitle: String {
        let f = DateFormatter()
        f.dateFormat = "MMMM yyyy"
        return f.string(from: viewedDate)
    }

    private func shiftMonth(_ delta: Int) {
        guard let d = Calendar.current.date(byAdding: .month, value: delta, to: viewedDate) else { return }
        viewedDate = d
        // Day only switches selection if user explicitly taps in MonthGridView
    }

    private func loadMonth() async {
        let year  = Calendar.current.component(.year, from: viewedDate)
        let month = Calendar.current.component(.month, from: viewedDate)
        loadingMonth = true
        monthEvents = (try? await api.eventsForMonth(year: year, month: month)) ?? []
        loadingMonth = false
    }
}

import SwiftUI
import AVFoundation
import UIKit
import UserNotifications

struct SettingsView: View {
    @EnvironmentObject var settings: AppSettings
    @EnvironmentObject var api: APIClient
    @State private var healthStatus: String? = nil
    @State private var checking = false
    @State private var unreviewed = 0
    // Reminders: the server-side policy (nil until the Mac answers) and the
    // category list its per-category leads are rendered against.
    @State private var notifConfig: NotificationsConfig? = nil
    @State private var reminderCategories: [EventCategory] = []
    @State private var permStatus: UNAuthorizationStatus? = nil

    private let leadChoices = [5, 10, 15, 30, 60]
    @FocusState private var urlFocused: Bool
    @FocusState private var keyFocused: Bool

    private var validLanguages: [String] { voices.map(\.language) }

    private let voices: [(label: String, language: String)] = [
        ("Samantha (US)", "en-US"),
        ("Daniel (UK)",   "en-GB"),
        ("Karen (AU)",    "en-AU"),
    ]

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {

                    // MARK: Server
                    GroupBox(label: Label("Server", systemImage: "network")) {
                        VStack(spacing: 12) {
                            HStack {
                                TextField("http://100.x.x.x:8080", text: $settings.serverURL)
                                    .keyboardType(.URL)
                                    .autocorrectionDisabled()
                                    .textInputAutocapitalization(.never)
                                    .focused($urlFocused)
                                if !settings.serverURL.isEmpty {
                                    Button { settings.serverURL = "" } label: {
                                        Image(systemName: "xmark.circle.fill")
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                            .padding(10)
                            .background(Color(.systemBackground))
                            .cornerRadius(8)
                            .overlay(RoundedRectangle(cornerRadius: 8).stroke(urlFocused ? settings.accentColor : Color(.separator), lineWidth: 1))
                            .onTapGesture { urlFocused = true }

                            HStack {
                                TextField("API Key (optional)", text: $settings.apiKey)
                                    .autocorrectionDisabled()
                                    .textInputAutocapitalization(.never)
                                    .focused($keyFocused)
                                if !settings.apiKey.isEmpty {
                                    Button { settings.apiKey = "" } label: {
                                        Image(systemName: "xmark.circle.fill")
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                            .padding(10)
                            .background(Color(.systemBackground))
                            .cornerRadius(8)
                            .overlay(RoundedRectangle(cornerRadius: 8).stroke(keyFocused ? settings.accentColor : Color(.separator), lineWidth: 1))
                            .onTapGesture { keyFocused = true }

                            Button(action: checkHealth) {
                                HStack {
                                    Text("Test Connection")
                                    Spacer()
                                    if checking {
                                        ProgressView()
                                    } else if let s = healthStatus {
                                        Text(s)
                                            .foregroundColor(s.contains("✓") ? .green : .red)
                                            .font(.caption)
                                    }
                                }
                            }

                            Text("Your Mac's Tailscale IP — this Mac is 100.92.216.112 (the port 8080 and http:// are added for you)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding(.top, 4)
                    }

                    // MARK: Appearance
                    GroupBox(label: Label("Appearance", systemImage: "paintbrush")) {
                        VStack(alignment: .leading, spacing: 12) {
                            Picker("Theme", selection: $settings.theme) {
                                Text("Light").tag("light")
                                Text("Dark").tag("dark")
                            }
                            .pickerStyle(.segmented)

                            Divider().padding(.vertical, 4)

                            Label("Accent Color", systemImage: "paintpalette")
                            HStack(spacing: 10) {
                                ForEach(Theme.accentPresets, id: \.hex) { preset in
                                    Circle()
                                        .fill(Color(hex: preset.hex) ?? Theme.defaultAccent)
                                        .frame(width: 28, height: 28)
                                        .overlay(
                                            Circle()
                                                .stroke(Color.primary.opacity(settings.accentColorHex.caseInsensitiveCompare(preset.hex) == .orderedSame ? 1 : 0), lineWidth: 2)
                                                .padding(2)
                                        )
                                        .onTapGesture { settings.accentColorHex = preset.hex }
                                }
                                ColorPicker("", selection: Binding(
                                    get: { settings.accentColor },
                                    set: { newColor in settings.accentColorHex = newColor.hexString ?? settings.accentColorHex }
                                ))
                                .labelsHidden()
                                .frame(width: 28, height: 28)
                            }

                            Divider().padding(.vertical, 4)

                            HStack {
                                Label("Month Font", systemImage: "calendar")
                                Spacer()
                                Stepper("\(Int(settings.fontMonth))", value: $settings.fontMonth, in: 8...24)
                            }
                            HStack {
                                Label("Week Font", systemImage: "calendar.day.timeline.left")
                                Spacer()
                                Stepper("\(Int(settings.fontWeek))", value: $settings.fontWeek, in: 8...24)
                            }
                            HStack {
                                Label("Day Font", systemImage: "calendar.day.timeline.leading")
                                Spacer()
                                Stepper("\(Int(settings.fontDay))", value: $settings.fontDay, in: 10...30)
                            }
                            HStack {
                                Label("Tasks Font", systemImage: "checklist")
                                Spacer()
                                Stepper("\(Int(settings.fontTasks))", value: $settings.fontTasks, in: 10...30)
                            }
                        }
                        .padding(.vertical, 4)
                    }

                    // MARK: Hebrew Calendar
                    GroupBox(label: Label("Hebrew Calendar", systemImage: "calendar.badge.clock")) {
                        VStack(alignment: .leading, spacing: 12) {
                            Picker("Show dates as", selection: $settings.hebrewDisplayMode) {
                                Text("English").tag("english")
                                Text("Hebrew").tag("hebrew")
                                Text("Both").tag("both")
                            }
                            .pickerStyle(.segmented)

                            Toggle("Show Jewish / Israeli holidays", isOn: $settings.showHolidays)
                            Toggle("Israel holiday schedule", isOn: $settings.israelHolidays)
                                .disabled(!settings.showHolidays)

                            Text("Hebrew dates use gematria letters (e.g. כ״ט תשרי). Holidays begin at sundown the evening before their main day.")
                                .font(.caption)
                                .foregroundColor(.secondary)

                            Divider().padding(.vertical, 2)

                            Toggle("Sundown follows this device", isOn: $settings.followMyLocation)
                                .onChange(of: settings.followMyLocation) { on in
                                    if on {
                                        DeviceLocation.shared.refresh(using: api)
                                    } else {
                                        Task { try? await api.clearObservanceLocation() }
                                    }
                                }

                            Text(settings.followMyLocation
                                 ? "Candle lighting and nightfall are computed for wherever you are. Your position is sent to your own host and nowhere else, once, when it has moved far enough to matter."
                                 : "Sundown uses the place configured on your host. Turn this on when you travel — the same clock time falls on different sides of Shabbat in different places.")
                                .font(.caption)
                                .foregroundColor(.secondary)

                            if !DeviceLocation.shared.status.isEmpty {
                                Text(DeviceLocation.shared.status)
                                    .font(.caption2)
                                    .foregroundColor(settings.accentColor)
                            }
                        }
                        .padding(.top, 4)
                    }

                    // MARK: Reminders
                    GroupBox(label: Label("Reminders", systemImage: "bell.badge")) {
                        VStack(alignment: .leading, spacing: 12) {
                            Toggle(isOn: $settings.remindersEnabled) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Remind before events")
                                    Text("This phone is the reliable ringer — it rings even when the Mac is asleep. What fires when is decided on the Mac.")
                                        .font(.caption).foregroundColor(.secondary)
                                }
                            }
                            .onChange(of: settings.remindersEnabled) { on in
                                if on { Task { permStatus = await NotificationPermission.request() } }
                                ReminderScheduler.shared.reconcile()
                            }

                            permissionRow

                            Divider()

                            HStack {
                                Text("Default lead time")
                                Spacer()
                                Menu {
                                    Button("Off") { setDefaultLead(0) }
                                    ForEach(leadChoices, id: \.self) { m in
                                        Button("\(m) min before") { setDefaultLead(m) }
                                    }
                                } label: {
                                    Text(leadLabel(notifConfig?.defaultLeadMinutes))
                                }
                                .disabled(notifConfig == nil)
                            }
                            Text("Off = opt-in only: reminders fire only where an event or a category asks for one.")
                                .font(.caption).foregroundColor(.secondary)

                            Toggle("Quiet on Shabbat & chagim", isOn: Binding(
                                get: { notifConfig?.respectObservance ?? true },
                                set: { on in
                                    notifConfig?.respectObservance = on
                                    Task {
                                        await api.patchNotifications(["respect_observance": on])
                                        await refreshReminderVerdicts()
                                    }
                                }))
                                .disabled(notifConfig == nil)
                            Text("Holds reminders through Shabbat and yom tov, candle lighting to nightfall — computed on your Mac, never by the clock date alone.")
                                .font(.caption).foregroundColor(.secondary)

                            if notifConfig != nil && !reminderCategories.isEmpty {
                                Divider()
                                Text("Per category").font(.subheadline.weight(.semibold))
                                ForEach(reminderCategories) { c in
                                    HStack(spacing: 10) {
                                        Circle().fill(Color(hex: c.color) ?? .gray)
                                            .frame(width: 12, height: 12)
                                        Text(c.name)
                                        Spacer()
                                        Menu {
                                            Button("Default") { setCategoryLead(c.name, nil) }
                                            Button("Off") { setCategoryLead(c.name, 0) }
                                            ForEach(leadChoices, id: \.self) { m in
                                                Button("\(m) min before") { setCategoryLead(c.name, m) }
                                            }
                                        } label: {
                                            Text(categoryLeadLabel(c.name))
                                        }
                                    }
                                }
                                Text("Off mutes the whole category — its events never ring unless one asks by itself.")
                                    .font(.caption).foregroundColor(.secondary)
                            }

                            if notifConfig == nil {
                                Text("Lead times live on your Mac — it isn't reachable right now.")
                                    .font(.caption).foregroundColor(.orange)
                            }
                        }
                        .padding(.top, 4)
                    }

                    // MARK: Tabs
                    GroupBox(label: Label("Tabs", systemImage: "square.grid.2x2")) {
                        VStack(alignment: .leading, spacing: 8) {
                            Toggle("Show Coursework Tab", isOn: $settings.showCourseworkTab)
                            Toggle("Show Workout Tab", isOn: $settings.showWorkoutTab)
                            Toggle("Show Timer Tab", isOn: $settings.showTimerTab)
                        }
                    }
                    .padding(.top, 4)

                    // MARK: Voice
                    GroupBox(label: Label("Voice", systemImage: "speaker.wave.2")) {
                        VStack(alignment: .leading, spacing: 12) {
                            Toggle(isOn: $settings.speakReplies) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Speak replies aloud")
                                    Text("Reads the result of each command. Off = silent, the text still shows in the thinking sheet.")
                                        .font(.caption).foregroundColor(.secondary)
                                }
                            }
                            Picker("TTS Voice", selection: $settings.ttsVoice) {
                                ForEach(voices, id: \.language) { v in
                                    Text(v.label).tag(v.language)
                                }
                            }
                            .pickerStyle(.segmented)
                            .disabled(!settings.speakReplies)

                            Divider()

                            Toggle(isOn: $settings.stopWordsEnabled) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Stop on “execute”")
                                    Text("Say execute / done / submit / confirm and the recording ends by itself (on-device, like the Mac)")
                                        .font(.caption).foregroundColor(.secondary)
                                }
                            }
                            Toggle("Ask before sending (Redo / Add more)", isOn: $settings.reviewBeforeSend)
                            Text("After the recording stops you get 4 seconds to redo it or keep talking before it is sent.")
                                .font(.caption).foregroundColor(.secondary)
                            Toggle("Stop automatically after silence", isOn: $settings.silenceStopEnabled)
                            HStack {
                                Text("Auto-stop after silence")
                                Spacer()
                                Text("\(Int(settings.silenceStopSeconds)) s").font(.caption.monospacedDigit()).foregroundColor(.secondary)
                            }
                            Slider(value: $settings.silenceStopSeconds, in: 2...12, step: 1).disabled(!settings.silenceStopEnabled)

                            Toggle(isOn: $settings.showThinking) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Show assistant thinking")
                                    Text("Live step-by-step log while a command runs")
                                        .font(.caption).foregroundColor(.secondary)
                                }
                            }

                            NavigationLink {
                                AssistantReviewView()
                            } label: {
                                HStack {
                                    Label("Review commands", systemImage: "checkmark.bubble")
                                    Spacer()
                                    if unreviewed > 0 {
                                        Text("\(unreviewed)")
                                            .font(.caption.weight(.semibold))
                                            .padding(.horizontal, 7).padding(.vertical, 2)
                                            .background(settings.accentColor.opacity(0.2))
                                            .foregroundColor(settings.accentColor)
                                            .clipShape(Capsule())
                                    } else {
                                        Text("Was it right? Tap yes or no").font(.caption).foregroundColor(.secondary)
                                    }
                                    Image(systemName: "chevron.right").font(.caption).foregroundColor(.secondary)
                                }
                            }

                            NavigationLink {
                                VocabularyView()
                            } label: {
                                HStack {
                                    Label("Vocabulary", systemImage: "character.book.closed")
                                    Spacer()
                                    Text("Names & words it should know")
                                        .font(.caption).foregroundColor(.secondary)
                                    Image(systemName: "chevron.right")
                                        .font(.caption).foregroundColor(.secondary)
                                }
                            }

                            NavigationLink {
                                CategoriesView()
                            } label: {
                                HStack {
                                    Label("Event colours", systemImage: "paintpalette")
                                    Spacer()
                                    Text("Categories & colours")
                                        .font(.caption).foregroundColor(.secondary)
                                    Image(systemName: "chevron.right")
                                        .font(.caption).foregroundColor(.secondary)
                                }
                            }
                        }
                        .padding(.vertical, 4)
                    }

                    // MARK: About
                    GroupBox(label: Label("About", systemImage: "info.circle")) {
                        HStack {
                            Text("Version")
                            Spacer()
                            Text("1.0").foregroundColor(.secondary)
                        }
                        Divider()
                        Link("GitHub", destination: URL(string: "https://github.com/GilCaplan/MACalendar")!)
                    }
                }
                .padding()
            }
            .navigationTitle("Settings")
            .onAppear {
                if !validLanguages.contains(settings.ttsVoice) {
                    settings.ttsVoice = "en-US"
                }
                Task { unreviewed = await api.unreviewedCount() }
                Task {
                    permStatus = await NotificationPermission.status()
                    notifConfig = try? await api.notificationsConfig()
                    reminderCategories = (try? await api.categories()) ?? []
                }
            }
        }
    }

    // MARK: - Reminders helpers

    @ViewBuilder
    private var permissionRow: some View {
        switch permStatus {
        case .some(.notDetermined):
            Button {
                Task { permStatus = await NotificationPermission.request() }
            } label: {
                Label("Allow notifications", systemImage: "bell")
            }
        case .some(.denied):
            // iOS never re-prompts a denied app — the system Settings page
            // is the only way back.
            Button {
                if let url = URL(string: UIApplication.openSettingsURLString) {
                    UIApplication.shared.open(url)
                }
            } label: {
                Label("Notifications are off — open iOS Settings", systemImage: "bell.slash")
                    .foregroundColor(.orange)
            }
        case .some:
            Label("Notifications allowed", systemImage: "checkmark.circle")
                .font(.callout).foregroundColor(.green)
        case .none:
            EmptyView()
        }
    }

    private func leadLabel(_ v: Int?) -> String {
        guard let v else { return "—" }
        return v == 0 ? "Off" : "\(v) min"
    }

    private func categoryLeadLabel(_ name: String) -> String {
        guard let leads = notifConfig?.categoryLeads else { return "—" }
        guard let v = leads[name] else { return "Default" }
        return v == 0 ? "Off" : "\(v) min"
    }

    private func setDefaultLead(_ v: Int) {
        notifConfig?.defaultLeadMinutes = v
        Task {
            await api.patchNotifications(["default_lead_minutes": v])
            if v > 0 { NotificationPermission.requestIfNeeded() }
            await refreshReminderVerdicts()
        }
    }

    private func setCategoryLead(_ name: String, _ v: Int?) {
        guard var cfg = notifConfig else { return }
        if let v { cfg.categoryLeads[name] = v } else { cfg.categoryLeads.removeValue(forKey: name) }
        notifConfig = cfg
        Task {
            // PATCH /config merges at the section level, so the map goes whole.
            await api.patchNotifications(["category_leads": cfg.categoryLeads])
            if (v ?? 0) > 0 { NotificationPermission.requestIfNeeded() }
            await refreshReminderVerdicts()
        }
    }

    /// A policy edit changes every event's notify_at, but only on the Mac —
    /// and a config write doesn't move the /changes token. Re-fetch the
    /// current month so the cache (and, via cacheEvents → reconcile, the
    /// scheduled notifications) pick the new verdicts up now, not on the
    /// next event edit.
    private func refreshReminderVerdicts() async {
        let now = Date()
        _ = try? await api.eventsForMonth(year: Calendar.current.component(.year, from: now),
                                          month: Calendar.current.component(.month, from: now))
    }

    private func checkHealth() {
        urlFocused = false
        keyFocused = false
        checking = true
        healthStatus = nil
        Task {
            do {
                let h = try await api.health()
                healthStatus = "✓ \(h.llm)"
            } catch {
                healthStatus = "✗ \(error.localizedDescription) — \(settings.serverURL.isEmpty ? "no server URL set" : settings.serverURL)"
            }
            checking = false
        }
    }
}

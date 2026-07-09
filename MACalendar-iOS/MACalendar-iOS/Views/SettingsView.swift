import SwiftUI
import AVFoundation

struct SettingsView: View {
    @EnvironmentObject var settings: AppSettings
    @EnvironmentObject var api: APIClient
    @State private var healthStatus: String? = nil
    @State private var checking = false
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

                            Text("Your Mac's Tailscale IP, e.g. http://100.64.0.1:8080")
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
                    GroupBox(label: Label("Hebrew Calendar", systemImage: "star.of.david")) {
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
                        }
                        .padding(.top, 4)
                    }

                    // MARK: Voice
                    GroupBox(label: Label("Voice", systemImage: "speaker.wave.2")) {
                        Picker("TTS Voice", selection: $settings.ttsVoice) {
                            ForEach(voices, id: \.language) { v in
                                Text(v.label).tag(v.language)
                            }
                        }
                        .pickerStyle(.segmented)
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
            }
        }
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
                healthStatus = "✗ \(error.localizedDescription)"
            }
            checking = false
        }
    }
}

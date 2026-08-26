import SwiftUI

@main
struct MACalendarApp: App {
    @StateObject private var settings = AppSettings()
    @StateObject private var api: APIClient

    init() {
        let s = AppSettings()
        _settings = StateObject(wrappedValue: s)
        _api = StateObject(wrappedValue: APIClient(settings: s))
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(settings)
                .environmentObject(api)
                .preferredColorScheme(settings.theme == "dark" ? .dark : .light)
                .tint(settings.accentColor)
                .onOpenURL { url in
                    // A .txt shared from WhatsApp ("Export Chat" → MACalendar) lands here.
                    let accessed = url.startAccessingSecurityScopedResource()
                    defer { if accessed { url.stopAccessingSecurityScopedResource() } }
                    guard let data = try? Data(contentsOf: url) else { return }
                    let text = String(data: data, encoding: .utf8) ?? String(data: data, encoding: .isoLatin1) ?? ""
                    guard !text.isEmpty else { return }
                    ImportInbox.shared.pendingName = url.lastPathComponent
                    ImportInbox.shared.pendingText = text
                    try? FileManager.default.removeItem(at: url)   // don't keep the chat around
                }
        }
    }
}

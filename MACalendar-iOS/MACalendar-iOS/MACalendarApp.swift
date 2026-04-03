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
        }
    }
}

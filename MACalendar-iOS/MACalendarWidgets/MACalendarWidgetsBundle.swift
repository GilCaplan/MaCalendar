import SwiftUI
import WidgetKit

/// Entry point of the widget extension.
///
/// Two widgets, fed two different ways, deliberately:
///
///   • `UpNextLiveActivity` — the lock-screen card. The app *pushes* it
///     content; it draws nothing it was not handed.
///   • `UpNextHomeWidget` — the home-screen widget. It *pulls*, from the JSON
///     snapshot the app mirrors into the shared App Group container, and its
///     timeline carries future-dated entries so it advances on its own.
///
/// Still no asset catalog: everything either target draws is a system colour
/// or a hex the app resolved.
@main
struct MACalendarWidgetsBundle: WidgetBundle {
    var body: some Widget {
        UpNextLiveActivity()
        UpNextHomeWidget()
    }
}

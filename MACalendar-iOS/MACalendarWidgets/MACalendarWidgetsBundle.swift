import SwiftUI
import WidgetKit

/// Entry point of the widget extension.
///
/// The bundle carries only the "Up Next" Live Activity today — there are no
/// home-screen widgets, and no asset catalog, deliberately: the extension stays
/// as small as it can be, and everything it draws is handed to it by the app.
@main
struct MACalendarWidgetsBundle: WidgetBundle {
    var body: some Widget {
        UpNextLiveActivity()
    }
}

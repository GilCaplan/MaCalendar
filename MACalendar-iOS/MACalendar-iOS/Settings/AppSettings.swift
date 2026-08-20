import Foundation
import Combine
import SwiftUI

class AppSettings: ObservableObject {
    @Published var serverURL: String {
        didSet { UserDefaults.standard.set(serverURL, forKey: "serverURL") }
    }
    @Published var apiKey: String {
        didSet { UserDefaults.standard.set(apiKey, forKey: "apiKey") }
    }
    @Published var ttsVoice: String {
        didSet { UserDefaults.standard.set(ttsVoice, forKey: "ttsVoice") }
    }
    @Published var theme: String {
        didSet { UserDefaults.standard.set(theme, forKey: "userTheme") }
    }
    @Published var accentColorHex: String {
        didSet { UserDefaults.standard.set(accentColorHex, forKey: "accentColorHex") }
    }
    var accentColor: Color { Color(hex: accentColorHex) ?? Theme.defaultAccent }

    @Published var fontMonth: Double {
        didSet { UserDefaults.standard.set(fontMonth, forKey: "fontMonth") }
    }
    @Published var fontWeek: Double {
        didSet { UserDefaults.standard.set(fontWeek, forKey: "fontWeek") }
    }
    @Published var fontDay: Double {
        didSet { UserDefaults.standard.set(fontDay, forKey: "fontDay") }
    }
    @Published var fontTasks: Double {
        didSet { UserDefaults.standard.set(fontTasks, forKey: "fontTasks") }
    }

    // Hebrew calendar — local-only, mirrors the Mac's config.yaml options but
    // isn't synced from it (same precedent as the font settings above).
    @Published var hebrewDisplayMode: String {
        didSet { UserDefaults.standard.set(hebrewDisplayMode, forKey: "hebrewDisplayMode") }
    }
    @Published var showHolidays: Bool {
        didSet { UserDefaults.standard.set(showHolidays, forKey: "showHolidays") }
    }
    @Published var israelHolidays: Bool {
        didSet { UserDefaults.standard.set(israelHolidays, forKey: "israelHolidays") }
    }

    // Local-only, mirrors the Mac's config.yaml `todo.show_completed` (default
    // off) but isn't synced from it — same precedent as the Hebrew settings
    // above. Unlike Mac, which only exposes this via config.yaml, iOS gets an
    // in-app toggle (TasksView toolbar) since editing a config file on a
    // phone isn't practical.
    @Published var hideCompletedTasks: Bool {
        didSet { UserDefaults.standard.set(hideCompletedTasks, forKey: "hideCompletedTasks") }
    }

    // Same pattern as hideCompletedTasks above, applied to Coursework assignments.
    @Published var hideCompletedAssignments: Bool {
        didSet { UserDefaults.standard.set(hideCompletedAssignments, forKey: "hideCompletedAssignments") }
    }

    // Local-only, mirrors the Mac's config.yaml `ui.show_coursework` (default
    // on) but isn't synced from it — same precedent as the settings above.
    @Published var showCourseworkTab: Bool {
        didSet { UserDefaults.standard.set(showCourseworkTab, forKey: "showCourseworkTab") }
    }

    // Same pattern as showCourseworkTab above, for the local-only Workout tab.
    @Published var showWorkoutTab: Bool {
        didSet { UserDefaults.standard.set(showWorkoutTab, forKey: "showWorkoutTab") }
    }

    init() {
        self.serverURL = UserDefaults.standard.string(forKey: "serverURL") ?? ""
        self.apiKey    = UserDefaults.standard.string(forKey: "apiKey") ?? ""
        self.ttsVoice  = UserDefaults.standard.string(forKey: "ttsVoice") ?? "en-US"
        self.theme     = UserDefaults.standard.string(forKey: "userTheme") ?? "dark"
        self.accentColorHex = UserDefaults.standard.string(forKey: "accentColorHex") ?? Theme.defaultAccentHex

        let fm = UserDefaults.standard.double(forKey: "fontMonth")
        self.fontMonth = fm == 0 ? 13 : fm
        
        let fw = UserDefaults.standard.double(forKey: "fontWeek")
        self.fontWeek  = fw == 0 ? 13 : fw
        
        let fd = UserDefaults.standard.double(forKey: "fontDay")
        self.fontDay   = fd == 0 ? 15 : fd
        
        let ft = UserDefaults.standard.double(forKey: "fontTasks")
        self.fontTasks = ft == 0 ? 16 : ft

        self.hebrewDisplayMode = UserDefaults.standard.string(forKey: "hebrewDisplayMode") ?? "both"
        self.showHolidays = UserDefaults.standard.object(forKey: "showHolidays") == nil
            ? true : UserDefaults.standard.bool(forKey: "showHolidays")
        self.israelHolidays = UserDefaults.standard.object(forKey: "israelHolidays") == nil
            ? true : UserDefaults.standard.bool(forKey: "israelHolidays")

        self.hideCompletedTasks = UserDefaults.standard.object(forKey: "hideCompletedTasks") == nil
            ? true : UserDefaults.standard.bool(forKey: "hideCompletedTasks")

        self.hideCompletedAssignments = UserDefaults.standard.object(forKey: "hideCompletedAssignments") == nil
            ? true : UserDefaults.standard.bool(forKey: "hideCompletedAssignments")

        self.showCourseworkTab = UserDefaults.standard.object(forKey: "showCourseworkTab") == nil
            ? true : UserDefaults.standard.bool(forKey: "showCourseworkTab")

        self.showWorkoutTab = UserDefaults.standard.object(forKey: "showWorkoutTab") == nil
            ? true : UserDefaults.standard.bool(forKey: "showWorkoutTab")
    }
}

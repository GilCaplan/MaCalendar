import Foundation
import Combine

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

    init() {
        self.serverURL = UserDefaults.standard.string(forKey: "serverURL") ?? ""
        self.apiKey    = UserDefaults.standard.string(forKey: "apiKey") ?? ""
        self.ttsVoice  = UserDefaults.standard.string(forKey: "ttsVoice") ?? "en-US"
        self.theme     = UserDefaults.standard.string(forKey: "userTheme") ?? "dark"
        
        let fm = UserDefaults.standard.double(forKey: "fontMonth")
        self.fontMonth = fm == 0 ? 13 : fm
        
        let fw = UserDefaults.standard.double(forKey: "fontWeek")
        self.fontWeek  = fw == 0 ? 13 : fw
        
        let fd = UserDefaults.standard.double(forKey: "fontDay")
        self.fontDay   = fd == 0 ? 15 : fd
        
        let ft = UserDefaults.standard.double(forKey: "fontTasks")
        self.fontTasks = ft == 0 ? 16 : ft
    }
}

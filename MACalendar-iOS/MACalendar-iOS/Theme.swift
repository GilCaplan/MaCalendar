import SwiftUI
import UIKit

/// Shared design tokens — mirrors the Mac app's "Moody Dev-tool" system
/// (near-black surfaces via the native dark color scheme, a single
/// user-configurable accent, sharp/compact shapes). Backgrounds/text lean on
/// iOS's own semantic colors (systemBackground, .separator, .secondary, …)
/// since those already adapt correctly to dark mode and accessibility
/// settings; only the accent is custom.
enum Theme {
    static let defaultAccentHex = "#F5A524"
    static var defaultAccent: Color { Color(hex: defaultAccentHex)! }

    /// Presets offered in the Settings accent-color swatch picker.
    static let accentPresets: [(name: String, hex: String)] = [
        ("Amber",  "#F5A524"),
        ("Indigo", "#6F68F0"),
        ("Teal",   "#2DD4BF"),
        ("Coral",  "#E0714F"),
        ("Blue",   "#3B93FF"),
        ("Pink",   "#D6409F"),
        ("Green",  "#2FAE5C"),
    ]

    // Sharp/compact corner radii for custom-drawn shapes (event blocks,
    // pills), matching the density chosen on the Mac app.
    static let radiusSM: CGFloat = 4
    static let radiusMD: CGFloat = 8
}

extension Color {
    /// Legible foreground color (near-black warm, or white) for text/icons
    /// placed on top of a background given as a hex string. Falls back to
    /// white if the hex can't be parsed, matching prior unconditional-white
    /// behavior for callers that always pass a valid color.
    static func onColor(hex: String) -> Color {
        let h = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard h.count == 6, let wren = UInt64(h, radix: 16) else { return .white }
        func lin(_ c: Double) -> Double { c <= 0.03928 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4) }
        let r = Double((wren >> 16) & 0xFF) / 255
        let g = Double((wren >> 8) & 0xFF) / 255
        let b = Double(wren & 0xFF) / 255
        let lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
        return lum > 0.42 ? (Color(hex: "#15100A") ?? .black) : .white
    }

    /// Hex string ("#RRGGBB") for a concrete color, e.g. one picked via
    /// SwiftUI's native ColorPicker. Nil if the color can't be resolved to
    /// sRGB components (shouldn't happen for picker output).
    var hexString: String? {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        guard UIColor(self).getRed(&r, green: &g, blue: &b, alpha: &a) else { return nil }
        return String(format: "#%02X%02X%02X", Int(r * 255), Int(g * 255), Int(b * 255))
    }
}

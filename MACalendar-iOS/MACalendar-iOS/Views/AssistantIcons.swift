import SwiftUI

/// Shared glyph set — mirrors the Mac app's hand-authored SVGs in
/// `assistant/calendar_ui/icons/*.svg`: same 24x24 grid, same shapes, same
/// 1.75pt-equivalent rounded stroke. Drawn natively with SwiftUI `Path` so
/// iOS needs no image assets and every glyph tints with
/// `.foregroundColor`/`.tint` like a font glyph would.
enum AssistantIconName {
    case heard, vocab, rule, memory, llm, validate, execute, verify, done, error
    case iphone, mac, corrected, rejected, approved, thumbsUp, thumbsDown, pending, retry, question
}

/// One glyph. Usage: `AssistantIcon(.heard)`, `AssistantIcon(.done, size: 20)`.
struct AssistantIcon: View {
    let name: AssistantIconName
    var size: CGFloat = 16
    var strokeWidth: CGFloat = 1.75

    init(_ name: AssistantIconName, size: CGFloat = 16, strokeWidth: CGFloat = 1.75) {
        self.name = name
        self.size = size
        self.strokeWidth = strokeWidth
    }

    var body: some View {
        ZStack {
            _AssistantIconFill(name: name)
            _AssistantIconStroke(name: name)
                .stroke(style: StrokeStyle(lineWidth: strokeWidth * (size / 24), lineCap: .round, lineJoin: .round))
        }
        .frame(width: size, height: size)
    }
}

/// The stroked ("outline") portion of a glyph — most of the set.
private struct _AssistantIconStroke: Shape {
    let name: AssistantIconName

    func path(in rect: CGRect) -> Path {
        let g = _Grid(rect)
        var path = Path()
        switch name {
        case .heard:
            for (x, y0, y1) in [(4.0, 10.0, 14.0), (8.0, 6.0, 18.0), (12.0, 3.0, 21.0), (16.0, 7.0, 17.0), (20.0, 10.0, 14.0)] {
                path.move(to: g.pt(x, y0)); path.addLine(to: g.pt(x, y1))
            }
        case .vocab:
            path.move(to: g.pt(12, 19.7))
            path.addCurve(to: g.pt(5.5, 17.7), control1: g.pt(10.4, 19), control2: g.pt(8.1, 17.7))
            path.addLine(to: g.pt(3, 18))
            path.addLine(to: g.pt(3, 4.6))
            path.addCurve(to: g.pt(5.5, 4.3), control1: g.pt(3, 4.4), control2: g.pt(4.2, 4.3))
            path.addCurve(to: g.pt(12, 6.3), control1: g.pt(8.1, 4.3), control2: g.pt(10.4, 5))
            path.move(to: g.pt(12, 19.7))
            path.addCurve(to: g.pt(18.5, 17.7), control1: g.pt(13.6, 19), control2: g.pt(15.9, 17.7))
            path.addLine(to: g.pt(21, 18))
            path.addLine(to: g.pt(21, 4.6))
            path.addCurve(to: g.pt(18.5, 4.3), control1: g.pt(21, 4.4), control2: g.pt(19.8, 4.3))
            path.addCurve(to: g.pt(12, 6.3), control1: g.pt(15.9, 4.3), control2: g.pt(13.6, 5))
            path.move(to: g.pt(12, 6.3)); path.addLine(to: g.pt(12, 19.7))
        case .memory:
            path.addEllipse(in: g.rect(cx: 6, cy: 7, r: 2))
            path.addEllipse(in: g.rect(cx: 18, cy: 7, r: 2))
            path.addEllipse(in: g.rect(cx: 12, cy: 17, r: 2))
            path.move(to: g.pt(7.7, 8.3)); path.addLine(to: g.pt(10.4, 15.6))
            path.move(to: g.pt(16.3, 8.3)); path.addLine(to: g.pt(13.6, 15.6))
            path.move(to: g.pt(8, 7)); path.addLine(to: g.pt(16, 7))
        case .validate:
            path.move(to: g.pt(12, 3)); path.addLine(to: g.pt(19, 6)); path.addLine(to: g.pt(19, 11))
            path.addCurve(to: g.pt(12, 21), control1: g.pt(19, 16), control2: g.pt(16, 19.5))
            path.addCurve(to: g.pt(5, 11), control1: g.pt(8, 19.5), control2: g.pt(5, 16))
            path.addLine(to: g.pt(5, 6)); path.closeSubpath()
            path.move(to: g.pt(9, 12)); path.addLine(to: g.pt(11, 14)); path.addLine(to: g.pt(15, 10))
        case .execute:
            path.addEllipse(in: g.rect(cx: 12, cy: 12, r: 3))
            let ticks: [(Double, Double, Double, Double)] = [
                (12, 3, 12, 5.6), (12, 18.4, 12, 21), (21, 12, 18.4, 12), (5.6, 12, 3, 12),
                (18.4, 5.6, 16.6, 7.4), (7.4, 16.6, 5.6, 18.4), (18.4, 18.4, 16.6, 16.6), (7.4, 7.4, 5.6, 5.6),
            ]
            for (x0, y0, x1, y1) in ticks { path.move(to: g.pt(x0, y0)); path.addLine(to: g.pt(x1, y1)) }
        case .verify:
            path.addEllipse(in: g.rect(cx: 10, cy: 10, r: 6))
            path.move(to: g.pt(14.5, 14.5)); path.addLine(to: g.pt(20, 20))
            path.move(to: g.pt(7.3, 10.2)); path.addLine(to: g.pt(9.1, 12)); path.addLine(to: g.pt(13, 8))
        case .done:
            path.move(to: g.pt(6, 21)); path.addLine(to: g.pt(6, 3))
        case .error:
            path.move(to: g.pt(12, 3)); path.addLine(to: g.pt(22, 20)); path.addLine(to: g.pt(2, 20)); path.closeSubpath()
            path.move(to: g.pt(12, 9)); path.addLine(to: g.pt(12, 14))
        case .iphone:
            path.addRoundedRect(in: g.rect(x: 7, y: 2, w: 10, h: 20), cornerSize: g.size(2, 2))
            path.move(to: g.pt(11, 19)); path.addLine(to: g.pt(13, 19))
        case .mac:
            path.addRoundedRect(in: g.rect(x: 4, y: 4, w: 16, h: 11), cornerSize: g.size(1.2, 1.2))
        case .corrected:
            path.move(to: g.pt(4, 20)); path.addLine(to: g.pt(5, 16)); path.addLine(to: g.pt(16, 5))
            path.addLine(to: g.pt(19, 8)); path.addLine(to: g.pt(8, 19)); path.closeSubpath()
            path.move(to: g.pt(14, 7)); path.addLine(to: g.pt(17, 10))
        case .rejected:
            path.move(to: g.pt(4, 7)); path.addLine(to: g.pt(20, 7))
            path.move(to: g.pt(9, 7)); path.addLine(to: g.pt(9, 4)); path.addLine(to: g.pt(15, 4)); path.addLine(to: g.pt(15, 7))
            path.move(to: g.pt(6, 7)); path.addLine(to: g.pt(7, 20)); path.addLine(to: g.pt(17, 20)); path.addLine(to: g.pt(18, 7))
            path.move(to: g.pt(10, 11)); path.addLine(to: g.pt(10, 17))
            path.move(to: g.pt(14, 11)); path.addLine(to: g.pt(14, 17))
        case .approved:
            path.addEllipse(in: g.rect(cx: 12, cy: 12, r: 9))
            path.move(to: g.pt(8, 12.5)); path.addLine(to: g.pt(10.5, 15)); path.addLine(to: g.pt(16, 9.5))
        case .thumbsUp:
            path.move(to: g.pt(8, 21)); path.addLine(to: g.pt(8, 10))
            path.move(to: g.pt(8, 10)); path.addLine(to: g.pt(11.5, 3.5))
            path.addCurve(to: g.pt(13.8, 3.3), control1: g.pt(12, 2.6), control2: g.pt(13.2, 2.5))
            path.addCurve(to: g.pt(14.1, 5.1), control1: g.pt(14.2, 3.8), control2: g.pt(14.3, 4.5))
            path.addLine(to: g.pt(13, 9)); path.addLine(to: g.pt(18.5, 9))
            path.addCurve(to: g.pt(20.1, 11.1), control1: g.pt(19.6, 9), control2: g.pt(20.4, 10))
            path.addLine(to: g.pt(18.3, 18.6))
            path.addCurve(to: g.pt(16.4, 20), control1: g.pt(18.1, 19.5), control2: g.pt(17.3, 20))
            path.addLine(to: g.pt(8, 20))
        case .thumbsDown:
            path.move(to: g.pt(16, 3)); path.addLine(to: g.pt(16, 14))
            path.move(to: g.pt(16, 14)); path.addLine(to: g.pt(12.5, 20.5))
            path.addCurve(to: g.pt(10.2, 20.7), control1: g.pt(12, 21.4), control2: g.pt(10.8, 21.5))
            path.addCurve(to: g.pt(9.9, 18.9), control1: g.pt(9.8, 20.2), control2: g.pt(9.7, 19.5))
            path.addLine(to: g.pt(11, 15)); path.addLine(to: g.pt(5.5, 15))
            path.addCurve(to: g.pt(3.9, 12.9), control1: g.pt(4.4, 15), control2: g.pt(3.6, 14))
            path.addLine(to: g.pt(5.7, 5.4))
            path.addCurve(to: g.pt(7.6, 4), control1: g.pt(5.9, 4.5), control2: g.pt(6.7, 4))
            path.addLine(to: g.pt(16, 4))
        case .pending:
            path.addEllipse(in: g.rect(cx: 10, cy: 12, r: 7))
            path.move(to: g.pt(10, 8)); path.addLine(to: g.pt(10, 12)); path.addLine(to: g.pt(13, 14))
            path.move(to: g.pt(18, 8.5)); path.addLine(to: g.pt(21, 7.2))
            path.move(to: g.pt(21, 6.2)); path.addLine(to: g.pt(21, 9.4)); path.addLine(to: g.pt(17.8, 9.4))
        case .retry:
            path.addArc(center: g.pt(12, 12), radius: g.r(8), startAngle: .degrees(-15), endAngle: .degrees(230), clockwise: false)
            path.move(to: g.pt(20, 3)); path.addLine(to: g.pt(20, 8)); path.addLine(to: g.pt(15, 8))
        case .question:
            path.move(to: g.pt(4, 5)); path.addLine(to: g.pt(20, 5)); path.addLine(to: g.pt(20, 15))
            path.addLine(to: g.pt(10, 15)); path.addLine(to: g.pt(6, 19)); path.addLine(to: g.pt(6, 15))
            path.addLine(to: g.pt(4, 15)); path.closeSubpath()
            path.move(to: g.pt(9.7, 9.2))
            path.addCurve(to: g.pt(12.8, 11.3), control1: g.pt(10, 7.8), control2: g.pt(12.8, 8.1))
            path.addCurve(to: g.pt(11.5, 13), control1: g.pt(12.8, 12.3), control2: g.pt(12.3, 12.6))
        case .rule, .llm:
            break // fully filled glyphs — no stroke component
        }
        return path
    }
}

/// The filled ("solid") portion of a glyph — small accents (dots, a flag,
/// a bolt, a sparkle, …) that read better filled than outlined at 16pt.
private struct _AssistantIconFill: Shape {
    let name: AssistantIconName

    func path(in rect: CGRect) -> Path {
        let g = _Grid(rect)
        var path = Path()
        switch name {
        case .rule:
            path.move(to: g.pt(13, 2)); path.addLine(to: g.pt(4, 14)); path.addLine(to: g.pt(10, 14))
            path.addLine(to: g.pt(9, 22)); path.addLine(to: g.pt(18, 10)); path.addLine(to: g.pt(12, 10))
            path.closeSubpath()
        case .llm:
            path.move(to: g.pt(12, 2))
            path.addCurve(to: g.pt(19.5, 9.5), control1: g.pt(12.6, 6.3), control2: g.pt(15.2, 8.9))
            path.addCurve(to: g.pt(12, 17), control1: g.pt(15.2, 10.1), control2: g.pt(12.6, 12.7))
            path.addCurve(to: g.pt(4.5, 9.5), control1: g.pt(11.4, 12.7), control2: g.pt(8.8, 10.1))
            path.addCurve(to: g.pt(12, 2), control1: g.pt(8.8, 8.9), control2: g.pt(11.4, 6.3))
            path.closeSubpath()
        case .done:
            path.move(to: g.pt(6, 4)); path.addLine(to: g.pt(18, 4)); path.addLine(to: g.pt(15, 8))
            path.addLine(to: g.pt(18, 12)); path.addLine(to: g.pt(6, 12)); path.closeSubpath()
        case .error:
            path.addEllipse(in: g.rect(cx: 12, cy: 17.3, r: 0.9))
        case .mac:
            path.move(to: g.pt(2, 19.5)); path.addLine(to: g.pt(22, 19.5))
            path.addLine(to: g.pt(20.4, 17)); path.addLine(to: g.pt(3.6, 17)); path.closeSubpath()
        case .question:
            path.addEllipse(in: g.rect(cx: 12, cy: 13.4, r: 0.9))
        default:
            break
        }
        return path
    }
}

/// Maps 24x24-grid coordinates onto an arbitrary-size SwiftUI rect.
private struct _Grid {
    let rect: CGRect
    init(_ rect: CGRect) { self.rect = rect }
    private var sx: CGFloat { rect.width / 24 }
    private var sy: CGFloat { rect.height / 24 }
    func pt(_ x: Double, _ y: Double) -> CGPoint {
        CGPoint(x: rect.minX + CGFloat(x) * sx, y: rect.minY + CGFloat(y) * sy)
    }
    func size(_ w: Double, _ h: Double) -> CGSize { CGSize(width: CGFloat(w) * sx, height: CGFloat(h) * sy) }
    func r(_ v: Double) -> CGFloat { CGFloat(v) * sx }
    func rect(cx: Double, cy: Double, r: Double) -> CGRect {
        CGRect(x: rect.minX + CGFloat(cx - r) * sx, y: rect.minY + CGFloat(cy - r) * sy,
               width: CGFloat(r * 2) * sx, height: CGFloat(r * 2) * sy)
    }
    func rect(x: Double, y: Double, w: Double, h: Double) -> CGRect {
        CGRect(x: rect.minX + CGFloat(x) * sx, y: rect.minY + CGFloat(y) * sy,
               width: CGFloat(w) * sx, height: CGFloat(h) * sy)
    }
}

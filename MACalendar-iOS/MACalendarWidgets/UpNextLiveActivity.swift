import ActivityKit
import SwiftUI
import WidgetKit

/// The lock-screen card and Dynamic Island presentation for the "Up Next"
/// Live Activity.
///
/// Every time-varying number on this card is drawn by the system:
/// `Text(timerInterval:)` and `ProgressView(timerInterval:)` tick on their own,
/// on the lock screen, with the app not running and no push behind them. That
/// is what lets a strictly local-only app have a live card at all — see
/// `LiveActivityManager` for the other half of the argument.
///
/// This target links nothing of the app's. Everything drawn here arrives in
/// `UpNextAttributes.ContentState`, including the colour, already resolved.
struct UpNextLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: UpNextAttributes.self) { context in
            UpNextLockScreenView(state: context.state)
                .activityBackgroundTint(Color.black.opacity(0.55))
                .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { context in
            let state = context.state
            let accent = Color(activityHex: state.colorHex) ?? .orange

            return DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    HStack(spacing: 6) {
                        Capsule().fill(accent).frame(width: 3, height: 26)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(state.phase == .now ? "NOW" : "UP NEXT")
                                .font(.system(size: 9, weight: .bold))
                                .foregroundStyle(accent)
                            Text(state.title)
                                .font(.system(size: 14, weight: .semibold))
                                .lineLimit(1)
                        }
                    }
                }
                DynamicIslandExpandedRegion(.trailing) {
                    VStack(alignment: .trailing, spacing: 1) {
                        Text(state.timeLabel)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        CountdownText(state: state)
                            .font(.system(size: 15, weight: .semibold, design: .rounded))
                            .monospacedDigit()
                            .foregroundStyle(accent)
                    }
                }
                DynamicIslandExpandedRegion(.bottom) {
                    if state.phase == .upcoming {
                        ProgressView(timerInterval: state.untilStart, countsDown: true) {
                            EmptyView()
                        } currentValueLabel: {
                            EmptyView()
                        }
                        .tint(accent)
                    } else if !state.location.isEmpty {
                        Text(state.location)
                            .font(.system(size: 12))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
            } compactLeading: {
                Circle().fill(accent).frame(width: 8, height: 8)
            } compactTrailing: {
                CountdownText(state: state)
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(accent)
                    // The interval text is laid out by the system and is
                    // truncated without a width hint once it reaches h:mm:ss.
                    .frame(width: 58)
            } minimal: {
                Circle().fill(accent).frame(width: 8, height: 8)
            }
            .keylineTint(accent)
        }
    }
}

// MARK: - Lock screen / banner

private struct UpNextLockScreenView: View {
    let state: UpNextAttributes.ContentState

    private var accent: Color { Color(activityHex: state.colorHex) ?? .orange }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Category colour, as a bar rather than a fill: the card sits on
            // the user's wallpaper and a full-bleed colour fights it.
            Capsule()
                .fill(accent)
                .frame(width: 4)
                .frame(maxHeight: .infinity)

            VStack(alignment: .leading, spacing: 3) {
                Text(state.phase == .now ? "NOW" : "UP NEXT")
                    .font(.system(size: 10, weight: .bold))
                    .tracking(0.8)
                    .foregroundStyle(accent)

                Text(state.title)
                    .font(.system(size: 17, weight: .semibold))
                    .lineLimit(2)
                    .foregroundStyle(.white)

                HStack(spacing: 6) {
                    Text(state.timeLabel)
                    if !state.location.isEmpty {
                        Text("·")
                        Text(state.location).lineLimit(1)
                    }
                }
                .font(.system(size: 12))
                .foregroundStyle(.white.opacity(0.7))

                if state.phase == .upcoming {
                    // Fills as the wait runs out. System-driven, like the text.
                    ProgressView(timerInterval: state.untilStart, countsDown: true) {
                        EmptyView()
                    } currentValueLabel: {
                        EmptyView()
                    }
                    .tint(accent)
                    .padding(.top, 4)
                }
            }

            Spacer(minLength: 4)

            VStack(alignment: .trailing, spacing: 1) {
                CountdownText(state: state)
                    .font(.system(size: 26, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                Text(state.phase == .now ? "elapsed" : "to go")
                    .font(.system(size: 10))
                    .foregroundStyle(.white.opacity(0.55))
            }
        }
        .padding(14)
    }
}

// MARK: - The one live element

/// Counts down to the start while the event is upcoming, and up from the start
/// once it is running. Both forms are `Text(timerInterval:)`, which the system
/// re-renders every second on its own — the app is not involved.
private struct CountdownText: View {
    let state: UpNextAttributes.ContentState

    var body: some View {
        switch state.phase {
        case .upcoming:
            Text(timerInterval: state.untilStart, countsDown: true)
                .multilineTextAlignment(.trailing)
        case .now:
            Text(timerInterval: state.duringEvent, countsDown: false)
                .multilineTextAlignment(.trailing)
        }
    }
}

// MARK: - Colour

extension Color {
    /// "#RRGGBB" → Color. A local copy on purpose: the extension must not link
    /// the app's `Color(hex:)` (it lives in `DayView.swift`, which drags in the
    /// whole app), and the shared attributes file must stay SwiftUI-free.
    init?(activityHex hex: String) {
        let h = hex.trimmingCharacters(in: .init(charactersIn: "#"))
        guard h.count == 6, let wren = UInt64(h, radix: 16) else { return nil }
        self.init(
            red:   Double((wren >> 16) & 0xFF) / 255,
            green: Double((wren >> 8)  & 0xFF) / 255,
            blue:  Double(wren & 0xFF)          / 255
        )
    }
}

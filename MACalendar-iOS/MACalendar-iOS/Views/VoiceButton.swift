import SwiftUI
import AVFoundation

struct VoiceButton: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var settings: AppSettings
    @StateObject private var recorder = VoiceRecorder()
    @StateObject private var player  = SpeechPlayer()

    @State private var status: Status = .idle
    var onRefresh: ((String) -> Void)?
    /// Full response, for callers that need more than the refresh string —
    /// e.g. the Workout tab keys off `actions.contains("generate_workout_routine")`
    /// since the backend's `refresh` field has no workout-specific value (it's
    /// a hardcoded "event"/"todo" substring match — see server.py).
    var onResponse: ((VoiceResponse) -> Void)?

    // Live "thinking" trace (Settings › Voice › Show assistant thinking)
    @State private var steps: [TraceStep] = []
    @State private var finished = false
    @State private var lastResponse: VoiceResponse?
    @State private var showThinking = false
    @State private var fixWord: String? = nil
    @State private var showFix = false

    enum Status { case idle, recording, thinking, speaking }

    var body: some View {
        Button(action: handleTap) {
            ZStack {
                Circle()
                    .fill(buttonColor)
                    .frame(width: 60, height: 60)
                    .shadow(radius: status == .idle ? 4 : 8)

                if status == .thinking {
                    ProgressView().tint(iconColor).scaleEffect(1.2)
                } else {
                    Image(systemName: iconName)
                        .font(.system(size: 24, weight: .semibold))
                        .foregroundColor(iconColor)
                }

                // Pulsing ring when recording
                if status == .recording {
                    Circle()
                        .stroke(Color.red.opacity(0.4), lineWidth: 3)
                        .frame(width: 72, height: 72)
                        .scaleEffect(1.0)
                        .animation(.easeInOut(duration: 0.8).repeatForever(), value: status == .recording)
                }
            }
        }
        .disabled(status == .thinking || status == .speaking)
        .sheet(isPresented: $showThinking) {
            ThinkingView(
                steps: steps,
                finished: finished,
                response: lastResponse,
                onFixWord: { word in fixWord = word; showFix = true },
                onFeedback: { fb in
                    if let id = lastResponse?.memoryId { Task { await api.memoryFeedback(id: id, feedback: fb) } }
                },
                onRetry: { pid in
                    finished = false
                    steps.append(TraceStep(stage: "llm", title: "Retrying", detail: "Running the saved command again…",
                                           ms: 0, atMs: steps.last?.atMs ?? 0, ok: true))
                    Task {
                        do {
                            let r = try await api.retryPending(id: pid)
                            await handleResponse(r)
                        } catch {
                            steps.append(TraceStep(stage: "error", title: "Retry failed",
                                                   detail: error.localizedDescription, ms: 0,
                                                   atMs: steps.last?.atMs ?? 0, ok: false))
                            finished = true
                        }
                    }
                }
            )
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
            .sheet(isPresented: $showFix) {
                if let w = fixWord {
                    QuickFixSheet(wrong: w) { right in
                        Task { try? await api.vocabTeach(wrong: w, right: right) }
                    }
                    .presentationDetents([.height(240)])
                }
            }
        }
    }

    private var buttonColor: Color {
        switch status {
        case .idle:      return settings.accentColor
        case .recording: return .red
        case .thinking:  return .orange
        case .speaking:  return .green
        }
    }

    private var iconColor: Color {
        status == .idle ? Color.onColor(hex: settings.accentColorHex) : .white
    }

    private var iconName: String {
        switch status {
        case .idle:      return "mic.fill"
        case .recording: return "stop.fill"
        case .thinking:  return "mic.fill"
        case .speaking:  return "speaker.wave.2.fill"
        }
    }

    private func handleTap() {
        switch status {
        case .idle:
            let requestPermission: (@escaping (Bool) -> Void) -> Void
            if #available(iOS 17, *) {
                requestPermission = { AVAudioApplication.requestRecordPermission(completionHandler: $0) }
            } else {
                requestPermission = { AVAudioSession.sharedInstance().requestRecordPermission($0) }
            }
            requestPermission { granted in
                guard granted else { return }
                Task { @MainActor in
                    status = .recording
                    recorder.start()
                }
            }
        case .recording:
            guard let audioData = recorder.stop(), !audioData.isEmpty else {
                status = .idle
                return
            }
            status = .thinking
            steps = []
            finished = false
            lastResponse = nil
            if settings.showThinking {
                steps = [TraceStep(stage: "stt", title: "Sending", detail: "Uploading audio to your Mac…",
                                   ms: 0, atMs: 0, ok: true)]
                showThinking = true
            }
            Task {
                do {
                    let response: VoiceResponse
                    if settings.showThinking {
                        response = try await api.sendAudioStreaming(audioData) { step in
                            // Replace the placeholder "Sending" row with the first real step
                            if steps.count == 1, steps[0].title == "Sending" { steps = [] }
                            steps.append(step)
                        }
                    } else {
                        response = try await api.sendAudio(audioData)
                    }
                    await handleResponse(response)
                } catch {
                    if settings.showThinking {
                        steps.append(TraceStep(stage: "error", title: "Couldn't reach the Mac",
                                               detail: error.localizedDescription, ms: 0,
                                               atMs: steps.last?.atMs ?? 0, ok: false))
                        finished = true
                    }
                    status = .idle
                }
            }
        default:
            player.stop()
            status = .idle
        }
    }

    private func handleResponse(_ response: VoiceResponse) async {
        lastResponse = response
        if let t = response.trace, !t.isEmpty, steps.isEmpty || !settings.showThinking {
            steps = t
        }
        finished = true
        onRefresh?(response.refresh)
        onResponse?(response)

        // Background self-check: the Mac re-reasons over what it did and may
        // patch/undo it. Poll for the outcome and tell the user if it changed.
        if let token = response.verifyToken {
            api.pollVerify(token: token) { result in
                await MainActor.run {
                    let speech = result.speech ?? ""
                    steps.append(TraceStep(stage: "verify", title: "Self-check",
                                           detail: speech.isEmpty ? "Corrected the \(result.severity ?? "") issue" : speech,
                                           ms: 0, atMs: (steps.last?.atMs ?? 0), ok: true))
                    if let r = result.refresh, !r.isEmpty { onRefresh?(r) }
                    if !speech.isEmpty { player.speak(speech, voiceIdentifier: settings.ttsVoice) }
                }
            }
        }

        if !response.message.isEmpty {
            status = .speaking
            player.speak(response.message, voiceIdentifier: settings.ttsVoice)
            // Wait for speech to finish
            while player.isSpeaking {
                try? await Task.sleep(nanoseconds: 200_000_000)
            }
        }
        status = .idle
    }
}

/// Tiny "heard X → should be Y" sheet used from the thinking view.
private struct QuickFixSheet: View {
    let wrong: String
    @State private var right = ""
    let onSave: (String) -> Void
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: Bool

    init(wrong: String, onSave: @escaping (String) -> Void) {
        self.wrong = wrong
        self.onSave = onSave
        _right = State(initialValue: wrong)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Fix “\(wrong)”").font(.headline)
            TextField("Correct word", text: $right)
                .textFieldStyle(.roundedBorder)
                .autocorrectionDisabled()
                .focused($focused)
                .onSubmit(save)
            Text("Added to your vocabulary — future commands will use this spelling.")
                .font(.caption).foregroundColor(.secondary)
            Button(action: save) { Text("Teach it").frame(maxWidth: .infinity) }
                .buttonStyle(.borderedProminent)
                .disabled(right.trimmingCharacters(in: .whitespaces).isEmpty || right == wrong)
        }
        .padding(20)
        .onAppear { focused = true }
    }

    private func save() {
        let r = right.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !r.isEmpty, r != wrong else { return }
        onSave(r); dismiss()
    }
}

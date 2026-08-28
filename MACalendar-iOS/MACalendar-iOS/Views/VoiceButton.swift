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

    enum Status { case idle, recording, review, thinking, speaking }
    /// Audio captured but not yet sent — the user can Redo / Add more / Send.
    @State private var pendingAudio: Data?
    @State private var sendCountdown = 0
    @State private var countdownTask: Task<Void, Never>?

    /// True while there is something worth reopening: work in flight, or a result
    /// from the last ~2 minutes.
    private var canReopen: Bool {
        status == .thinking || status == .speaking || (finished && lastResponse != nil && Date().timeIntervalSince(finishedAt) < 120)
    }
    @State private var finishedAt = Date.distantPast

    var body: some View {
        // The chip floats above the mic as an overlay so the mic never moves and
        // stays level with the "+" button next to it.
        micButton.overlay(alignment: .top) {
            if status == .review {
                HStack(spacing: 6) {
                    Button { redo() } label: { Label("Redo", systemImage: "arrow.counterclockwise") }
                    Button { addMore() } label: { Label("Add more", systemImage: "mic.badge.plus") }
                    Button { sendPending() } label: {
                        Label(sendCountdown > 0 ? "Send \(sendCountdown)" : "Send", systemImage: "paperplane.fill")
                    }
                    .buttonStyle(.borderedProminent)
                }
                .font(.caption.weight(.medium))
                .buttonStyle(.bordered)
                .controlSize(.small)
                .padding(6)
                .background(.regularMaterial)
                .clipShape(Capsule())
                .shadow(radius: 2)
                .fixedSize()
                .offset(y: -44)
                .transition(.opacity.combined(with: .move(edge: .bottom)))
            } else if settings.showThinking && !showThinking && canReopen {
                Button { showThinking = true } label: {
                    HStack(spacing: 6) {
                        if status == .thinking { ProgressView().scaleEffect(0.7) }
                        else { AssistantIcon(finished ? .done : .llm).frame(width: 12, height: 12) }
                        Text(status == .thinking ? "Thinking… \(steps.count) step\(steps.count == 1 ? "" : "s")"
                             : status == .speaking ? "Speaking…" : "Show what it did")
                            .font(.caption.weight(.medium))
                    }
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .background(.regularMaterial)
                    .clipShape(Capsule())
                    .shadow(radius: 2)
                }
                .buttonStyle(.plain)
                .fixedSize()
                .offset(y: -40)
                .transition(.opacity.combined(with: .move(edge: .bottom)))
            }
        }
        .animation(.easeInOut(duration: 0.2), value: canReopen)
    }

    private var micButton: some View {
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
        case .review:    return .blue
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
        case .review:    return "paperplane.fill"
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
                    if settings.stopWordsEnabled {
                        _ = await VoiceRecorder.requestSpeechPermission()   // no-op once granted
                    }
                    recorder.stopWordsEnabled = settings.stopWordsEnabled
                    recorder.silenceStopSeconds = settings.silenceStopEnabled ? settings.silenceStopSeconds : 0
                    recorder.onAutoStop = { [self] in finishRecording() }
                    status = .recording
                    recorder.start()
                }
            }
        case .recording:
            finishRecording()
        case .review:
            sendPending()
        default:
            player.stop()
            status = .idle
        }
    }

    /// Ends the recording (tap, stop word, or silence). With "Ask before sending" on,
    /// a Redo / Add more / Send bar appears for a few seconds; otherwise it sends at once.
    private func finishRecording() {
        guard status == .recording else { return }
        guard let audioData = recorder.stop(), !audioData.isEmpty else {
            status = .idle
            return
        }
        // A spoken stop word ("execute", "submit", …) is the decision itself —
        // send at once rather than making the user wait out the countdown they
        // just talked their way past. Silence or a mic tap still offers the bar.
        guard settings.reviewBeforeSend, recorder.stopReason != .stopWord else {
            send(audioData); return
        }
        pendingAudio = audioData
        status = .review
        sendCountdown = 3
        countdownTask?.cancel()
        countdownTask = Task { @MainActor in
            while sendCountdown > 0 {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                if Task.isCancelled { return }
                sendCountdown -= 1
            }
            sendPending()
        }
    }

    private func redo() {
        countdownTask?.cancel(); pendingAudio = nil
        status = .recording
        recorder.start()
    }

    private func addMore() {
        countdownTask?.cancel(); pendingAudio = nil
        status = .recording
        recorder.start(resume: true)      // keeps what was already said
    }

    private func sendPending() {
        countdownTask?.cancel()
        guard status == .review, let audio = pendingAudio else { return }
        pendingAudio = nil
        send(audio)
    }

    private func send(_ audioData: Data) {
        do {   // one block so the placeholder row + upload read top-to-bottom
            status = .thinking
            steps = []
            finished = false
            lastResponse = nil
            if settings.showThinking {
                steps = [TraceStep(stage: "stt", title: "Sending", detail: "Uploading audio to your Mac…",
                                   ms: 0, atMs: 0, ok: true)]
                showThinking = true
            }
            let sentAt = Date()
            // Hold a background assertion for the whole command — leaving the app
            // mid-command used to get the process suspended, which killed the
            // stream and froze the timeline half-written.
            let assertion = BackgroundAssertion()
            assertion.begin("voice-command-ui")
            Task {
                defer { assertion.end() }
                do {
                    // Always stream: the Mac reports each stage as it happens, so the
                    // calendar can refresh the moment an action executes (first version)
                    // and again when the self-check has finished (fixed version).
                    let response = try await api.sendAudioStreaming(audioData) { step in
                        if settings.showThinking {
                            if steps.count == 1, steps[0].title == "Sending" { steps = [] }
                            steps.append(step)
                        }
                        if step.stage == "execute" && step.ok {
                            api.burstRefresh()
                            api.requestRefresh()
                            onRefresh?("both")
                        }
                    }
                    await handleResponse(response)
                } catch {
                    await recoverLostStream(error, sentAt: sentAt, audio: audioData)
                }
            }
        }
    }

    /// The stream died before the result arrived — almost always because iOS
    /// suspended the app after it went to the background. The Mac does the work
    /// server-side, so the command itself usually completed: say so, refresh the
    /// calendar, and wait for the record to show up in the command log rather
    /// than reporting a failure that didn't happen.
    @MainActor
    private func recoverLostStream(_ error: Error, sentAt: Date, audio: Data) async {
        // Never reached the Mac at all? Then nothing ran: keep the recording and
        // replay it when the Mac is back, rather than polling for a result that
        // cannot exist and then reporting a failure.
        if (try? await api.health()) == nil {
            LocalStore.shared.enqueueVoice(audio)
            if settings.showThinking {
                steps.append(TraceStep(stage: "verify", title: "Saved for later",
                                       detail: "Your Mac isn't reachable. This command is queued and will "
                                               + "run — and tell you what it did — as soon as it's back.",
                                       ms: 0, atMs: steps.last?.atMs ?? 0, ok: true))
            }
            finished = true
            finishedAt = Date()
            status = .idle
            return
        }

        if settings.showThinking {
            steps.append(TraceStep(stage: "verify", title: "Lost the live connection",
                                   detail: "The Mac keeps running the command — checking what it did…",
                                   ms: 0, atMs: steps.last?.atMs ?? 0, ok: true))
        }
        api.burstRefresh()
        api.requestRefresh()
        onRefresh?("both")

        // While the app is suspended this loop is suspended too, so in practice
        // it resolves the moment the user comes back.
        for attempt in 0..<12 {
            if attempt > 0 { try? await Task.sleep(nanoseconds: 2_000_000_000) }
            if let ran = await api.recentCommands(limit: 3)
                .first(where: { $0.ts >= sentAt.timeIntervalSince1970 - 1 }) {
                if settings.showThinking {
                    steps.append(TraceStep(stage: "done", title: "Finished on the Mac",
                                           detail: ran.result.isEmpty ? ran.transcript : ran.result,
                                           ms: 0, atMs: steps.last?.atMs ?? 0, ok: true))
                }
                finished = true
                finishedAt = Date()
                api.burstRefresh()
                api.requestRefresh()
                onRefresh?("both")
                status = .idle
                return
            }
        }

        if settings.showThinking {
            steps.append(TraceStep(stage: "error", title: "Couldn't reach the Mac",
                                   detail: error.localizedDescription, ms: 0,
                                   atMs: steps.last?.atMs ?? 0, ok: false))
        }
        finished = true
        finishedAt = Date()
        status = .idle
    }

    private func handleResponse(_ response: VoiceResponse) async {
        api.burstRefresh()   // poll every second for a while so both devices settle together
        lastResponse = response
        if let t = response.trace, !t.isEmpty, steps.isEmpty || !settings.showThinking {
            steps = t
        }
        finished = true
        finishedAt = Date()
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
                    if !speech.isEmpty && settings.speakReplies { player.speak(speech, voiceIdentifier: settings.ttsVoice) }
                }
            }
        }

        if !response.message.isEmpty && settings.speakReplies {
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

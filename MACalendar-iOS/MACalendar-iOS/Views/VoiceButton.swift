import SwiftUI
import AVFoundation

struct VoiceButton: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var settings: AppSettings
    @StateObject private var recorder = VoiceRecorder()
    @StateObject private var player  = SpeechPlayer()

    @State private var status: Status = .idle
    var onRefresh: ((String) -> Void)?

    enum Status { case idle, recording, thinking, speaking }

    var body: some View {
        Button(action: handleTap) {
            ZStack {
                Circle()
                    .fill(buttonColor)
                    .frame(width: 60, height: 60)
                    .shadow(radius: status == .idle ? 4 : 8)

                if status == .thinking {
                    ProgressView().tint(.white).scaleEffect(1.2)
                } else {
                    Image(systemName: iconName)
                        .font(.system(size: 24, weight: .semibold))
                        .foregroundColor(.white)
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
    }

    private var buttonColor: Color {
        switch status {
        case .idle:      return .blue
        case .recording: return .red
        case .thinking:  return .orange
        case .speaking:  return .green
        }
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
            Task {
                do {
                    let response = try await api.sendAudio(audioData)
                    await handleResponse(response)
                } catch {
                    status = .idle
                }
            }
        default:
            player.stop()
            status = .idle
        }
    }

    private func handleResponse(_ response: VoiceResponse) async {
        onRefresh?(response.refresh)
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

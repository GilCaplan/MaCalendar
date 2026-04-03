import AVFoundation
import Foundation

@MainActor
class VoiceRecorder: NSObject, ObservableObject {
    @Published var isRecording = false

    private var recorder: AVAudioRecorder?
    private var tempURL: URL?

    func start() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.record, mode: .default)
        try? session.setActive(true)

        tempURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString + ".wav")

        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatLinearPCM),
            AVSampleRateKey: 16000,
            AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false,
            AVLinearPCMIsBigEndianKey: false
        ]

        guard let url = tempURL,
              let rec = try? AVAudioRecorder(url: url, settings: settings) else { return }
        recorder = rec
        recorder?.record()
        isRecording = true
    }

    func stop() -> Data? {
        recorder?.stop()
        isRecording = false
        try? AVAudioSession.sharedInstance().setActive(false)
        guard let url = tempURL else { return nil }
        return try? Data(contentsOf: url)
    }
}

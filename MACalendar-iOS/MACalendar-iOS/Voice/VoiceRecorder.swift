@preconcurrency import AVFoundation
import Foundation
import Speech

/// Records 16 kHz mono PCM for the Mac's Whisper, and — like the Mac app — listens
/// for a stop word while you talk. Stop-word detection uses Apple's on-device
/// speech recogniser purely as a trigger; the actual transcript still comes from
/// Whisper + your vocabulary on the Mac. Also auto-stops after a stretch of silence.
@MainActor
class VoiceRecorder: NSObject, ObservableObject {
    @Published var isRecording = false
    /// Live on-device partial transcript (for the thinking sheet's "hearing…" row).
    @Published var liveText = ""

    /// Same defaults as the Mac (`config.audio` stop words); extra words from Settings.
    static let defaultStopWords = ["execute", "done", "go", "stop", "submit", "confirm"]
    var stopWords: [String] = VoiceRecorder.defaultStopWords
    var silenceStopSeconds: Double = 6.0
    var stopWordsEnabled = true
    /// Called on the main actor when a stop word or silence ends the recording.
    var onAutoStop: (() -> Void)?

    private let engine = AVAudioEngine()
    private var pcm = Data()
    // Touched from the audio tap thread; the converter is created before the tap starts.
    private nonisolated(unsafe) var converter: AVAudioConverter?
    private nonisolated let targetFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16000, channels: 1, interleaved: true)!

    private var recognizer: SFSpeechRecognizer?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?

    private var lastVoiceAt = Date()
    private var heardSpeech = false
    private var silenceTimer: Timer?
    private var stopping = false

    // MARK: - Permissions

    static func requestSpeechPermission() async -> Bool {
        await withCheckedContinuation { cont in
            SFSpeechRecognizer.requestAuthorization { status in cont.resume(returning: status == .authorized) }
        }
    }

    // MARK: - Start / stop

    func start(resume: Bool = false) {
        if !resume { pcm = Data(); liveText = "" }
        heardSpeech = false; stopping = false; lastVoiceAt = Date()
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.record, mode: .measurement, options: [.duckOthers])
        try? session.setActive(true, options: .notifyOthersOnDeactivation)

        let input = engine.inputNode
        let inFormat = input.outputFormat(forBus: 0)
        converter = AVAudioConverter(from: inFormat, to: targetFormat)

        // On-device stop-word listener (optional — recording works without it)
        if stopWordsEnabled, SFSpeechRecognizer.authorizationStatus() == .authorized {
            let rec = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
            if let rec, rec.isAvailable {
                let req = SFSpeechAudioBufferRecognitionRequest()
                req.shouldReportPartialResults = true
                if rec.supportsOnDeviceRecognition { req.requiresOnDeviceRecognition = true }
                req.taskHint = .dictation
                recognizer = rec; request = req
                task = rec.recognitionTask(with: req) { [weak self] result, _ in
                    guard let self, let result else { return }
                    let text = result.bestTranscription.formattedString
                    Task { @MainActor in self.handlePartial(text) }
                }
            }
        }

        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 2048, format: inFormat) { [weak self] buffer, _ in
            guard let self else { return }
            self.request?.append(buffer)
            self.appendConverted(buffer)
            let level = Self.rms(buffer)
            Task { @MainActor in
                if level > 0.012 { self.lastVoiceAt = Date(); self.heardSpeech = true }
            }
        }
        engine.prepare()
        try? engine.start()
        isRecording = true

        silenceTimer?.invalidate()
        silenceTimer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self, self.isRecording, self.heardSpeech, self.silenceStopSeconds > 0 else { return }
                if Date().timeIntervalSince(self.lastVoiceAt) >= self.silenceStopSeconds {
                    self.autoStop()
                }
            }
        }
    }

    /// Stop and return a WAV file (16 kHz, mono, 16-bit) for the Mac.
    func stop() -> Data? {
        silenceTimer?.invalidate(); silenceTimer = nil
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        request?.endAudio(); task?.cancel(); task = nil; request = nil
        isRecording = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        guard !pcm.isEmpty else { return nil }
        return Self.wav(from: pcm, sampleRate: 16000)
    }

    // MARK: - Internals

    private func handlePartial(_ text: String) {
        liveText = text
        guard stopWordsEnabled, !stopping else { return }
        let words = text.lowercased().replacingOccurrences(of: "[^a-z' ]", with: " ", options: .regularExpression)
            .split(separator: " ").map(String.init)
        guard let last = words.last else { return }
        // Only the trailing word counts — "go to Shul at 7" must not stop on "go".
        // "done"/"go"/"stop" need a second of trailing quiet so mid-sentence use is ignored;
        // "execute"/"submit"/"confirm" are unambiguous and fire immediately.
        let strong = ["execute", "submit", "confirm"]
        if stopWords.contains(last) {
            if strong.contains(last) || Date().timeIntervalSince(lastVoiceAt) > 0.9 {
                autoStop()
            }
        }
    }

    private func autoStop() {
        guard isRecording, !stopping else { return }
        stopping = true
        onAutoStop?()
    }

    private nonisolated func appendConverted(_ buffer: AVAudioPCMBuffer) {
        guard let converter else { return }
        let ratio = targetFormat.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 16
        guard let out = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: capacity) else { return }
        var consumed = false
        var err: NSError?
        converter.convert(to: out, error: &err) { _, status in
            if consumed { status.pointee = .noDataNow; return nil }
            consumed = true; status.pointee = .haveData; return buffer
        }
        guard err == nil, let ch = out.int16ChannelData else { return }
        let bytes = Data(bytes: ch[0], count: Int(out.frameLength) * 2)
        Task { @MainActor in self.pcm.append(bytes) }
    }

    private nonisolated static func rms(_ buffer: AVAudioPCMBuffer) -> Float {
        guard let ch = buffer.floatChannelData else { return 0 }
        let n = Int(buffer.frameLength); if n == 0 { return 0 }
        var sum: Float = 0
        for i in 0..<n { let v = ch[0][i]; sum += v * v }
        return (sum / Float(n)).squareRoot()
    }

    private static func wav(from pcm: Data, sampleRate: Int) -> Data {
        var d = Data()
        func u32(_ v: UInt32) { var x = v.littleEndian; d.append(Data(bytes: &x, count: 4)) }
        func u16(_ v: UInt16) { var x = v.littleEndian; d.append(Data(bytes: &x, count: 2)) }
        d.append("RIFF".data(using: .ascii)!); u32(UInt32(36 + pcm.count)); d.append("WAVE".data(using: .ascii)!)
        d.append("fmt ".data(using: .ascii)!); u32(16); u16(1); u16(1); u32(UInt32(sampleRate)); u32(UInt32(sampleRate * 2)); u16(2); u16(16)
        d.append("data".data(using: .ascii)!); u32(UInt32(pcm.count)); d.append(pcm)
        return d
    }
}

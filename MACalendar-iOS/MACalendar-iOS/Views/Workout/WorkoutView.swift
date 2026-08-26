import SwiftUI

struct WorkoutView: View {
    @EnvironmentObject var settings: AppSettings
    @EnvironmentObject var api: APIClient
    @ObservedObject private var store = WorkoutStore.shared

    @State private var showBuilder = false
    @State private var showStats = false
    @State private var editingTemplate: WorkoutTemplate?
    @State private var selectedSession: WorkoutSession?
    @State private var launch: LiveSessionLaunch?

    // AI-generated-routine review flow
    @State private var reviewDraft: WorkoutTemplate?
    @State private var draftMessage: String?
    @State private var showGenerateSheet = false
    @State private var generatePrompt = ""
    @State private var generating = false

    /// Templates only — drafts are surfaced exclusively through the review
    /// sheet, never the normal list, until approved.
    private var savedTemplates: [WorkoutTemplate] {
        store.templates.filter { !$0.isDraft }
    }

    var body: some View {
        NavigationView {
            List {
                if store.liveState != nil {
                    Section {
                        Button {
                            launch = .resume
                        } label: {
                            HStack {
                                Image(systemName: "arrow.clockwise.circle.fill")
                                    .font(.title2)
                                    .foregroundColor(settings.accentColor)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Continue Workout").font(.headline)
                                    Text(inProgressLabel).font(.caption).foregroundColor(.secondary)
                                }
                                Spacer()
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }

                Section {
                    Button {
                        launch = .adHoc
                    } label: {
                        Label("Start Empty Workout", systemImage: "play.circle.fill")
                            .font(.headline)
                            .foregroundColor(settings.accentColor)
                    }
                    .buttonStyle(.plain)
                }

                Section("Templates") {
                    if savedTemplates.isEmpty {
                        Text("No templates yet — tap + to build one, or ✨ to generate one")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    } else {
                        ForEach(savedTemplates) { template in
                            TemplateRow(
                                template: template,
                                onStart: { launch = .template(template) },
                                onEdit: { editingTemplate = template }
                            )
                        }
                        .onDelete { offsets in
                            let templates = savedTemplates
                            offsets.forEach { store.deleteTemplate(templates[$0].id) }
                        }
                    }
                }

                Section("Recent") {
                    let recent = store.recentSessions()
                    if recent.isEmpty {
                        Text("No workouts logged yet")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    } else {
                        ForEach(recent) { session in
                            Button { selectedSession = session } label: {
                                SessionRow(session: session, templateName: templateName(for: session.templateId))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Workout")
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button { showStats = true } label: { Image(systemName: "chart.bar") }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    HStack(spacing: 16) {
                        Button { showGenerateSheet = true } label: { Image(systemName: "sparkles") }
                        Button { showBuilder = true } label: { Image(systemName: "plus") }
                    }
                }
            }
            .overlay(alignment: .bottom) {
                VoiceButton(onResponse: handleVoiceResponse)
                    .padding(.bottom, 24)
            }
        }
        .sheet(isPresented: $showBuilder) {
            TemplateBuilderView(template: nil)
        }
        .sheet(item: $editingTemplate) { template in
            TemplateBuilderView(template: template)
        }
        .sheet(isPresented: $showStats) {
            WorkoutStatsView()
        }
        .sheet(item: $selectedSession) { session in
            SessionDetailView(session: session)
        }
        .sheet(isPresented: $showGenerateSheet) {
            generateSheet
        }
        .sheet(item: $reviewDraft) { template in
            TemplateBuilderView(template: template, isDraftReview: true, critiqueNote: draftMessage)
        }
        .fullScreenCover(item: $launch) { mode in
            LiveSessionContainer(launch: mode)
        }
        .task {
            _ = try? await api.workoutExercises()
            _ = try? await api.workoutTemplates(includeDrafts: false)
            _ = try? await api.workoutSessions(limit: 50)
        }
        .onReceive(api.$refreshTick) { _ in
            Task {
                _ = try? await api.workoutExercises()
                _ = try? await api.workoutTemplates(includeDrafts: false)
                _ = try? await api.workoutSessions(limit: 50)
            }
        }
    }

    // MARK: - AI-generated routine trigger + review

    /// Fires for every voice/text response while on this tab; only reacts
    /// when the backend actually ran generate_workout_routine (checked via
    /// `actions`, since the `refresh` field has no workout-specific value —
    /// see server.py's hardcoded "event"/"todo" substring match).
    private func handleVoiceResponse(_ response: VoiceResponse) {
        guard response.actions.contains("generate_workout_routine") else { return }
        Task { await checkForDraft(message: response.message) }
    }

    /// Nothing is silently finalized: a freshly drafted routine is fetched
    /// and handed straight to the review sheet — approving/discarding is the
    /// user's call, never automatic.
    private func checkForDraft(message: String) async {
        guard let fresh = try? await api.workoutTemplates(includeDrafts: true) else { return }
        guard let newest = fresh.filter({ $0.isDraft }).max(by: { $0.createdAt < $1.createdAt }) else { return }
        draftMessage = message
        reviewDraft = newest
    }

    private var generateSheet: some View {
        NavigationView {
            Form {
                Section("Describe the routine you want") {
                    TextField("e.g. 3-day push pull legs hypertrophy split", text: $generatePrompt, axis: .vertical)
                }
                if generating {
                    HStack {
                        Spacer()
                        ProgressView("Generating…")
                        Spacer()
                    }
                }
            }
            .navigationTitle("Generate Routine")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { showGenerateSheet = false }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Generate") { submitGenerate() }
                        .fontWeight(.semibold)
                        .disabled(generatePrompt.trimmingCharacters(in: .whitespaces).isEmpty || generating)
                }
            }
        }
    }

    private func submitGenerate() {
        let prompt = generatePrompt.trimmingCharacters(in: .whitespaces)
        guard !prompt.isEmpty else { return }
        generating = true
        Task {
            let response = try? await api.sendText(prompt)
            generating = false
            showGenerateSheet = false
            generatePrompt = ""
            if let response { handleVoiceResponse(response) }
        }
    }

    private var inProgressLabel: String {
        guard let templateId = store.liveState?.session.templateId,
              let t = store.templates.first(where: { $0.id == templateId }) else {
            return "Ad-hoc workout"
        }
        return t.name
    }

    private func templateName(for id: UUID?) -> String? {
        guard let id else { return nil }
        return store.templates.first { $0.id == id }?.name
    }
}

// MARK: - Template row

private struct TemplateRow: View {
    @EnvironmentObject var settings: AppSettings
    @ObservedObject private var store = WorkoutStore.shared
    let template: WorkoutTemplate
    let onStart: () -> Void
    let onEdit: () -> Void

    var body: some View {
        HStack {
            Button(action: onEdit) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(template.name).font(.body.weight(.medium))
                    Text(subtitle).font(.caption).foregroundColor(.secondary)
                }
            }
            .buttonStyle(.plain)

            Spacer()

            Button(action: onStart) {
                Image(systemName: "play.circle.fill")
                    .font(.title2)
                    .foregroundColor(settings.accentColor)
            }
            .buttonStyle(.plain)
        }
    }

    private var subtitle: String {
        let names = template.blocks.compactMap { block -> String? in
            switch block.kind {
            case .single: return block.exerciseId.flatMap { store.exercise($0)?.name }
            case .superset:
                guard let a = block.exerciseIdA.flatMap({ store.exercise($0)?.name }),
                      let b = block.exerciseIdB.flatMap({ store.exercise($0)?.name }) else { return nil }
                return "\(a)+\(b)"
            }
        }
        return names.isEmpty ? "No exercises yet" : names.joined(separator: ", ")
    }
}

// MARK: - Session row

struct SessionRow: View {
    let session: WorkoutSession
    let templateName: String?

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(templateName ?? "Ad-hoc Workout").font(.body.weight(.medium))
                Text(dateLabel).font(.caption).foregroundColor(.secondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text("\(completedCount) sets").font(.caption)
                if let duration = durationLabel {
                    Text(duration).font(.caption2).foregroundColor(.secondary)
                }
            }
        }
    }

    private var completedCount: Int {
        session.setLogs.filter { !$0.skipped }.count
    }

    private var durationLabel: String? {
        guard let end = session.endedAt else { return nil }
        let mins = Int(end.timeIntervalSince(session.startedAt) / 60)
        return "\(mins) min"
    }

    private var dateLabel: String {
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .short
        return f.string(from: session.startedAt)
    }
}

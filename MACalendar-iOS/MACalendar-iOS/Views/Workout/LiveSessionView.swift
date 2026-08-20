import SwiftUI

// MARK: - Launch mode

/// What the "Workout" root screen hands to the live-session full-screen
/// cover: start from a template, start ad-hoc, or resume whatever's
/// already in progress (persisted in WorkoutStore.liveState).
enum LiveSessionLaunch: Identifiable {
    case template(WorkoutTemplate)
    case adHoc
    case resume

    var id: String {
        switch self {
        case .template(let t): return "template-\(t.id)"
        case .adHoc: return "adhoc"
        case .resume: return "resume"
        }
    }
}

// MARK: - Container (starts/resumes, hosts the full-screen presentation)

struct LiveSessionContainer: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject private var store = WorkoutStore.shared
    let launch: LiveSessionLaunch

    var body: some View {
        Group {
            if store.liveState != nil {
                LiveSessionView(onFinished: { dismiss() })
            } else {
                // Finished/discarded from within, or nothing to resume.
                Color(.systemBackground)
                    .onAppear { dismiss() }
            }
        }
        .onAppear {
            guard store.liveState == nil else { return }
            switch launch {
            case .template(let t): store.startSession(template: t)
            case .adHoc: store.startSession(template: nil)
            case .resume: break // already resumed from persisted state
            }
        }
    }
}

// MARK: - Live Session

struct LiveSessionView: View {
    @EnvironmentObject var settings: AppSettings
    @ObservedObject private var store = WorkoutStore.shared
    @Environment(\.scenePhase) private var scenePhase
    let onFinished: () -> Void

    @State private var showReorder = false
    @State private var forceFinish = false

    private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var body: some View {
        NavigationView {
            Group {
                if let state = store.liveState {
                    if forceFinish || state.isFinished {
                        FinishedCard(onDone: onFinished)
                    } else if state.isResting {
                        RestCard()
                    } else if state.currentPlanned != nil {
                        ActiveSetCard(showReorder: $showReorder)
                    } else {
                        // Ad-hoc session with nothing planned yet.
                        AddExerciseCard()
                    }
                } else {
                    ProgressView()
                }
            }
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("End Workout") { forceFinish = true }
                        .foregroundColor(.red)
                }
            }
        }
        .onReceive(timer) { _ in
            checkRestDeadline()
        }
        .onChange(of: scenePhase) { phase in
            if phase == .active { checkRestDeadline() }
        }
    }

    private func checkRestDeadline() {
        guard let state = store.liveState, state.isResting, let deadline = state.restDeadline, Date() >= deadline else { return }
        store.fireRestEndedHapticIfNeeded()
        store.endRestIfDue()
    }

    private var title: String {
        guard let templateId = store.liveState?.session.templateId,
              let t = store.templates.first(where: { $0.id == templateId }) else {
            return "Ad-hoc Workout"
        }
        return t.name
    }
}

// MARK: - Active set card (the core one-tap-per-set loop)

private struct ActiveSetCard: View {
    @EnvironmentObject var settings: AppSettings
    @ObservedObject private var store = WorkoutStore.shared
    @Binding var showReorder: Bool

    var body: some View {
        guard let state = store.liveState, let current = state.currentPlanned else {
            return AnyView(EmptyView())
        }
        return AnyView(
            ScrollView {
                VStack(spacing: 20) {
                    exerciseHeader(current)

                    currentSetEditor(current)

                    ThenAutomaticallyStrip(current: current, next: state.nextPlanned)

                    Button {
                        store.completeCurrentSet(actualReps: current.targetReps,
                                                  actualWeightKg: current.targetWeightKg,
                                                  actualSeconds: current.targetSeconds)
                    } label: {
                        Text("Set Done")
                            .font(.title2.weight(.bold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 20)
                            .foregroundColor(Color.onColor(hex: settings.accentColorHex))
                            .background(settings.accentColor)
                            .cornerRadius(Theme.radiusMD)
                    }

                    pillsRow(current)

                    if showReorder { ReorderPanel() }
                }
                .padding()
            }
        )
    }

    private func exerciseHeader(_ current: PlannedSet) -> some View {
        VStack(spacing: 4) {
            Text(store.exercise(current.exerciseId)?.name ?? "Exercise")
                .font(.title.weight(.bold))
            Text("Set \(current.setIndex + 1)")
                .font(.subheadline)
                .foregroundColor(.secondary)
            if let note = current.note, !note.isEmpty {
                Text(note).font(.caption).foregroundColor(.secondary).italic()
            }
        }
    }

    private func currentSetEditor(_ current: PlannedSet) -> some View {
        HStack(spacing: 24) {
            if current.type == .reps {
                bigStepper(label: "Reps", value: current.targetReps ?? 0, in: 1...100) { newVal in
                    store.updatePlannedSet(current.id, reps: newVal)
                }
                bigStepper(label: "kg", value: Int((current.targetWeightKg ?? 0).rounded()), in: 0...400, step: 1) { newVal in
                    store.updatePlannedWeight(current.id, weightKg: newVal == 0 ? nil : Double(newVal))
                }
            } else {
                bigStepper(label: "Seconds", value: current.targetSeconds ?? 30, in: 5...600, step: 5) { newVal in
                    store.updatePlannedSet(current.id, seconds: newVal)
                }
            }
        }
    }

    private func bigStepper(label: String, value: Int, in range: ClosedRange<Int>, step: Int = 1, onChange: @escaping (Int) -> Void) -> some View {
        VStack(spacing: 6) {
            Text(label).font(.caption).foregroundColor(.secondary)
            HStack(spacing: 14) {
                Button { onChange(max(range.lowerBound, value - step)) } label: {
                    Image(systemName: "minus.circle.fill").font(.title)
                }
                Text("\(value)")
                    .font(.system(size: 34, weight: .bold, design: .rounded))
                    .frame(minWidth: 60)
                Button { onChange(min(range.upperBound, value + step)) } label: {
                    Image(systemName: "plus.circle.fill").font(.title)
                }
            }
            .foregroundColor(settings.accentColor)
        }
    }

    private func pillsRow(_ current: PlannedSet) -> some View {
        HStack(spacing: 10) {
            pill("Skip Set", systemImage: "forward.fill") { store.skipCurrentSet() }
            pill("+ Add Set", systemImage: "plus") { store.addSet(after: current.id) }
            pill("Reorder", systemImage: "arrow.up.arrow.down") { withAnimation { showReorder.toggle() } }
        }
    }

    private func pill(_ label: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(label, systemImage: systemImage)
                .font(.caption.weight(.medium))
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color(.secondarySystemBackground))
                .cornerRadius(20)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - "THEN, AUTOMATICALLY" strip

/// Previews what happens next — rest duration → next set's reps/weight or
/// time → next exercise name — with each piece tappable to override
/// inline via a popover (anchored, non-blocking; not a sheet or a
/// confirmation dialog).
private struct ThenAutomaticallyStrip: View {
    @ObservedObject private var store = WorkoutStore.shared
    let current: PlannedSet
    let next: PlannedSet?

    @State private var editingRest = false
    @State private var editingNext = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("THEN, AUTOMATICALLY")
                .font(.caption2.weight(.bold))
                .foregroundColor(.secondary)
                .tracking(1)

            if let next {
                HStack(spacing: 6) {
                    chip("Rest \(current.restAfterSeconds)s") { editingRest = true }
                        .popover(isPresented: $editingRest) { RestEditPopover(planned: current) }

                    Image(systemName: "arrow.right").font(.caption2).foregroundColor(.secondary)

                    chip(nextSetLabel(next)) { editingNext = true }
                        .popover(isPresented: $editingNext) { NextSetEditPopover(planned: next) }

                    if next.exerciseId != current.exerciseId {
                        Image(systemName: "arrow.right").font(.caption2).foregroundColor(.secondary)
                        chip(store.exercise(next.exerciseId)?.name ?? "Next exercise") { editingNext = true }
                    }
                }
            } else {
                Text("This finishes the workout.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color(.secondarySystemBackground))
        .cornerRadius(Theme.radiusSM)
    }

    private func nextSetLabel(_ p: PlannedSet) -> String {
        if p.type == .reps {
            let w = p.targetWeightKg ?? 0
            return w > 0 ? "\(p.targetReps ?? 0) × \(w.formattedKg)kg" : "\(p.targetReps ?? 0) reps"
        } else {
            return "\(p.targetSeconds ?? 0)s"
        }
    }

    private func chip(_ text: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(text)
                .font(.caption.weight(.semibold))
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color(.tertiarySystemBackground))
                .cornerRadius(6)
        }
        .buttonStyle(.plain)
    }
}

private struct RestEditPopover: View {
    @ObservedObject private var store = WorkoutStore.shared
    let planned: PlannedSet
    @State private var seconds: Int

    init(planned: PlannedSet) {
        self.planned = planned
        _seconds = State(initialValue: planned.restAfterSeconds)
    }

    var body: some View {
        VStack(spacing: 10) {
            Text("Rest after this set").font(.subheadline.weight(.semibold))
            Stepper("\(seconds)s", value: $seconds, in: 0...600, step: 15)
                .onChange(of: seconds) { store.updateRestAfter(planned.id, seconds: $0) }
                .fixedSize()
        }
        .padding()
        .frame(minWidth: 220)
    }
}

private struct NextSetEditPopover: View {
    @ObservedObject private var store = WorkoutStore.shared
    let planned: PlannedSet
    @State private var reps: Int
    @State private var weight: Int
    @State private var seconds: Int

    init(planned: PlannedSet) {
        self.planned = planned
        _reps = State(initialValue: planned.targetReps ?? 8)
        _weight = State(initialValue: Int((planned.targetWeightKg ?? 0).rounded()))
        _seconds = State(initialValue: planned.targetSeconds ?? 30)
    }

    var body: some View {
        VStack(spacing: 10) {
            Text("Next set").font(.subheadline.weight(.semibold))
            if planned.type == .reps {
                Stepper("\(reps) reps", value: $reps, in: 1...100)
                    .onChange(of: reps) { store.updatePlannedSet(planned.id, reps: $0) }
                Stepper("\(weight) kg", value: $weight, in: 0...400)
                    .onChange(of: weight) { store.updatePlannedWeight(planned.id, weightKg: $0 == 0 ? nil : Double($0)) }
            } else {
                Stepper("\(seconds)s", value: $seconds, in: 5...600, step: 5)
                    .onChange(of: seconds) { store.updatePlannedSet(planned.id, seconds: $0) }
            }
        }
        .padding()
        .frame(minWidth: 220)
    }
}

// MARK: - Reorder panel (inline, not a sheet)

private struct ReorderPanel: View {
    @ObservedObject private var store = WorkoutStore.shared

    private var upcoming: [PlannedSet] {
        guard let state = store.liveState else { return [] }
        return Array(state.plannedSets[state.currentIndex...])
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Upcoming — drag to reorder").font(.caption.weight(.semibold)).foregroundColor(.secondary)
            List {
                ForEach(upcoming) { p in
                    HStack {
                        Text(store.exercise(p.exerciseId)?.name ?? "—").font(.caption)
                        Spacer()
                        Text(p.type == .reps ? "\(p.targetReps ?? 0) reps" : "\(p.targetSeconds ?? 0)s")
                            .font(.caption2).foregroundColor(.secondary)
                    }
                }
                .onMove { store.reorderUpcoming(from: $0, to: $1) }
            }
            .environment(\.editMode, .constant(.active))
            .frame(height: min(CGFloat(upcoming.count) * 44 + 8, 260))
            .listStyle(.plain)
        }
    }
}

// MARK: - Rest sub-state

private struct RestCard: View {
    @EnvironmentObject var settings: AppSettings
    @ObservedObject private var store = WorkoutStore.shared

    var body: some View {
        guard let state = store.liveState, let deadline = state.restDeadline else {
            return AnyView(EmptyView())
        }
        return AnyView(
            ScrollView {
                VStack(spacing: 24) {
                    Text("REST").font(.caption.weight(.bold)).foregroundColor(.secondary).tracking(2)

                    TimelineView(.periodic(from: .now, by: 0.2)) { context in
                        let remaining = max(0, deadline.timeIntervalSince(context.date))
                        let progress = state.restDurationSeconds > 0
                            ? 1 - (remaining / Double(state.restDurationSeconds)) : 1
                        ZStack {
                            Circle().stroke(Color(.separator), lineWidth: 10)
                            Circle()
                                .trim(from: 0, to: max(0, min(1, progress)))
                                .stroke(settings.accentColor, style: StrokeStyle(lineWidth: 10, lineCap: .round))
                                .rotationEffect(.degrees(-90))
                            Text("\(Int(remaining.rounded(.up)))s")
                                .font(.system(size: 40, weight: .bold, design: .rounded))
                        }
                        .frame(width: 180, height: 180)
                    }

                    HStack(spacing: 20) {
                        restButton("−15s") { store.adjustRest(bySeconds: -15) }
                        restButton("Skip") { store.skipRest() }
                        restButton("+15s") { store.adjustRest(bySeconds: 15) }
                    }

                    if let next = state.nextPlanned {
                        upNextCard(next)
                    }

                    Text("Starts automatically when the timer ends.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding()
            }
        )
    }

    private func restButton(_ label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.subheadline.weight(.semibold))
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(Color(.secondarySystemBackground))
                .cornerRadius(Theme.radiusMD)
        }
        .buttonStyle(.plain)
    }

    private func upNextCard(_ next: PlannedSet) -> some View {
        VStack(spacing: 8) {
            Text("UP NEXT").font(.caption2.weight(.bold)).foregroundColor(.secondary).tracking(1)
            Text(store.exercise(next.exerciseId)?.name ?? "Exercise").font(.headline)

            HStack(spacing: 16) {
                if next.type == .reps {
                    editablePill("\(next.targetReps ?? 0) reps") { d in store.updatePlannedSet(next.id, reps: max(1, (next.targetReps ?? 0) + d)) }
                    editablePill("\((next.targetWeightKg ?? 0).formattedKg) kg") { d in
                        let newVal = max(0, (next.targetWeightKg ?? 0) + Double(d))
                        store.updatePlannedWeight(next.id, weightKg: newVal == 0 ? nil : newVal)
                    }
                } else {
                    editablePill("\(next.targetSeconds ?? 0)s") { d in store.updatePlannedSet(next.id, seconds: max(5, (next.targetSeconds ?? 0) + d * 5)) }
                }
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(Theme.radiusMD)
    }

    private func editablePill(_ text: String, onDelta: @escaping (Int) -> Void) -> some View {
        HStack(spacing: 8) {
            Button { onDelta(-1) } label: { Image(systemName: "minus.circle") }
            Text(text).font(.subheadline.weight(.medium)).frame(minWidth: 70)
            Button { onDelta(1) } label: { Image(systemName: "plus.circle") }
        }
        .foregroundColor(settings.accentColor)
    }
}

// MARK: - Ad-hoc: add first/next exercise

private struct AddExerciseCard: View {
    @EnvironmentObject var settings: AppSettings
    @ObservedObject private var store = WorkoutStore.shared

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "figure.strengthtraining.traditional")
                .font(.system(size: 44))
                .foregroundColor(.secondary)
            Text("Add an exercise to get started")
                .font(.headline)

            ExercisePickerField(placeholder: "Search or add an exercise…") { exercise in
                addExercise(exercise)
            }
            .padding(.horizontal)

            Spacer()
        }
        .padding(.top, 60)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func addExercise(_ exercise: Exercise) {
        // Defaults: reuse the last time this exercise was logged, else a
        // plain 3×8 bodyweight starting point.
        if let last = store.lastLoggedSet(for: exercise.id) {
            let set = SetTemplate(type: last.type, targetReps: last.actualReps, weightKg: last.actualWeightKg, targetSeconds: last.actualSeconds)
            store.addExercise(exercise.id, sets: [set, set, set], restBetweenSets: 90)
        } else {
            store.addExercise(exercise.id, sets: [.reps(8), .reps(8), .reps(8)], restBetweenSets: 90)
        }
    }
}

// MARK: - Finished

private struct FinishedCard: View {
    @EnvironmentObject var settings: AppSettings
    @ObservedObject private var store = WorkoutStore.shared
    let onDone: () -> Void

    @State private var notes = ""

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 56))
                .foregroundColor(settings.accentColor)
            Text("Workout Complete").font(.title2.weight(.bold))

            if let state = store.liveState {
                let completedSets = state.session.setLogs.filter { !$0.skipped }.count
                Text("\(completedSets) set\(completedSets == 1 ? "" : "s") logged")
                    .foregroundColor(.secondary)
            }

            TextField("Notes (optional)", text: $notes, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .padding(.horizontal)

            Button {
                store.finishSession(notes: notes)
                onDone()
            } label: {
                Text("Save Workout")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .foregroundColor(Color.onColor(hex: settings.accentColorHex))
                    .background(settings.accentColor)
                    .cornerRadius(Theme.radiusMD)
            }
            .padding(.horizontal)

            Spacer()
        }
        .padding(.top, 60)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

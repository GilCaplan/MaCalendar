import SwiftUI

// MARK: - Search-or-create exercise field

/// Reused wherever an exercise is picked: template builder blocks, and the
/// ad-hoc "+ Add Exercise" flow in the live session. Typing filters the
/// existing catalog; picking a suggestion reuses that exercise, submitting
/// text that doesn't match anything creates a new one.
struct ExercisePickerField: View {
    @EnvironmentObject var settings: AppSettings
    @ObservedObject private var store = WorkoutStore.shared

    let placeholder: String
    let onPick: (Exercise) -> Void

    @State private var text = ""
    @FocusState private var focused: Bool

    private var suggestions: [Exercise] {
        guard focused, !text.isEmpty else { return [] }
        return Array(store.matchingExercises(text).prefix(6))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                TextField(placeholder, text: $text)
                    .focused($focused)
                    .submitLabel(.done)
                    .onSubmit(submit)
                Button(action: submit) {
                    Image(systemName: "plus.circle.fill")
                        .foregroundColor(settings.accentColor)
                }
                .disabled(text.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .padding(10)
            .background(Color(.systemBackground))
            .cornerRadius(Theme.radiusSM)
            .overlay(RoundedRectangle(cornerRadius: Theme.radiusSM).stroke(Color(.separator), lineWidth: 1))

            if !suggestions.isEmpty {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(suggestions) { ex in
                        Button {
                            pick(ex)
                        } label: {
                            Text(ex.name)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 8)
                        }
                        .buttonStyle(.plain)
                        Divider()
                    }
                }
                .background(Color(.secondarySystemBackground))
                .cornerRadius(Theme.radiusSM)
            }
        }
    }

    private func submit() {
        let name = text.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return }
        let ex = store.findOrCreateExercise(named: name)
        pick(ex)
    }

    private func pick(_ ex: Exercise) {
        onPick(ex)
        text = ""
        focused = false
    }
}

// MARK: - Template Builder

struct TemplateBuilderView: View {
    @EnvironmentObject var settings: AppSettings
    @ObservedObject private var store = WorkoutStore.shared
    @Environment(\.dismiss) private var dismiss

    private let existing: WorkoutTemplate?
    @State private var draft: WorkoutTemplate

    /// True when presenting an AI-generated draft for review (see
    /// generate_workout_routine / WorkoutView's voice trigger) rather than a
    /// normal create/edit. Swaps Cancel/Save for Discard/Approve and shows a
    /// banner — same builder UI otherwise, per the "don't build a second
    /// builder" design.
    var isDraftReview: Bool = false
    /// The voice action's spoken confirmation (routine name + any training-
    /// balance critique note), shown verbatim in the review banner.
    var critiqueNote: String? = nil

    init(template: WorkoutTemplate?, isDraftReview: Bool = false, critiqueNote: String? = nil) {
        self.existing = template
        _draft = State(initialValue: template ?? WorkoutTemplate(name: ""))
        self.isDraftReview = isDraftReview
        self.critiqueNote = critiqueNote
    }

    var body: some View {
        NavigationView {
            List {
                if isDraftReview {
                    Section {
                        VStack(alignment: .leading, spacing: 6) {
                            Label("AI-drafted routine — review before saving", systemImage: "sparkles")
                                .font(.caption.weight(.semibold))
                                .foregroundColor(settings.accentColor)
                            if let critiqueNote, !critiqueNote.isEmpty {
                                Text(critiqueNote).font(.caption).foregroundColor(.secondary)
                            }
                        }
                    }
                }

                Section {
                    TextField("Template name (e.g. Push Day A)", text: $draft.name)
                }

                Section("Default Rest") {
                    HStack {
                        restPill(label: "Between sets", seconds: $draft.defaultRestBetweenSets)
                        restPill(label: "Between exercises", seconds: $draft.defaultRestBetweenExercises)
                    }
                    .padding(.vertical, 2)
                }

                Section("Exercises") {
                    ForEach($draft.blocks) { $block in
                        let idx = draft.blocks.firstIndex { $0.id == block.id } ?? 0
                        BlockEditorCard(
                            block: $block,
                            canCombineWithNext: idx < draft.blocks.count - 1 && draft.blocks[idx].kind == .single && draft.blocks[idx + 1].kind == .single,
                            onCombineWithNext: { combineWithNext(idx) },
                            onSplit: { split(idx) },
                            onDelete: { draft.blocks.removeAll { $0.id == block.id } }
                        )
                    }
                    .onMove { draft.blocks.move(fromOffsets: $0, toOffset: $1) }

                    ExercisePickerField(placeholder: "Add exercise…") { exercise in
                        draft.blocks.append(.single(exerciseId: exercise.id, sets: [.reps(8)]))
                    }
                }
            }
            .listStyle(.insetGrouped)
            .environment(\.editMode, .constant(.active))
            .navigationTitle(isDraftReview ? "Review Draft" : (existing == nil ? "New Template" : "Edit Template"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    if isDraftReview {
                        Button("Discard", role: .destructive) { discardDraft() }
                    } else {
                        Button("Cancel") { dismiss() }
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    if isDraftReview {
                        Button("Approve") { approveDraft() }
                            .fontWeight(.semibold)
                            .disabled(draft.name.trimmingCharacters(in: .whitespaces).isEmpty || draft.blocks.isEmpty)
                    } else {
                        Button("Save") { save() }
                            .fontWeight(.semibold)
                            .disabled(draft.name.trimmingCharacters(in: .whitespaces).isEmpty || draft.blocks.isEmpty)
                    }
                }
            }
        }
    }

    private func restPill(label: String, seconds: Binding<Int>) -> some View {
        VStack(spacing: 4) {
            Text(label).font(.caption2).foregroundColor(.secondary)
            Stepper("\(seconds.wrappedValue)s", value: seconds, in: 0...600, step: 15)
                .font(.caption.weight(.medium))
        }
        .padding(8)
        .background(Color(.secondarySystemBackground))
        .cornerRadius(Theme.radiusSM)
        .frame(maxWidth: .infinity)
    }

    private func combineWithNext(_ idx: Int) {
        guard idx < draft.blocks.count - 1 else { return }
        let a = draft.blocks[idx]
        let b = draft.blocks[idx + 1]
        guard a.kind == .single, b.kind == .single, let exA = a.exerciseId, let exB = b.exerciseId else { return }
        let merged = Block.superset(exerciseIdA: exA, exerciseIdB: exB, setsA: [.reps(8)], setsB: [.reps(8)], restAfterRound: 60)
        draft.blocks.replaceSubrange(idx...(idx + 1), with: [merged])
    }

    private func split(_ idx: Int) {
        guard idx < draft.blocks.count else { return }
        let block = draft.blocks[idx]
        guard block.kind == .superset, let exA = block.exerciseIdA, let exB = block.exerciseIdB else { return }
        let blockA = Block.single(exerciseId: exA, sets: block.setsA.isEmpty ? [.reps(8)] : block.setsA)
        let blockB = Block.single(exerciseId: exB, sets: block.setsB.isEmpty ? [.reps(8)] : block.setsB)
        draft.blocks.replaceSubrange(idx...idx, with: [blockA, blockB])
    }

    private func save() {
        let name = draft.name.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return }
        draft.name = name
        store.saveTemplate(draft)
        dismiss()
    }

    /// Nothing is silently finalized: dropping a draft just deletes it
    /// (it was only ever server-side + this local review copy, never a
    /// "real" saved template).
    private func discardDraft() {
        store.deleteTemplate(draft.id)
        dismiss()
    }

    /// Pushes any edits made in the review sheet first (still tagged
    /// 'draft', so a save-only failure here doesn't accidentally finalize
    /// unreviewed content), then flips status via the dedicated approve
    /// endpoint.
    private func approveDraft() {
        let name = draft.name.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return }
        draft.name = name
        store.saveTemplate(draft)
        store.approveTemplate(draft.id)
        dismiss()
    }
}

// MARK: - Block editor card

private struct BlockEditorCard: View {
    @EnvironmentObject var settings: AppSettings
    @ObservedObject private var store = WorkoutStore.shared

    @Binding var block: Block
    let canCombineWithNext: Bool
    let onCombineWithNext: () -> Void
    let onSplit: () -> Void
    let onDelete: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            header

            if block.kind == .single {
                singleBody
            } else {
                supersetBody
            }
        }
        .padding(.vertical, 4)
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                if block.kind == .single {
                    Text(exerciseName(block.exerciseId)).font(.subheadline.weight(.semibold))
                } else {
                    Text("\(exerciseName(block.exerciseIdA)) + \(exerciseName(block.exerciseIdB))")
                        .font(.subheadline.weight(.semibold))
                    Text("Superset").font(.caption2).foregroundColor(settings.accentColor)
                }
            }
            Spacer()
            Menu {
                if block.kind == .single, canCombineWithNext {
                    Button("Combine with Next as Superset", action: onCombineWithNext)
                }
                if block.kind == .superset {
                    Button("Split into Two Exercises", action: onSplit)
                }
                Button("Remove", role: .destructive, action: onDelete)
            } label: {
                Image(systemName: "ellipsis.circle").foregroundColor(.secondary)
            }
        }
    }

    private func exerciseName(_ id: UUID?) -> String {
        guard let id else { return "—" }
        return store.exercise(id)?.name ?? "—"
    }

    // MARK: single

    private var singleBody: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(block.sets.enumerated()), id: \.element.id) { i, _ in
                SetRow(set: bindingForSet(i)) {
                    block.sets.remove(at: i)
                }
            }
            HStack {
                Button {
                    block.sets.append(block.sets.last ?? .reps(8))
                } label: {
                    Label("Add Set", systemImage: "plus")
                        .font(.caption.weight(.medium))
                        .foregroundColor(settings.accentColor)
                }
                .buttonStyle(.plain)

                Spacer()

                Stepper(restOverrideLabel,
                        onIncrement: { bumpOverride(15) },
                        onDecrement: { bumpOverride(-15) })
                    .font(.caption2)
                    .fixedSize()
            }
        }
    }

    private var restOverrideLabel: String {
        if let v = block.restBetweenSetsOverride { return "Rest \(v)s" }
        return "Rest default"
    }

    private func bumpOverride(_ delta: Int) {
        let base = block.restBetweenSetsOverride ?? 0
        let next = max(0, base + delta)
        block.restBetweenSetsOverride = next
    }

    private func bindingForSet(_ i: Int) -> Binding<SetTemplate> {
        Binding(get: { block.sets[i] }, set: { block.sets[i] = $0 })
    }

    // MARK: superset

    private var supersetBody: some View {
        let rounds = max(block.setsA.count, block.setsB.count)
        return VStack(alignment: .leading, spacing: 8) {
            ForEach(0..<rounds, id: \.self) { r in
                VStack(alignment: .leading, spacing: 4) {
                    Text("Round \(r + 1)").font(.caption2).foregroundColor(.secondary)
                    if r < block.setsA.count {
                        SetRow(set: bindingForSetA(r), label: exerciseName(block.exerciseIdA)) {
                            removeRound(r)
                        }
                    }
                    if r < block.setsB.count {
                        SetRow(set: bindingForSetB(r), label: exerciseName(block.exerciseIdB)) {
                            removeRound(r)
                        }
                    }
                }
            }
            HStack {
                Button {
                    block.setsA.append(block.setsA.last ?? .reps(8))
                    block.setsB.append(block.setsB.last ?? .reps(8))
                } label: {
                    Label("Add Round", systemImage: "plus")
                        .font(.caption.weight(.medium))
                        .foregroundColor(settings.accentColor)
                }
                .buttonStyle(.plain)

                Spacer()

                Stepper("Rest after round \(block.restAfterRound ?? 60)s",
                        value: Binding(get: { block.restAfterRound ?? 60 }, set: { block.restAfterRound = $0 }),
                        in: 0...600, step: 15)
                    .font(.caption2)
                    .fixedSize()
            }
        }
    }

    private func removeRound(_ r: Int) {
        if r < block.setsA.count { block.setsA.remove(at: r) }
        if r < block.setsB.count { block.setsB.remove(at: r) }
    }

    private func bindingForSetA(_ i: Int) -> Binding<SetTemplate> {
        Binding(get: { block.setsA[i] }, set: { block.setsA[i] = $0 })
    }
    private func bindingForSetB(_ i: Int) -> Binding<SetTemplate> {
        Binding(get: { block.setsB[i] }, set: { block.setsB[i] = $0 })
    }
}

// MARK: - Single set row (reps×weight, or seconds — mixed types allowed)

private struct SetRow: View {
    @Binding var set: SetTemplate
    var label: String? = nil
    let onDelete: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            if let label {
                Text(label).font(.caption2).foregroundColor(.secondary).frame(width: 60, alignment: .leading)
            }

            Picker("", selection: Binding(
                get: { set.type },
                set: { newType in
                    set.type = newType
                    if newType == .reps, set.targetReps == nil { set.targetReps = 8 }
                    if newType == .time, set.targetSeconds == nil { set.targetSeconds = 30 }
                }
            )) {
                Text("Reps").tag(SetType.reps)
                Text("Time").tag(SetType.time)
            }
            .pickerStyle(.segmented)
            .frame(width: 110)

            if set.type == .reps {
                Stepper("\(set.targetReps ?? 8)", value: Binding(
                    get: { set.targetReps ?? 8 }, set: { set.targetReps = $0 }
                ), in: 1...100)
                .font(.caption)

                Stepper(weightLabel, value: Binding(
                    get: { set.weightKg ?? 0 }, set: { set.weightKg = $0 == 0 ? nil : $0 }
                ), in: 0...300, step: 1.25)
                .font(.caption)
            } else {
                Stepper("\(set.targetSeconds ?? 30)s", value: Binding(
                    get: { set.targetSeconds ?? 30 }, set: { set.targetSeconds = $0 }
                ), in: 5...600, step: 5)
                .font(.caption)
            }

            Spacer(minLength: 0)

            Button(action: onDelete) {
                Image(systemName: "minus.circle.fill").foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
        }
    }

    private var weightLabel: String {
        guard let w = set.weightKg, w > 0 else { return "BW" }
        return "\(w.formattedKg)kg"
    }
}

extension Double {
    /// Compact kg display: whole numbers with no trailing ".0", otherwise one decimal.
    var formattedKg: String {
        self.truncatingRemainder(dividingBy: 1) == 0 ? String(format: "%.0f", self) : String(format: "%.1f", self)
    }
}

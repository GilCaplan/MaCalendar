import SwiftUI

/// A past session, opened for viewing/editing. Every logged value is
/// editable after the fact — matches the Mac Timer's edit-after-the-fact
/// precedent. Delete removes the whole session.
struct SessionDetailView: View {
    @EnvironmentObject var settings: AppSettings
    @ObservedObject private var store = WorkoutStore.shared
    @Environment(\.dismiss) private var dismiss

    @State private var session: WorkoutSession

    init(session: WorkoutSession) {
        _session = State(initialValue: session)
    }

    var body: some View {
        NavigationView {
            List {
                Section {
                    HStack {
                        Text("Started")
                        Spacer()
                        Text(dateLabel(session.startedAt)).foregroundColor(.secondary)
                    }
                    if let end = session.endedAt {
                        HStack {
                            Text("Duration")
                            Spacer()
                            Text("\(Int(end.timeIntervalSince(session.startedAt) / 60)) min").foregroundColor(.secondary)
                        }
                    }
                    TextField("Notes", text: $session.notes, axis: .vertical)
                        .onChange(of: session.notes) { _ in save() }
                }

                if session.setLogs.isEmpty {
                    Text("No sets logged").font(.subheadline).foregroundColor(.secondary)
                } else {
                    ForEach(exerciseGroups, id: \.exerciseId) { group in
                        Section(store.exercise(group.exerciseId)?.name ?? "Exercise") {
                            ForEach(group.logs) { log in
                                LogEditRow(log: bindingForLog(log.id))
                            }
                        }
                    }
                }
            }
            .navigationTitle("Session")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Close") { dismiss() }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(role: .destructive) {
                        store.deleteSession(session.id)
                        dismiss()
                    } label: {
                        Image(systemName: "trash")
                    }
                }
            }
        }
    }

    private var exerciseGroups: [(exerciseId: UUID, logs: [SetLog])] {
        var order: [UUID] = []
        var map: [UUID: [SetLog]] = [:]
        for log in session.setLogs {
            if map[log.exerciseId] == nil { order.append(log.exerciseId) }
            map[log.exerciseId, default: []].append(log)
        }
        return order.map { (exerciseId: $0, logs: map[$0] ?? []) }
    }

    private func bindingForLog(_ id: UUID) -> Binding<SetLog> {
        Binding(
            get: { session.setLogs.first { $0.id == id } ?? SetLog(exerciseId: UUID(), setIndex: 0, type: .reps) },
            set: { newVal in
                guard let i = session.setLogs.firstIndex(where: { $0.id == id }) else { return }
                session.setLogs[i] = newVal
                save()
            }
        )
    }

    private func save() { store.updateSession(session) }

    private func dateLabel(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .short
        return f.string(from: date)
    }
}

private struct LogEditRow: View {
    @Binding var log: SetLog

    var body: some View {
        HStack(spacing: 8) {
            Text("Set \(log.setIndex + 1)")
                .font(.caption2)
                .foregroundColor(.secondary)
                .frame(width: 44, alignment: .leading)

            if log.skipped {
                Text("Skipped").font(.caption).foregroundColor(.secondary)
                Spacer()
                Button("Log It") {
                    log.skipped = false
                    log.completedAt = log.completedAt ?? Date()
                    if log.type == .reps { log.actualReps = log.actualReps ?? 8 }
                    if log.type == .time { log.actualSeconds = log.actualSeconds ?? 30 }
                }
                .font(.caption)
            } else {
                if log.type == .reps {
                    Stepper("\(log.actualReps ?? 0)",
                            value: Binding(get: { log.actualReps ?? 0 }, set: { log.actualReps = $0 }),
                            in: 0...100)
                        .font(.caption)
                    Stepper(weightLabel,
                            value: Binding(get: { log.actualWeightKg ?? 0 }, set: { log.actualWeightKg = $0 == 0 ? nil : $0 }),
                            in: 0...300, step: 1.25)
                        .font(.caption)
                } else {
                    Stepper("\(log.actualSeconds ?? 0)s",
                            value: Binding(get: { log.actualSeconds ?? 0 }, set: { log.actualSeconds = $0 }),
                            in: 0...600, step: 5)
                        .font(.caption)
                }
                Spacer(minLength: 0)
                Button("Skip") {
                    log.skipped = true
                    log.completedAt = nil
                }
                .font(.caption2)
                .foregroundColor(.secondary)
            }
        }
    }

    private var weightLabel: String {
        guard let w = log.actualWeightKg, w > 0 else { return "BW" }
        return "\(w.formattedKg)kg"
    }
}

import SwiftUI
import Charts

struct WorkoutStatsView: View {
    @EnvironmentObject var settings: AppSettings
    @ObservedObject private var store = WorkoutStore.shared
    @Environment(\.dismiss) private var dismiss

    enum RangeMode: String, CaseIterable { case week = "Week", month = "Month", all = "All-time" }
    @State private var rangeMode: RangeMode = .week

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Picker("Range", selection: $rangeMode) {
                        ForEach(RangeMode.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                    }
                    .pickerStyle(.segmented)

                    summaryTiles
                    weeklyVolumeChart
                    exerciseTrends
                }
                .padding()
            }
            .navigationTitle("Stats")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    // MARK: - Range

    private var range: ClosedRange<Date> {
        let now = Date()
        switch rangeMode {
        case .week:
            let start = Calendar.current.date(byAdding: .day, value: -7, to: now) ?? now
            return start...now
        case .month:
            let start = Calendar.current.date(byAdding: .month, value: -1, to: now) ?? now
            return start...now
        case .all:
            return Date.distantPast...now
        }
    }

    private var sessionsInRange: [WorkoutSession] { store.filteredSessions(in: range) }

    // MARK: - Summary tiles

    private var summaryTiles: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            statTile("Workouts", "\(sessionsInRange.count)")
            statTile("Total Sets", "\(totalSets)")
            statTile("Volume", "\(Int(totalVolume)) kg")
            statTile("Time", timeLabel)
        }
    }

    private var totalSets: Int {
        sessionsInRange.reduce(0) { $0 + $1.setLogs.filter { !$0.skipped }.count }
    }

    private var totalVolume: Double {
        sessionsInRange.reduce(0.0) { sum, session in
            sum + session.setLogs
                .filter { !$0.skipped && $0.type == .reps }
                .reduce(0.0) { s, log in s + Double(log.actualReps ?? 0) * (log.actualWeightKg ?? 0) }
        }
    }

    private var totalTrainingSeconds: Double {
        sessionsInRange.reduce(0.0) { sum, session in
            guard let end = session.endedAt else { return sum }
            return sum + end.timeIntervalSince(session.startedAt)
        }
    }

    private var timeLabel: String {
        let total = Int(totalTrainingSeconds)
        let hrs = total / 3600
        let mins = (total % 3600) / 60
        return hrs > 0 ? "\(hrs)h \(mins)m" : "\(mins)m"
    }

    private func statTile(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(value).font(.title2.weight(.bold))
            Text(label).font(.caption).foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(Theme.radiusMD)
    }

    // MARK: - Weekly volume chart

    private struct WeekBucket: Identifiable {
        let id = UUID()
        let weekStart: Date
        let volume: Double
    }

    private var weeklyBuckets: [WeekBucket] {
        let cal = Calendar.current
        var buckets: [Date: Double] = [:]
        for session in sessionsInRange {
            guard let weekStart = cal.dateInterval(of: .weekOfYear, for: session.startedAt)?.start else { continue }
            let vol = session.setLogs
                .filter { !$0.skipped && $0.type == .reps }
                .reduce(0.0) { s, log in s + Double(log.actualReps ?? 0) * (log.actualWeightKg ?? 0) }
            buckets[weekStart, default: 0] += vol
        }
        return buckets.map { WeekBucket(weekStart: $0.key, volume: $0.value) }.sorted { $0.weekStart < $1.weekStart }
    }

    private var weeklyVolumeChart: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Weekly Volume").font(.headline)
            if weeklyBuckets.isEmpty {
                Text("No data yet").font(.caption).foregroundColor(.secondary)
            } else {
                Chart(weeklyBuckets) { bucket in
                    BarMark(
                        x: .value("Week", bucket.weekStart, unit: .weekOfYear),
                        y: .value("Volume", bucket.volume)
                    )
                    .foregroundStyle(settings.accentColor)
                }
                .frame(height: 160)
            }
        }
    }

    // MARK: - Per-exercise trend rows

    private struct ExerciseTrend: Identifiable {
        let id: UUID
        let name: String
        let topSetLabel: String
        let bestRepsLabel: String
        let longestHoldLabel: String
    }

    private var exerciseTrends: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Exercises").font(.headline)
            if trends.isEmpty {
                Text("No data yet").font(.caption).foregroundColor(.secondary)
            } else {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(trends) { t in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(t.name).font(.subheadline.weight(.semibold))
                            Text("Top set \(t.topSetLabel) · Best reps \(t.bestRepsLabel) · Longest hold \(t.longestHoldLabel)")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                        .padding(.vertical, 6)
                        Divider()
                    }
                }
            }
        }
    }

    private var trends: [ExerciseTrend] {
        let logs = sessionsInRange.flatMap { $0.setLogs }.filter { !$0.skipped }
        let byExercise = Dictionary(grouping: logs, by: { $0.exerciseId })
        return byExercise.compactMap { exId, exerciseLogs -> ExerciseTrend? in
            guard let name = store.exercise(exId)?.name else { return nil }
            let repLogs = exerciseLogs.filter { $0.type == .reps }
            let timeLogs = exerciseLogs.filter { $0.type == .time }

            let topSet = repLogs.max { ($0.actualWeightKg ?? 0) < ($1.actualWeightKg ?? 0) }
            let topSetLabel = topSet.map { "\($0.actualReps ?? 0)×\(($0.actualWeightKg ?? 0).formattedKg)kg" } ?? "—"

            let bestReps = repLogs.compactMap { $0.actualReps }.max()
            let bestRepsLabel = bestReps.map { "\($0)" } ?? "—"

            let longestHold = timeLogs.compactMap { $0.actualSeconds }.max()
            let longestHoldLabel = longestHold.map { "\($0)s" } ?? "—"

            return ExerciseTrend(id: exId, name: name, topSetLabel: topSetLabel,
                                  bestRepsLabel: bestRepsLabel, longestHoldLabel: longestHoldLabel)
        }
        .sorted { $0.name < $1.name }
    }
}

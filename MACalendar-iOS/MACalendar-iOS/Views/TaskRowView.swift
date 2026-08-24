import SwiftUI

/// Small pill used for task tags everywhere in the Tasks tab (rows, filter bar,
/// tag pickers). `selected` fills it with the tag color; otherwise it's outlined.
struct TagChip: View {
    let name: String
    let hex: String
    var selected: Bool = true
    var compact: Bool = false

    private var color: Color { Color(hex: hex) ?? .accentColor }

    var body: some View {
        Text(name)
            .font(.system(size: compact ? 10 : 12, weight: .semibold))
            .lineLimit(1)
            .padding(.horizontal, compact ? 6 : 10)
            .padding(.vertical, compact ? 2 : 5)
            .background(
                Capsule().fill(selected ? color.opacity(0.9) : color.opacity(0.12))
            )
            .overlay(Capsule().stroke(color.opacity(selected ? 0 : 0.6), lineWidth: 1))
            .foregroundColor(selected ? Color.onColor(hex: hex) : color)
    }
}

struct TaskRowView: View {
    @EnvironmentObject var settings: AppSettings
    var todo: Todo
    var allTags: [TodoTag]
    var onToggle: () -> Void
    var onDelete: () -> Void
    var onSave: (String, String, String, [String]) -> Void  // title, priority, dueDate, tags

    @State private var isExpanded = false
    @State private var editTitle: String
    @State private var editPriority: String
    @State private var editDueDate: Date?
    @State private var editTags: [String]

    private static let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    init(todo: Todo,
         allTags: [TodoTag] = [],
         onToggle: @escaping () -> Void,
         onDelete: @escaping () -> Void,
         onSave: @escaping (String, String, String, [String]) -> Void) {
        self.todo = todo
        self.allTags = allTags
        self.onToggle = onToggle
        self.onDelete = onDelete
        self.onSave = onSave
        _editTitle    = State(initialValue: todo.title)
        _editPriority = State(initialValue: todo.priority)
        _editDueDate  = State(initialValue: Self.dateFormatter.date(from: todo.dueDate))
        _editTags     = State(initialValue: todo.tags)
    }

    private func hex(for name: String) -> String {
        allTags.first { $0.name.caseInsensitiveCompare(name) == .orderedSame }?.hexColor
            ?? TodoTag(name: name).hexColor
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {

            // ── Main row ──────────────────────────────────────────────
            HStack(spacing: 12) {
                Button(action: onToggle) {
                    Image(systemName: todo.isDone ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: settings.fontTasks + 4))
                        .foregroundColor(todo.isDone ? settings.accentColor : .secondary)
                }
                .buttonStyle(.plain)

                VStack(alignment: .leading, spacing: 4) {
                    Text(todo.title)
                        .font(.system(size: settings.fontTasks))
                        .strikethrough(todo.isDone)
                        .foregroundColor(todo.isDone ? .secondary : .primary)

                    if !todo.tags.isEmpty && !isExpanded {
                        HStack(spacing: 4) {
                            ForEach(todo.tags, id: \.self) { t in
                                TagChip(name: t, hex: hex(for: t), selected: true, compact: true)
                                    .opacity(todo.isDone ? 0.5 : 1)
                            }
                        }
                    }
                }

                Spacer()

                // Use .highPriorityGesture on a plain Image — NOT a Button.
                // Button inside a List row conflicts with the row's swipe gesture
                // recognizer even with .buttonStyle(.plain), causing the swipe-delete
                // action to fire on tap. A bare onTapGesture / highPriorityGesture
                // on a non-Button view bypasses that conflict entirely.
                Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.secondary)
                    .frame(width: 32, height: 32)
                    .contentShape(Rectangle())
                    .highPriorityGesture(
                        TapGesture().onEnded { toggleExpand() }
                    )
            }

            // ── Expanded detail panel ─────────────────────────────────
            if isExpanded {
                VStack(alignment: .leading, spacing: 10) {
                    // Editable title
                    TextField("Title", text: $editTitle)
                        .font(.system(size: settings.fontTasks - 1))
                        .textFieldStyle(.roundedBorder)
                        .submitLabel(.done)

                    // Tags — tap to toggle membership
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Tags")
                            .font(.system(size: settings.fontTasks - 2))
                            .foregroundColor(.secondary)
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 6) {
                                ForEach(allTags) { tag in
                                    let on = editTags.contains { $0.caseInsensitiveCompare(tag.name) == .orderedSame }
                                    TagChip(name: tag.name, hex: tag.hexColor, selected: on)
                                        .contentShape(Capsule())
                                        .onTapGesture { toggleTag(tag.name) }
                                }
                                if allTags.isEmpty {
                                    Text("No tags yet — add one with the tag button above.")
                                        .font(.system(size: settings.fontTasks - 3))
                                        .foregroundColor(.secondary)
                                }
                            }
                            .padding(.vertical, 2)
                        }
                    }

                    // Priority picker
                    HStack(spacing: 6) {
                        Text("Priority")
                            .font(.system(size: settings.fontTasks - 2))
                            .foregroundColor(.secondary)
                        Picker("Priority", selection: $editPriority) {
                            Text("None").tag("")
                            Text("Low").tag("low")
                            Text("Medium").tag("medium")
                            Text("High").tag("high")
                        }
                        .pickerStyle(.menu)
                        .labelsHidden()
                    }

                    // Due date picker + clear button
                    HStack(spacing: 6) {
                        Text("Due date")
                            .font(.system(size: settings.fontTasks - 2))
                            .foregroundColor(.secondary)

                        DatePicker(
                            "",
                            selection: Binding(
                                get: { editDueDate ?? Date() },
                                set: { editDueDate = $0 }
                            ),
                            displayedComponents: .date
                        )
                        .labelsHidden()
                        .opacity(editDueDate == nil ? 0.4 : 1)

                        if editDueDate == nil {
                            Button("Set") { editDueDate = Date() }
                                .font(.system(size: settings.fontTasks - 2))
                                .buttonStyle(.plain)
                                .foregroundColor(settings.accentColor)
                        } else {
                            Button(action: { editDueDate = nil }) {
                                Image(systemName: "xmark.circle.fill")
                                    .foregroundColor(.secondary)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .padding(.top, 10)
                .padding(.horizontal, 4)
                .padding(.bottom, 6)
            }
        }
        // Keep edit fields in sync when the parent refreshes (but only when closed
        // so we don't stomp on the user's in-progress edits).
        .onChange(of: todo) { newTodo in
            guard !isExpanded else { return }
            editTitle    = newTodo.title
            editPriority = newTodo.priority
            editDueDate  = Self.dateFormatter.date(from: newTodo.dueDate)
            editTags     = newTodo.tags
        }
        .swipeActions(edge: .trailing) {
            Button(role: .destructive, action: onDelete) {
                Label("Delete", systemImage: "trash")
            }
        }
    }

    private func toggleTag(_ name: String) {
        if let i = editTags.firstIndex(where: { $0.caseInsensitiveCompare(name) == .orderedSame }) {
            editTags.remove(at: i)
        } else {
            editTags.append(name)
        }
    }

    private func toggleExpand() {
        if isExpanded {
            // Collapsing — persist edits
            let dueDateStr = editDueDate.map { Self.dateFormatter.string(from: $0) } ?? ""
            onSave(editTitle, editPriority, dueDateStr, editTags)
        }
        withAnimation(.easeInOut(duration: 0.2)) {
            isExpanded.toggle()
        }
    }
}

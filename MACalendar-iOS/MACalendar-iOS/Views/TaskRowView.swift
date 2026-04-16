import SwiftUI

struct TaskRowView: View {
    @EnvironmentObject var settings: AppSettings
    var todo: Todo
    var onToggle: () -> Void
    var onDelete: () -> Void
    var onSave: (String, String, String) -> Void  // title, priority, dueDate

    @State private var isExpanded = false
    @State private var editTitle: String
    @State private var editPriority: String
    @State private var editDueDate: Date?

    private static let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    init(todo: Todo,
         onToggle: @escaping () -> Void,
         onDelete: @escaping () -> Void,
         onSave: @escaping (String, String, String) -> Void) {
        self.todo = todo
        self.onToggle = onToggle
        self.onDelete = onDelete
        self.onSave = onSave
        _editTitle    = State(initialValue: todo.title)
        _editPriority = State(initialValue: todo.priority)
        _editDueDate  = State(initialValue: Self.dateFormatter.date(from: todo.dueDate))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {

            // ── Main row ──────────────────────────────────────────────
            HStack(spacing: 12) {
                Button(action: onToggle) {
                    Image(systemName: todo.isDone ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: settings.fontTasks + 4))
                        .foregroundColor(todo.isDone ? .blue : .secondary)
                }
                .buttonStyle(.plain)

                Text(todo.title)
                    .font(.system(size: settings.fontTasks))
                    .strikethrough(todo.isDone)
                    .foregroundColor(todo.isDone ? .secondary : .primary)

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
                                .foregroundColor(.blue)
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
        }
        .swipeActions(edge: .trailing) {
            Button(role: .destructive, action: onDelete) {
                Label("Delete", systemImage: "trash")
            }
        }
    }

    private func toggleExpand() {
        if isExpanded {
            // Collapsing — persist edits
            let dueDateStr = editDueDate.map { Self.dateFormatter.string(from: $0) } ?? ""
            onSave(editTitle, editPriority, dueDateStr)
        }
        withAnimation(.easeInOut(duration: 0.2)) {
            isExpanded.toggle()
        }
    }
}

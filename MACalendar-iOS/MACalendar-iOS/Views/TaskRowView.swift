import SwiftUI

struct TaskRowView: View {
    @EnvironmentObject var settings: AppSettings
    var todo: Todo
    var onToggle: () -> Void
    var onDelete: () -> Void

    var body: some View {
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
        }
        .swipeActions(edge: .trailing) {
            Button(role: .destructive, action: onDelete) {
                Label("Delete", systemImage: "trash")
            }
        }
    }
}

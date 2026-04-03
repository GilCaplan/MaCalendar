import SwiftUI

struct TasksView: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var settings: AppSettings

    @State private var todos: [Todo] = []
    @State private var newTaskTitle = ""
    @State private var newTaskList = "today"
    @State private var loading = false
    @State private var errorMsg: String?
    @State private var editMode: EditMode = .inactive

    private var todayTasks: [Todo]   { todos.filter { $0.list == "today" } }
    private var generalTasks: [Todo] { todos.filter { $0.list == "general" } }

    private var hasCompleted: Bool {
        todos.contains { $0.isDone }
    }

    var body: some View {
        NavigationView {
            List {
                // ── Manual add row ──
                Section {
                    HStack {
                        TextField("Add task…", text: $newTaskTitle)
                            .submitLabel(.done)
                            .onSubmit(addTask)
                        Picker("", selection: $newTaskList) {
                            Text("Today").tag("today")
                            Text("General").tag("general")
                        }
                        .pickerStyle(.menu)
                        .labelsHidden()
                        Button(action: addTask) {
                            Image(systemName: "plus.circle.fill")
                                .foregroundColor(.blue)
                        }
                        .disabled(newTaskTitle.isEmpty)
                    }
                }

                Section(header: Text("Today").font(.system(size: settings.fontTasks, weight: .bold))) {
                    if todayTasks.isEmpty {
                        Text("No tasks for today").font(.system(size: settings.fontTasks - 2)).foregroundColor(.secondary)
                    } else {
                        ForEach(todayTasks) { todo in
                            TaskRowView(
                                todo: todo,
                                onToggle: { toggle(todo) },
                                onDelete: { delete(todo) }
                            )
                            .onDrag { NSItemProvider(object: "\(todo.id)" as NSString) }
                        }
                        .onMove { from, to in moveTasksWithin(list: "today", from: from, to: to) }
                        .onDelete { offsets in deleteTasks(list: "today", at: offsets) }
                    }
                }
                .onDrop(of: ["public.text"], isTargeted: nil) { providers in
                    handleDrop(providers: providers, toList: "today")
                }

                Section(header: Text("General").font(.system(size: settings.fontTasks, weight: .bold))) {
                    if generalTasks.isEmpty {
                        Text("No general tasks").font(.system(size: settings.fontTasks - 2)).foregroundColor(.secondary)
                    } else {
                        ForEach(generalTasks) { todo in
                            TaskRowView(
                                todo: todo,
                                onToggle: { toggle(todo) },
                                onDelete: { delete(todo) }
                            )
                            .onDrag { NSItemProvider(object: "\(todo.id)" as NSString) }
                        }
                        .onMove { from, to in moveTasksWithin(list: "general", from: from, to: to) }
                        .onDelete { offsets in deleteTasks(list: "general", at: offsets) }
                    }
                }
                .onDrop(of: ["public.text"], isTargeted: nil) { providers in
                    handleDrop(providers: providers, toList: "general")
                }
            }
            .environment(\.editMode, $editMode)
            .navigationTitle("Tasks")
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    if hasCompleted {
                        Button(action: clearCompleted) {
                            Label("Clear Done", systemImage: "trash.slash")
                                .foregroundColor(.red)
                        }
                    }
                }
                ToolbarItemGroup(placement: .navigationBarTrailing) {
                    Button(action: { withAnimation { editMode = editMode == .active ? .inactive : .active } }) {
                        Text(editMode == .active ? "Done" : "Edit")
                    }
                    Button(action: load) {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            }
            .overlay {
                if loading { ProgressView() }
            }
            .safeAreaInset(edge: .bottom) {
                // Reserve space so the floating VoiceButton doesn't cover list items
                Color.clear.frame(height: 100)
            }
            .task { load() }
            .overlay(alignment: .bottom) {
                VoiceButton(onRefresh: { refresh in
                    if refresh == "todos" || refresh == "both" { load() }
                })
                .padding(.bottom, 24)
            }
        }
    }

    // MARK: - Data

    private func load() {
        loading = true
        Task {
            do {
                todos = try await api.todos(list: "all", includeCompleted: true)
            } catch {
                errorMsg = error.localizedDescription
            }
            loading = false
        }
    }

    private func addTask() {
        guard !newTaskTitle.isEmpty else { return }
        let title = newTaskTitle
        let list  = newTaskList
        newTaskTitle = ""
        Task {
            _ = try? await api.createTodo(title: title, list: list)
            load()
        }
    }

    private func toggle(_ todo: Todo) {
        Task {
            _ = try? await api.toggleTodo(id: todo.id)
            load()
        }
    }

    private func delete(_ todo: Todo) {
        Task {
            try? await api.deleteTodo(id: todo.id)
            todos.removeAll { $0.id == todo.id }
        }
    }

    private func deleteTasks(list: String, at offsets: IndexSet) {
        let source = list == "today" ? todayTasks : generalTasks
        for i in offsets {
            let todo = source[i]
            Task { try? await api.deleteTodo(id: todo.id) }
            todos.removeAll { $0.id == todo.id }
        }
    }

    private func moveTasksWithin(list: String, from: IndexSet, to: Int) {
        var arr = list == "today" ? todayTasks : generalTasks
        arr.move(fromOffsets: from, toOffset: to)
        let ids = arr.map { $0.id }
        // Optimistic local reorder
        let moved = arr
        todos = todos.filter { $0.list != list } + moved
        Task { try? await api.reorderTodos(list: list, ids: ids) }
    }

    private func handleDrop(providers: [NSItemProvider], toList: String) -> Bool {
        guard let provider = providers.first else { return false }
        provider.loadObject(ofClass: NSString.self) { string, _ in
            guard let idStr = string as? String, let id = Int(idStr) else { return }
            DispatchQueue.main.async {
                if let idx = todos.firstIndex(where: { $0.id == id }) {
                    var todo = todos[idx]
                    if todo.list != toList {
                        todo.list = toList
                        todos[idx] = todo
                        Task { try? await api.updateTodo(id: id, list: toList) }
                    }
                }
            }
        }
        return true
    }

    private func clearCompleted() {
        todos.removeAll { $0.isDone }
        Task {
            try? await api.clearCompletedTodos()
            load()
        }
    }
}

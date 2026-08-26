import SwiftUI

struct TasksView: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var settings: AppSettings

    @State private var todos: [Todo] = []
    @State private var tags: [TodoTag] = []
    @State private var newTaskTitle = ""
    @State private var newTaskList = "today"
    @State private var loading = false
    @State private var errorMsg: String?
    @State private var editMode: EditMode = .inactive
    @State private var showManageTags = false

    static let untaggedKey = "__untagged__"

    // MARK: - Derived

    /// Tag applied to tasks added from the add row:
    /// explicit "tag mode" wins; otherwise, while filtering by a tag, new tasks
    /// inherit that tag so they don't vanish from the list you're looking at.
    private var effectiveAutoTags: [String] {
        if !settings.taskAutoTag.isEmpty { return [settings.taskAutoTag] }
        return settings.taskTagFilters.filter { $0 != Self.untaggedKey }
    }

    /// True when `todo` matches any of the selected filters (or nothing is selected).
    private func matchesFilter(_ todo: Todo) -> Bool {
        let f = settings.taskTagFilters
        if f.isEmpty { return true }
        for key in f {
            if key == Self.untaggedKey {
                if todo.tags.isEmpty { return true }
            } else if todo.hasTag(key) {
                return true
            }
        }
        return false
    }

    private var visibleTodos: [Todo] {
        let v = settings.hideCompletedTasks ? todos.filter { !$0.isDone } : todos
        return v.filter(matchesFilter)
    }
    private var todayTasks: [Todo]   { visibleTodos.filter { $0.list == "today" } }
    private var generalTasks: [Todo] { visibleTodos.filter { $0.list == "general" } }

    private var hasCompleted: Bool {
        todos.contains { $0.isDone }
    }

    private var isFiltering: Bool { !settings.taskTagFilters.isEmpty }

    private func hex(for name: String) -> String {
        tags.first { $0.name.caseInsensitiveCompare(name) == .orderedSame }?.hexColor
            ?? TodoTag(name: name).hexColor
    }

    private func count(for tagName: String) -> Int {
        let base = settings.hideCompletedTasks ? todos.filter { !$0.isDone } : todos
        if tagName == Self.untaggedKey { return base.filter { $0.tags.isEmpty }.count }
        return base.filter { $0.hasTag(tagName) }.count
    }

    // MARK: - Body

    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                filterBar
                    .padding(.vertical, 8)
                    .background(Color(.systemGroupedBackground))

                List {
                    // ── Manual add row ──
                    Section {
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                TextField(addPlaceholder, text: $newTaskTitle)
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
                                        .foregroundColor(settings.accentColor)
                                }
                                .disabled(newTaskTitle.isEmpty)
                            }
                            if !effectiveAutoTags.isEmpty {
                                HStack(spacing: 6) {
                                    Image(systemName: "tag.fill")
                                        .font(.system(size: 10))
                                        .foregroundColor(.secondary)
                                    Text(settings.taskAutoTag.isEmpty ? "New tasks get" : "Tag mode:")
                                        .font(.system(size: settings.fontTasks - 3))
                                        .foregroundColor(.secondary)
                                    ForEach(effectiveAutoTags, id: \.self) { t in
                                        TagChip(name: t, hex: hex(for: t), compact: true)
                                    }
                                }
                            }
                        }
                    }

                    Section(header: sectionHeader("Today", count: todayTasks.count)) {
                        if todayTasks.isEmpty {
                            Text(isFiltering ? "Nothing tagged here for today" : "No tasks for today")
                                .font(.system(size: settings.fontTasks - 2)).foregroundColor(.secondary)
                        } else {
                            ForEach(todayTasks) { todo in
                                row(for: todo)
                            }
                            .onMove { from, to in moveTasksWithin(list: "today", from: from, to: to) }
                            .onDelete { offsets in deleteTasks(list: "today", at: offsets) }
                        }
                    }
                    .onDrop(of: ["public.text"], isTargeted: nil) { providers in
                        handleDrop(providers: providers, toList: "today")
                    }

                    Section(header: sectionHeader("General", count: generalTasks.count)) {
                        if generalTasks.isEmpty {
                            Text(isFiltering ? "Nothing tagged here" : "No general tasks")
                                .font(.system(size: settings.fontTasks - 2)).foregroundColor(.secondary)
                        } else {
                            ForEach(generalTasks) { todo in
                                row(for: todo)
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
            }
            .navigationTitle(navTitle)
            .toolbar {
                ToolbarItemGroup(placement: .navigationBarLeading) {
                    if hasCompleted {
                        Button(action: { settings.hideCompletedTasks.toggle() }) {
                            Image(systemName: settings.hideCompletedTasks ? "eye" : "eye.slash")
                        }
                        .help(settings.hideCompletedTasks ? "Show completed" : "Hide completed")

                        Button(action: clearCompleted) {
                            Label("Clear Done", systemImage: "trash.slash")
                                .foregroundColor(.red)
                        }
                    }
                }
                ToolbarItemGroup(placement: .navigationBarTrailing) {
                    tagModeMenu
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
            // The list only refreshed on appear / pull, so a fetch that failed while the
            // Mac was restarting left it empty. Reload when the Mac comes back.
            .onReceive(api.$refreshTick) { _ in load() }
            .overlay(alignment: .bottom) {
                VoiceButton(onRefresh: { refresh in
                    if refresh == "todos" || refresh == "both" { load() }
                })
                .padding(.bottom, 24)
            }
            .sheet(isPresented: $showManageTags) {
                ManageTagsSheet(tags: $tags, onAdd: addTag, onDelete: deleteTag)
                    .environmentObject(settings)
            }
        }
    }

    // MARK: - Sub-views

    private var navTitle: String {
        let f = settings.taskTagFilters
        if f.isEmpty { return "Tasks" }
        return f.map { $0 == Self.untaggedKey ? "Untagged" : $0 }.joined(separator: " · ")
    }

    private var addPlaceholder: String {
        let f = settings.taskTagFilters
        if f.count == 1, f[0].caseInsensitiveCompare("groceries") == .orderedSame { return "Add grocery item…" }
        return "Add task…"
    }

    private func sectionHeader(_ title: String, count: Int) -> some View {
        HStack {
            Text(title).font(.system(size: settings.fontTasks, weight: .bold))
            if isFiltering && count > 0 {
                Text("\(count)")
                    .font(.system(size: settings.fontTasks - 4, weight: .semibold))
                    .foregroundColor(.secondary)
            }
        }
    }

    private func row(for todo: Todo) -> some View {
        TaskRowView(
            todo: todo,
            allTags: tags,
            onToggle: { toggle(todo) },
            onDelete: { delete(todo) },
            onSave:   { title, priority, dueDate, newTags in
                save(todo, title: title, priority: priority, dueDate: dueDate, tags: newTags)
            }
        )
        .onDrag { NSItemProvider(object: "\(todo.id)" as NSString) }
        .contextMenu {
            Menu("Tags") {
                ForEach(tags) { tag in
                    Button {
                        var t = todo.tags
                        if let i = t.firstIndex(where: { $0.caseInsensitiveCompare(tag.name) == .orderedSame }) {
                            t.remove(at: i)
                        } else {
                            t.append(tag.name)
                        }
                        save(todo, title: todo.title, priority: todo.priority, dueDate: todo.dueDate, tags: t)
                    } label: {
                        if todo.hasTag(tag.name) {
                            Label(tag.name, systemImage: "checkmark")
                        } else {
                            Text(tag.name)
                        }
                    }
                }
            }
            Button(role: .destructive, action: { delete(todo) }) {
                Label("Delete", systemImage: "trash")
            }
        }
    }

    /// Horizontal chip strip: All · <each tag> · Untagged · manage.
    private var filterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                filterChip(label: "All", key: "", hex: settings.accentColor.hexString ?? "#4a9edd")
                ForEach(tags) { tag in
                    filterChip(label: tag.name, key: tag.name, hex: tag.hexColor)
                        .contextMenu {
                            Button {
                                settings.taskAutoTag = settings.taskAutoTag == tag.name ? "" : tag.name
                            } label: {
                                Label(settings.taskAutoTag == tag.name ? "Stop tag mode" : "Tag mode: \(tag.name)",
                                      systemImage: "tag")
                            }
                            if tag.builtin == 0 {
                                Button(role: .destructive) { deleteTag(tag.name) } label: {
                                    Label("Delete tag", systemImage: "trash")
                                }
                            }
                        }
                }
                filterChip(label: "Untagged", key: Self.untaggedKey, hex: "#8a8a8a")

                Button(action: { showManageTags = true }) {
                    Image(systemName: "plus")
                        .font(.system(size: 12, weight: .bold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(Capsule().fill(Color.secondary.opacity(0.15)))
                        .foregroundColor(.primary)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Manage tags")
            }
            .padding(.horizontal, 16)
        }
    }

    private func filterChip(label: String, key: String, hex: String) -> some View {
        let selected = key.isEmpty ? settings.taskTagFilters.isEmpty : settings.taskTagFilters.contains(key)
        let n = key.isEmpty ? 0 : count(for: key)
        return HStack(spacing: 4) {
            TagChip(name: label, hex: hex, selected: selected)
            if n > 0 && !selected {
                Text("\(n)")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.secondary)
            }
        }
        .contentShape(Capsule())
        .onTapGesture {
            withAnimation(.easeInOut(duration: 0.15)) {
                if key.isEmpty {
                    settings.taskTagFilters = []            // "All" clears every filter
                } else if selected {
                    settings.taskTagFilters.removeAll { $0 == key }   // re-tap turns that tag off
                } else {
                    settings.taskTagFilters.append(key)
                }
            }
        }
    }

    /// Toolbar menu: pick a tag that every new task from this phone gets.
    private var tagModeMenu: some View {
        Menu {
            Section("Tag mode — auto-tag new tasks") {
                Button {
                    settings.taskAutoTag = ""
                } label: {
                    if settings.taskAutoTag.isEmpty { Label("Off", systemImage: "checkmark") } else { Text("Off") }
                }
                ForEach(tags) { tag in
                    Button {
                        settings.taskAutoTag = tag.name
                    } label: {
                        if settings.taskAutoTag == tag.name {
                            Label(tag.name, systemImage: "checkmark")
                        } else {
                            Text(tag.name)
                        }
                    }
                }
            }
            Divider()
            Button { showManageTags = true } label: {
                Label("Manage tags…", systemImage: "slider.horizontal.3")
            }
        } label: {
            Image(systemName: settings.taskAutoTag.isEmpty ? "tag" : "tag.fill")
        }
    }

    // MARK: - Data

    private func load() {
        loading = true
        Task {
            do {
                async let t = api.todos(list: "all", includeCompleted: true)
                async let g = api.tags()
                todos = try await t
                tags  = (try? await g) ?? tags
                // Drop stale filter / tag-mode choices that point at a deleted tag.
                let names = Set(tags.map { $0.name.lowercased() })
                let pruned = settings.taskTagFilters.filter {
                    $0 == Self.untaggedKey || names.contains($0.lowercased())
                }
                if pruned != settings.taskTagFilters { settings.taskTagFilters = pruned }
                if !settings.taskAutoTag.isEmpty, !names.contains(settings.taskAutoTag.lowercased()) {
                    settings.taskAutoTag = ""
                }
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
        let newTags = effectiveAutoTags
        newTaskTitle = ""
        Task {
            _ = try? await api.createTodo(title: title, list: list, tags: newTags)
            load()
        }
    }

    private func addTag(_ name: String) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty,
              !tags.contains(where: { $0.name.caseInsensitiveCompare(trimmed) == .orderedSame })
        else { return }
        tags.append(TodoTag(name: trimmed))   // optimistic
        Task {
            try? await api.createTag(name: trimmed)
            tags = (try? await api.tags()) ?? tags
        }
    }

    private func deleteTag(_ name: String) {
        tags.removeAll { $0.name.caseInsensitiveCompare(name) == .orderedSame }
        for i in todos.indices {
            todos[i].tags.removeAll { $0.caseInsensitiveCompare(name) == .orderedSame }
        }
        settings.taskTagFilters.removeAll { $0.caseInsensitiveCompare(name) == .orderedSame }
        if settings.taskAutoTag.caseInsensitiveCompare(name) == .orderedSame { settings.taskAutoTag = "" }
        Task { try? await api.deleteTag(name: name) }
    }

    private func toggle(_ todo: Todo) {
        // Immediate optimistic UI update so the checkbox responds instantly,
        // even when offline (no waiting for the 8 s network timeout).
        if let i = todos.firstIndex(where: { $0.id == todo.id }) {
            todos[i].completed = todos[i].completed == 0 ? 1 : 0
        }
        Task { _ = try? await api.toggleTodo(id: todo.id) }
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
        // Reordering while a tag filter hides some rows would scramble the
        // hidden ones' positions, so only allow it on the unfiltered list.
        guard !isFiltering else { return }
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

    private func save(_ todo: Todo, title: String, priority: String, dueDate: String, tags newTags: [String]) {
        // Optimistic local update
        if let i = todos.firstIndex(where: { $0.id == todo.id }) {
            todos[i].title    = title
            todos[i].priority = priority
            todos[i].dueDate  = dueDate
            todos[i].tags     = newTags
        }
        Task { try? await api.updateTodo(id: todo.id, title: title, priority: priority, dueDate: dueDate, tags: newTags) }
    }

    private func clearCompleted() {
        todos.removeAll { $0.isDone }
        Task {
            try? await api.clearCompletedTodos()
            load()
        }
    }
}

// MARK: - Manage tags sheet

struct ManageTagsSheet: View {
    @EnvironmentObject var settings: AppSettings
    @Environment(\.dismiss) private var dismiss
    @Binding var tags: [TodoTag]
    var onAdd: (String) -> Void
    var onDelete: (String) -> Void

    @State private var newName = ""
    @FocusState private var nameFocused: Bool

    var body: some View {
        NavigationView {
            List {
                Section("New tag") {
                    HStack {
                        TextField("e.g. Errands, Gym, Reading…", text: $newName)
                            .focused($nameFocused)
                            .submitLabel(.done)
                            .onSubmit(commit)
                        Button(action: commit) {
                            Image(systemName: "plus.circle.fill")
                                .foregroundColor(settings.accentColor)
                        }
                        .disabled(newName.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                }
                Section("Tags") {
                    ForEach(tags) { tag in
                        HStack {
                            TagChip(name: tag.name, hex: tag.hexColor)
                            Spacer()
                            if tag.builtin != 0 {
                                Text("built-in")
                                    .font(.system(size: 11))
                                    .foregroundColor(.secondary)
                            }
                        }
                        .swipeActions(edge: .trailing) {
                            Button(role: .destructive) { onDelete(tag.name) } label: {
                                Label("Delete", systemImage: "trash")
                            }
                        }
                    }
                }
                Section {
                    Text("Deleting a tag removes it from every task. Long-press a tag in the filter bar to switch on tag mode for it.")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }
            }
            .navigationTitle("Tags")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .onAppear { nameFocused = true }
        }
    }

    private func commit() {
        let n = newName
        newName = ""
        onAdd(n)
    }
}

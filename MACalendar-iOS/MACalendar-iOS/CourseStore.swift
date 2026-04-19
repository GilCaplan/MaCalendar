import Foundation

/// Local JSON cache for courses and assignments.
/// Mirrors LocalStore's pattern: temp IDs are negative ints; offline writes
/// are queued in LocalStore.shared.enqueue() and replayed on reconnect.
@MainActor
class CourseStore: ObservableObject {
    static let shared = CourseStore()

    @Published private(set) var courses:     [Course]    = []
    @Published private(set) var assignments: [Assignment] = []

    private let dir = FileManager.default
        .urls(for: .documentDirectory, in: .userDomainMask)[0]
    private var nextTemp = -1

    private init() { load() }

    private func url(_ name: String) -> URL { dir.appendingPathComponent(name) }

    private func load() {
        let d = JSONDecoder()
        courses     = (try? d.decode([Course].self,     from: Data(contentsOf: url("mc_courses.json"))))     ?? []
        assignments = (try? d.decode([Assignment].self, from: Data(contentsOf: url("mc_assignments.json")))) ?? []
        // Start temp IDs below the lowest existing negative
        let negIds = courses.map { $0.id }.filter { $0 < 0 }
                   + assignments.map { $0.id }.filter { $0 < 0 }
        nextTemp = (negIds.min().map { $0 - 1 }) ?? -1
    }

    func persist() {
        let e = JSONEncoder()
        try? e.encode(courses).write(to:     url("mc_courses.json"))
        try? e.encode(assignments).write(to: url("mc_assignments.json"))
    }

    // MARK: - Cache (called after successful API fetch)

    func cacheCourses(_ fresh: [Course]) {
        let local = courses.filter { $0.id < 0 }
        courses = local + fresh
        persist()
    }

    func cacheAllAssignments(_ fresh: [Assignment]) {
        let local = assignments.filter { $0.id < 0 }
        assignments = local + fresh
        persist()
    }

    // MARK: - Reads

    func assignments(for courseId: Int) -> [Assignment] {
        assignments.filter { $0.courseId == courseId }
    }

    // MARK: - Optimistic local writes (offline path)

    func insertCourse(number: String, name: String, color: String, partners: [String]) -> Course {
        let c = Course(id: nextTemp, number: number, name: name, color: color, partners: partners)
        nextTemp -= 1
        courses.append(c)
        persist()
        return c
    }

    func patchCourse(_ id: Int, number: String, name: String, color: String, partners: [String]) {
        guard let i = courses.firstIndex(where: { $0.id == id }) else { return }
        courses[i].number   = number
        courses[i].name     = name
        courses[i].color    = color
        courses[i].partners = partners
        persist()
    }

    func removeCourse(_ id: Int) {
        courses.removeAll { $0.id == id }
        assignments.removeAll { $0.courseId == id }
        persist()
    }

    func insertAssignment(courseId: Int, title: String, dueDate: String = "") -> Assignment {
        let a = Assignment(id: nextTemp, courseId: courseId, title: title,
                           dueDate: dueDate, completed: false)
        nextTemp -= 1
        assignments.append(a)
        persist()
        return a
    }

    func patchAssignment(_ id: Int, title: String? = nil, dueDate: String? = nil,
                         completed: Bool? = nil, calendarEventId: Int? = nil) {
        guard let i = assignments.firstIndex(where: { $0.id == id }) else { return }
        if let v = title           { assignments[i].title           = v }
        if let v = dueDate         { assignments[i].dueDate         = v }
        if let v = completed       { assignments[i].completed       = v }
        if let v = calendarEventId { assignments[i].calendarEventId = v }
        persist()
    }

    func clearCalendarEventId(_ id: Int) {
        guard let i = assignments.firstIndex(where: { $0.id == id }) else { return }
        assignments[i].calendarEventId = nil
        persist()
    }

    func toggleAssignment(_ id: Int) {
        guard let i = assignments.firstIndex(where: { $0.id == id }) else { return }
        assignments[i].completed.toggle()
        persist()
    }

    func removeAssignment(_ id: Int) {
        assignments.removeAll { $0.id == id }
        persist()
    }
}

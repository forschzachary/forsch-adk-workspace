import Foundation

public actor ShelbyInMemoryReminderService: ShelbyReminderServiceProtocol {
    private let defaultListID = "default-list"
    private let defaultList = ShelbyReminderList(
        id: "default-list",
        title: "Reminders",
        isDefault: true
    )

    private(set) var accessStatus: ShelbyReminderAccessStatus
    private var lists: [String: ShelbyReminderList]
    private var reminders: [String: ShelbyReminderItem]

    public init(
        accessStatus: ShelbyReminderAccessStatus = .fullAccess,
        initialLists: [ShelbyReminderList] = []
    ) {
        self.accessStatus = accessStatus
        if initialLists.isEmpty {
            self.lists = [defaultList.id: defaultList]
        } else {
            self.lists = Dictionary(uniqueKeysWithValues: initialLists.map { ($0.id, $0) })
            if !initialLists.contains(where: { $0.isDefault }) {
                self.lists[defaultList.id] = defaultList
            }
        }
        self.reminders = [:]
    }

    public func setAccessStatus(_ status: ShelbyReminderAccessStatus) {
        accessStatus = status
    }

    public func refreshAuthorizationStatus() async -> ShelbyReminderAccessStatus {
        accessStatus
    }

    public func requestAuthorization() async throws -> ShelbyReminderAccessStatus {
        if accessStatus == .denied {
            throw ShelbyReminderServiceError.permissionDenied
        }
        accessStatus = .fullAccess
        return accessStatus
    }

    public func listReminderLists() async throws -> [ShelbyReminderList] {
        try ensureReadable()
        return lists.values.sorted { lhs, rhs in
            lhs.isDefault ? true : (!rhs.isDefault && lhs.title < rhs.title)
        }
    }

    public func fetchReminders(query: ShelbyReminderQuery) async throws -> [ShelbyReminderItem] {
        try ensureReadable()
        let filtered = reminders.values.filter { item in
            if let listId = query.listId, item.listId != listId {
                return false
            }

            if !query.includeCompleted && item.isCompleted {
                return false
            }

            if let term = query.searchTerm, !term.isEmpty {
                let haystack = "\(item.title) \(item.notes ?? "")".lowercased()
                if !haystack.contains(term.lowercased()) {
                    return false
                }
            }

            if let from = query.dueDateFrom, let due = item.dueDate, due < from {
                return false
            }

            if let to = query.dueDateTo, let due = item.dueDate, due > to {
                return false
            }

            return true
        }
        return filtered.sorted { lhs, rhs in
            if lhs.dueDate == nil && rhs.dueDate == nil {
                return lhs.title.localizedCaseInsensitiveCompare(rhs.title) == .orderedAscending
            }
            if lhs.dueDate == nil { return false }
            if rhs.dueDate == nil { return true }
            return lhs.dueDate! < rhs.dueDate!
        }
    }

    public func createReminder(_ draft: ShelbyReminderDraft) async throws -> ShelbyReminderItem {
        try ensureWritable()
        let title = draft.title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else {
            throw ShelbyReminderServiceError.invalidInput
        }
        let listId = draft.listId ?? defaultList.id
        guard lists[listId] != nil else {
            throw ShelbyReminderServiceError.listNotFound
        }

        let item = ShelbyReminderItem(
            id: UUID().uuidString,
            listId: listId,
            title: title,
            notes: draft.notes?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
            dueDate: draft.dueDate,
            alarmDate: draft.alarmDate,
            priority: clampedPriority(draft.priority),
            isCompleted: false
        )

        reminders[item.id] = item
        return item
    }

    public func updateReminder(id: String, update: ShelbyReminderUpdate) async throws -> ShelbyReminderItem {
        try ensureWritable()
        guard var item = reminders[id] else {
            throw ShelbyReminderServiceError.reminderNotFound
        }

        if let listId = update.listId {
            guard lists[listId] != nil else {
                throw ShelbyReminderServiceError.listNotFound
            }
            item = ShelbyReminderItem(
                id: item.id,
                listId: listId,
                title: item.title,
                notes: item.notes,
                dueDate: item.dueDate,
                alarmDate: item.alarmDate,
                priority: item.priority,
                isCompleted: item.isCompleted
            )
        }

        if let title = update.title?.trimmingCharacters(in: .whitespacesAndNewlines), !title.isEmpty {
            item = ShelbyReminderItem(
                id: item.id,
                listId: item.listId,
                title: title,
                notes: item.notes,
                dueDate: item.dueDate,
                alarmDate: item.alarmDate,
                priority: item.priority,
                isCompleted: item.isCompleted
            )
        }

        if let notes = update.notes {
            item = ShelbyReminderItem(
                id: item.id,
                listId: item.listId,
                title: item.title,
                notes: notes.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
                dueDate: item.dueDate,
                alarmDate: item.alarmDate,
                priority: item.priority,
                isCompleted: item.isCompleted
            )
        }

        if let dueDate = update.dueDate {
            item = ShelbyReminderItem(
                id: item.id,
                listId: item.listId,
                title: item.title,
                notes: item.notes,
                dueDate: dueDate,
                alarmDate: item.alarmDate,
                priority: item.priority,
                isCompleted: item.isCompleted
            )
        }

        if let alarmDate = update.alarmDate {
            item = ShelbyReminderItem(
                id: item.id,
                listId: item.listId,
                title: item.title,
                notes: item.notes,
                dueDate: item.dueDate,
                alarmDate: alarmDate,
                priority: item.priority,
                isCompleted: item.isCompleted
            )
        }

        if let priority = update.priority {
            item = ShelbyReminderItem(
                id: item.id,
                listId: item.listId,
                title: item.title,
                notes: item.notes,
                dueDate: item.dueDate,
                alarmDate: item.alarmDate,
                priority: clampedPriority(priority),
                isCompleted: item.isCompleted
            )
        }

        if let isCompleted = update.isCompleted {
            item = ShelbyReminderItem(
                id: item.id,
                listId: item.listId,
                title: item.title,
                notes: item.notes,
                dueDate: item.dueDate,
                alarmDate: item.alarmDate,
                priority: item.priority,
                isCompleted: isCompleted
            )
        }

        reminders[item.id] = item
        return item
    }

    public func completeReminder(id: String) async throws -> ShelbyReminderItem {
        let update = ShelbyReminderUpdate(isCompleted: true)
        return try await updateReminder(id: id, update: update)
    }

    public func deleteReminder(id: String) async throws {
        try ensureWritable()
        guard reminders.removeValue(forKey: id) != nil else {
            throw ShelbyReminderServiceError.reminderNotFound
        }
    }

    private func ensureReadable() throws {
        switch accessStatus {
        case .fullAccess, .partialAccess:
            return
        case .notDetermined, .unknown, .restricted, .denied:
            throw ShelbyReminderServiceError.notAuthorized
        }
    }

    private func ensureWritable() throws {
        switch accessStatus {
        case .fullAccess, .partialAccess:
            return
        case .notDetermined, .unknown, .restricted, .denied:
            throw ShelbyReminderServiceError.notAuthorized
        }
    }

    private func clampedPriority(_ priority: Int?) -> Int {
        let requested = priority ?? 0
        return max(0, min(9, requested))
    }
}

private extension String {
    var nilIfEmpty: String? {
        let normalized = trimmingCharacters(in: .whitespacesAndNewlines)
        return normalized.isEmpty ? nil : normalized
    }
}

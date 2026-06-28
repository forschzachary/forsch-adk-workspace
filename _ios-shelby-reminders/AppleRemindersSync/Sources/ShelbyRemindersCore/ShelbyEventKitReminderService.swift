#if canImport(EventKit)
@preconcurrency import EventKit
import Foundation

@available(iOS 13.0, macOS 10.15, *)
public final class ShelbyEventKitReminderService: NSObject, ShelbyReminderServiceProtocol {
    private let eventStore: EKEventStore

    public init(eventStore: EKEventStore = EKEventStore()) {
        self.eventStore = eventStore
    }

    public func refreshAuthorizationStatus() async -> ShelbyReminderAccessStatus {
        mapAuthorizationStatus(EKEventStore.authorizationStatus(for: .reminder))
    }

    public func requestAuthorization() async throws -> ShelbyReminderAccessStatus {
        if #available(iOS 17.0, macOS 14.0, *) {
            try await requestFullAccessIfNeeded()
        } else {
            try await requestLegacyAccessIfNeeded()
        }
        return await refreshAuthorizationStatus()
    }

    public func listReminderLists() async throws -> [ShelbyReminderList] {
        try await requireReadableAccess()
        let calendars = eventStore.calendars(for: .reminder)
        let defaultCalendar = eventStore.defaultCalendarForNewReminders()
        let defaultCalendarID = defaultCalendar?.calendarIdentifier
        return calendars.map { calendar in
            ShelbyReminderList(
                id: calendar.calendarIdentifier,
                title: calendar.title,
                isDefault: calendar.calendarIdentifier == defaultCalendarID
            )
        }.sorted { lhs, rhs in
            if lhs.isDefault { return true }
            if rhs.isDefault { return false }
            return lhs.title.localizedCaseInsensitiveCompare(rhs.title) == .orderedAscending
        }
    }

    public func fetchReminders(query: ShelbyReminderQuery) async throws -> [ShelbyReminderItem] {
        try await requireReadableAccess()

        let calendars: [EKCalendar]
        if let listId = query.listId {
            guard let calendar = ensureListExists(listId: listId) else {
                throw ShelbyReminderServiceError.listNotFound
            }
            calendars = [calendar]
        } else {
            calendars = eventStore.calendars(for: .reminder)
        }

        let predicate = eventStore.predicateForReminders(in: calendars)
        let all = await fetchRemindersFromStore(matching: predicate)

        return all.compactMap(mapReminderItem(from:))
            .filter { reminder in
                if !query.includeCompleted && reminder.isCompleted {
                    return false
                }

                if let term = query.searchTerm, !term.isEmpty {
                    let haystack = "\(reminder.title) \(reminder.notes ?? "")".lowercased()
                    if !haystack.contains(term.lowercased()) {
                        return false
                    }
                }

                if let from = query.dueDateFrom, let due = reminder.dueDate, due < from {
                    return false
                }

                if let to = query.dueDateTo, let due = reminder.dueDate, due > to {
                    return false
                }

                return true
            }
            .sorted { lhs, rhs in
                if lhs.dueDate == nil { return false }
                if rhs.dueDate == nil { return true }
                return lhs.dueDate! < rhs.dueDate!
            }
    }

    public func createReminder(_ draft: ShelbyReminderDraft) async throws -> ShelbyReminderItem {
        try await requireWritableAccess()

        let trimmedTitle = draft.title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedTitle.isEmpty else { throw ShelbyReminderServiceError.invalidInput }

        let reminder = EKReminder(eventStore: eventStore)
        reminder.title = trimmedTitle
        reminder.notes = draft.notes
        reminder.priority = mappedPriority(draft.priority)
        reminder.isCompleted = false

        if let listId = draft.listId {
            guard let calendar = ensureListExists(listId: listId) else {
                throw ShelbyReminderServiceError.listNotFound
            }
            reminder.calendar = calendar
        } else if let defaultCalendar = eventStore.defaultCalendarForNewReminders() {
            reminder.calendar = defaultCalendar
        } else if let fallback = eventStore.calendars(for: .reminder).first {
            reminder.calendar = fallback
        }

        reminder.dueDateComponents = mappedDateComponents(from: draft.dueDate)
        reminder.alarms = mappedAlarms(from: draft.alarmDate)

        try eventStore.save(reminder, commit: true)
        return mapReminderItem(from: reminder)
    }

    public func updateReminder(id: String, update: ShelbyReminderUpdate) async throws -> ShelbyReminderItem {
        try await requireWritableAccess()

        guard let reminder = eventStore.calendarItem(withIdentifier: id) as? EKReminder else {
            throw ShelbyReminderServiceError.reminderNotFound
        }

        let title = update.title?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let title, !title.isEmpty {
            reminder.title = title
        } else if let title = update.title, title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            throw ShelbyReminderServiceError.invalidInput
        }

        if let notes = update.notes {
            reminder.notes = notes
        }

        if let dueDate = update.dueDate {
            reminder.dueDateComponents = mappedDateComponents(from: dueDate)
        }

        if let alarmDate = update.alarmDate {
            reminder.alarms = mappedAlarms(from: alarmDate)
        }

        if let priority = update.priority {
            reminder.priority = mappedPriority(priority)
        }

        if let listId = update.listId {
            guard let calendar = ensureListExists(listId: listId) else {
                throw ShelbyReminderServiceError.listNotFound
            }
            reminder.calendar = calendar
        }

        if let isCompleted = update.isCompleted {
            reminder.isCompleted = isCompleted
            reminder.completionDate = isCompleted ? Date() : nil
        }

        try eventStore.save(reminder, commit: true)
        return mapReminderItem(from: reminder)
    }

    public func completeReminder(id: String) async throws -> ShelbyReminderItem {
        let update = ShelbyReminderUpdate(isCompleted: true)
        return try await updateReminder(id: id, update: update)
    }

    public func deleteReminder(id: String) async throws {
        try await requireWritableAccess()
        guard let reminder = eventStore.calendarItem(withIdentifier: id) as? EKReminder else {
            throw ShelbyReminderServiceError.reminderNotFound
        }
        try eventStore.remove(reminder, commit: true)
    }

    func mappedPriority(_ priority: Int?) -> Int {
        guard let priority else { return 0 }
        return max(0, min(9, priority))
    }

    func mappedDateComponents(from date: Date?) -> DateComponents? {
        guard let date else { return nil }
        return Calendar.current.dateComponents(
            in: .current,
            from: date
        )
    }

    func mappedAlarms(from date: Date?) -> [EKAlarm]? {
        guard let date else { return nil }
        return [EKAlarm(absoluteDate: date)]
    }

    func mapReminderItem(from reminder: EKReminder) -> ShelbyReminderItem {
        let dueDate = reminder.dueDateComponents?.date
        let alarmDate = reminder.alarms?.first?.absoluteDate
        return ShelbyReminderItem(
            id: reminder.calendarItemIdentifier,
            listId: reminder.calendar?.calendarIdentifier,
            title: reminder.title ?? "",
            notes: reminder.notes,
            dueDate: dueDate,
            alarmDate: alarmDate,
            priority: mappedPriority(reminder.priority),
            isCompleted: reminder.isCompleted
        )
    }

    func fetchRemindersFromStore(matching predicate: NSPredicate) async -> [EKReminder] {
        await withCheckedContinuation { continuation in
            eventStore.fetchReminders(matching: predicate) { reminders in
                continuation.resume(returning: reminders ?? [])
            }
        }
    }

    private func ensureListExists(listId: String) -> EKCalendar? {
        let calendars = eventStore.calendars(for: .reminder)
        return calendars.first(where: { $0.calendarIdentifier == listId })
    }

    private func requireReadableAccess() async throws {
        let status = await refreshAuthorizationStatus()
        switch status {
        case .notDetermined, .unknown, .restricted, .denied:
            throw ShelbyReminderServiceError.notAuthorized
        case .fullAccess, .partialAccess:
            return
        }
    }

    private func requireWritableAccess() async throws {
        let status = await refreshAuthorizationStatus()
        if status != .fullAccess && status != .partialAccess {
            throw ShelbyReminderServiceError.notAuthorized
        }
    }

    private func requestFullAccessIfNeeded() async throws {
        if #available(iOS 17.0, macOS 14.0, *) {
            return try await withCheckedThrowingContinuation { continuation in
                eventStore.requestFullAccessToReminders { granted, error in
                    if let error {
                        continuation.resume(throwing: error)
                    } else if granted {
                        continuation.resume(returning: ())
                    } else {
                        continuation.resume(throwing: ShelbyReminderServiceError.permissionDenied)
                    }
                }
            }
        } else {
            throw ShelbyReminderServiceError.notAuthorized
        }
    }

    private func requestLegacyAccessIfNeeded() async throws {
        return try await withCheckedThrowingContinuation { continuation in
            eventStore.requestAccess(to: .reminder) { granted, error in
                if let error {
                    continuation.resume(throwing: error)
                } else if granted {
                    continuation.resume(returning: ())
                } else {
                    continuation.resume(throwing: ShelbyReminderServiceError.permissionDenied)
                }
            }
        }
    }

    private func mapAuthorizationStatus(_ status: EKAuthorizationStatus) -> ShelbyReminderAccessStatus {
        switch status {
        case .notDetermined:
            return .notDetermined
        case .restricted:
            return .restricted
        case .denied:
            return .denied
        case .authorized:
            return .fullAccess
        case .fullAccess:
            return .fullAccess
        case .writeOnly:
            return .partialAccess
        @unknown default:
            return .unknown
        }
    }
}
#else
import Foundation

public final class ShelbyEventKitReminderService: NSObject, ShelbyReminderServiceProtocol {
    public init() {}

    public func refreshAuthorizationStatus() async -> ShelbyReminderAccessStatus {
        .unsupportedPlatform
    }

    public func requestAuthorization() async throws -> ShelbyReminderAccessStatus {
        throw ShelbyReminderServiceError.unsupportedPlatform
    }

    public func listReminderLists() async throws -> [ShelbyReminderList] {
        throw ShelbyReminderServiceError.unsupportedPlatform
    }

    public func fetchReminders(query: ShelbyReminderQuery) async throws -> [ShelbyReminderItem] {
        throw ShelbyReminderServiceError.unsupportedPlatform
    }

    public func createReminder(_ draft: ShelbyReminderDraft) async throws -> ShelbyReminderItem {
        throw ShelbyReminderServiceError.unsupportedPlatform
    }

    public func updateReminder(id: String, update: ShelbyReminderUpdate) async throws -> ShelbyReminderItem {
        throw ShelbyReminderServiceError.unsupportedPlatform
    }

    public func completeReminder(id: String) async throws -> ShelbyReminderItem {
        throw ShelbyReminderServiceError.unsupportedPlatform
    }

    public func deleteReminder(id: String) async throws {
        throw ShelbyReminderServiceError.unsupportedPlatform
    }
}
#endif

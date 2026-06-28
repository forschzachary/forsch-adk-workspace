import Foundation

public enum ShelbyReminderAccessStatus: String, Codable, Equatable, Sendable {
    case unknown
    case notDetermined
    case denied
    case restricted
    case fullAccess
    case partialAccess
}

public struct ShelbyReminderList: Identifiable, Codable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let isDefault: Bool

    public init(
        id: String,
        title: String,
        isDefault: Bool
    ) {
        self.id = id
        self.title = title
        self.isDefault = isDefault
    }
}

public struct ShelbyReminderItem: Identifiable, Codable, Equatable, Sendable {
    public let id: String
    public let listId: String?
    public let title: String
    public let notes: String?
    public let dueDate: Date?
    public let alarmDate: Date?
    public let priority: Int
    public let isCompleted: Bool

    public init(
        id: String,
        listId: String?,
        title: String,
        notes: String?,
        dueDate: Date?,
        alarmDate: Date?,
        priority: Int,
        isCompleted: Bool
    ) {
        self.id = id
        self.listId = listId
        self.title = title
        self.notes = notes
        self.dueDate = dueDate
        self.alarmDate = alarmDate
        self.priority = priority
        self.isCompleted = isCompleted
    }
}

public struct ShelbyReminderDraft: Codable, Equatable, Sendable {
    public let title: String
    public let notes: String?
    public let listId: String?
    public let dueDate: Date?
    public let alarmDate: Date?
    public let priority: Int?

    public init(
        title: String,
        notes: String? = nil,
        listId: String? = nil,
        dueDate: Date? = nil,
        alarmDate: Date? = nil,
        priority: Int? = nil
    ) {
        self.title = title
        self.notes = notes
        self.listId = listId
        self.dueDate = dueDate
        self.alarmDate = alarmDate
        self.priority = priority
    }
}

public struct ShelbyReminderUpdate: Codable, Equatable, Sendable {
    public let title: String?
    public let notes: String?
    public let listId: String?
    public let dueDate: Date?
    public let alarmDate: Date?
    public let priority: Int?
    public let isCompleted: Bool?

    public init(
        title: String? = nil,
        notes: String? = nil,
        listId: String? = nil,
        dueDate: Date? = nil,
        alarmDate: Date? = nil,
        priority: Int? = nil,
        isCompleted: Bool? = nil
    ) {
        self.title = title
        self.notes = notes
        self.listId = listId
        self.dueDate = dueDate
        self.alarmDate = alarmDate
        self.priority = priority
        self.isCompleted = isCompleted
    }
}

public struct ShelbyReminderQuery: Codable, Equatable, Sendable {
    public let listId: String?
    public let includeCompleted: Bool
    public let searchTerm: String?
    public let dueDateFrom: Date?
    public let dueDateTo: Date?

    public init(
        listId: String? = nil,
        includeCompleted: Bool = false,
        searchTerm: String? = nil,
        dueDateFrom: Date? = nil,
        dueDateTo: Date? = nil
    ) {
        self.listId = listId
        self.includeCompleted = includeCompleted
        self.searchTerm = searchTerm
        self.dueDateFrom = dueDateFrom
        self.dueDateTo = dueDateTo
    }

    public static func openList(includeCompleted: Bool = false) -> ShelbyReminderQuery {
        ShelbyReminderQuery(includeCompleted: includeCompleted)
    }
}

public enum ShelbyReminderServiceError: Error, Equatable, LocalizedError, Sendable {
    case permissionDenied
    case notAuthorized
    case listNotFound
    case reminderNotFound
    case invalidInput
    case unsupportedPlatform
    case other(String)

    public var errorDescription: String? {
        switch self {
        case .permissionDenied, .notAuthorized:
            return "Reminders permission is denied."
        case .listNotFound:
            return "The requested reminder list was not found."
        case .reminderNotFound:
            return "The requested reminder was not found."
        case .invalidInput:
            return "The reminder payload is invalid."
        case .unsupportedPlatform:
            return "Reminders service is not available on this platform."
        case .other(let message):
            return message
        }
    }
}

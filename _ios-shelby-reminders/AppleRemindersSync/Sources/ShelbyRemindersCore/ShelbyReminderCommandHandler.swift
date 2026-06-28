public struct ShelbyReminderCommand: Sendable, Equatable {
    public enum Kind: String, Sendable {
        case listLists = "list_lists"
        case listOpen = "list_open"
        case add
        case update
        case complete
        case delete
    }

    public let kind: Kind
    public let query: ShelbyReminderQuery?
    public let draft: ShelbyReminderDraft?
    public let update: ShelbyReminderUpdate?
    public let id: String?

    public init(
        kind: Kind,
        query: ShelbyReminderQuery? = nil,
        draft: ShelbyReminderDraft? = nil,
        update: ShelbyReminderUpdate? = nil,
        id: String? = nil
    ) {
        self.kind = kind
        self.query = query
        self.draft = draft
        self.update = update
        self.id = id
    }
}

public enum ShelbyReminderCommandOutput: Equatable {
    case listLists([ShelbyReminderList])
    case listOpen([ShelbyReminderItem])
    case add(ShelbyReminderItem)
    case update(ShelbyReminderItem)
    case complete(ShelbyReminderItem)
    case delete(Bool)
}

public enum ShelbyReminderCommandResponse: Equatable {
    case success(command: ShelbyReminderCommand.Kind, output: ShelbyReminderCommandOutput)
    case failure(command: ShelbyReminderCommand.Kind, error: ShelbyReminderServiceError)
}

public final class ShelbyReminderCommandHandler {
    private let service: ShelbyReminderServiceProtocol

    public init(service: ShelbyReminderServiceProtocol) {
        self.service = service
    }

    public func handle(_ command: ShelbyReminderCommand) async -> ShelbyReminderCommandResponse {
        do {
            switch command.kind {
            case .listLists:
                let lists = try await service.listReminderLists()
                return .success(command: .listLists, output: .listLists(lists))

            case .listOpen:
                let query = command.query ?? .init()
                let reminders = try await service.fetchReminders(query: query)
                return .success(command: .listOpen, output: .listOpen(reminders))

            case .add:
                guard let draft = command.draft else {
                    return .failure(
                        command: .add,
                        error: .invalidInput
                    )
                }
                let item = try await service.createReminder(draft)
                return .success(command: .add, output: .add(item))

            case .update:
                guard let reminderId = command.id, let update = command.update else {
                    return .failure(command: .update, error: .invalidInput)
                }
                let item = try await service.updateReminder(id: reminderId, update: update)
                return .success(command: .update, output: .update(item))

            case .complete:
                guard let reminderId = command.id else {
                    return .failure(command: .complete, error: .invalidInput)
                }
                let item = try await service.completeReminder(id: reminderId)
                return .success(command: .complete, output: .complete(item))

            case .delete:
                guard let reminderId = command.id else {
                    return .failure(command: .delete, error: .invalidInput)
                }
                try await service.deleteReminder(id: reminderId)
                return .success(command: .delete, output: .delete(true))
            }
        } catch let error as ShelbyReminderServiceError {
            return .failure(command: command.kind, error: error)
        } catch {
            return .failure(command: command.kind, error: .other(error.localizedDescription))
        }
    }
}

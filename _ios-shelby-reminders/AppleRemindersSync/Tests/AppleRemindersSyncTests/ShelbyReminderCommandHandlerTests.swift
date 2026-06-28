import XCTest
@testable import AppleRemindersSync

final class ShelbyReminderCommandHandlerTests: XCTestCase {
    func testCommandsSucceedForInMemoryService() async throws {
        let service = ShelbyInMemoryReminderService()
        let handler = ShelbyReminderCommandHandler(service: service)

        let listResult = await handler.handle(.init(kind: .listLists))
        guard case .success(command: .listLists, output: .listLists(let lists)) = listResult else {
            return XCTFail("Expected listLists success")
        }
        XCTAssertEqual(lists.count, 1)

        let addResult = await handler.handle(
            .init(
                kind: .add,
                draft: ShelbyReminderDraft(title: "Pick up groceries", notes: "Milk, eggs")
            )
        )
        guard case .success(command: .add, output: .add(let item)) = addResult else {
            return XCTFail("Expected add success")
        }
        XCTAssertEqual(item.title, "Pick up groceries")
        XCTAssertEqual(item.notes, "Milk, eggs")

        let openResult = await handler.handle(
            .init(kind: .listOpen, query: ShelbyReminderQuery(includeCompleted: true))
        )
        guard case .success(command: .listOpen, output: .listOpen(let reminders)) = openResult else {
            return XCTFail("Expected listOpen success")
        }
        XCTAssertEqual(reminders.map(\.id), [item.id])

        let completeResult = await handler.handle(.init(kind: .complete, id: item.id))
        guard case .success(command: .complete, output: .complete(let completed)) = completeResult else {
            return XCTFail("Expected complete success")
        }
        XCTAssertTrue(completed.isCompleted)

        let updateResult = await handler.handle(
            .init(
                kind: .update,
                update: ShelbyReminderUpdate(notes: "Milk and eggs"),
                id: item.id
            )
        )
        guard case .success(command: .update, output: .update(let updated)) = updateResult else {
            return XCTFail("Expected update success")
        }
        XCTAssertEqual(updated.notes, "Milk and eggs")

        let deleteResult = await handler.handle(.init(kind: .delete, id: item.id))
        guard case .success(command: .delete, output: .delete(true)) = deleteResult else {
            return XCTFail("Expected delete success")
        }

        let finalResult = await handler.handle(.init(kind: .listOpen, query: ShelbyReminderQuery(includeCompleted: true)))
        if case .success(command: .listOpen, output: .listOpen(let reminders)) = finalResult {
            XCTAssertEqual(reminders.isEmpty, true)
        } else {
            XCTFail("Expected final list open result")
        }
    }

    func testInvalidCommandPayloadReturnsStructuredError() async {
        let service = ShelbyInMemoryReminderService()
        let handler = ShelbyReminderCommandHandler(service: service)

        let result = await handler.handle(.init(kind: .add))
        guard case .failure(command: .add, error: let error) = result else {
            return XCTFail("Expected add error")
        }
        XCTAssertEqual(error, .invalidInput)
    }

    func testPermissionDeniedIsReturnedAsStructuredError() async {
        let service = PermissionDeniedService()
        let handler = ShelbyReminderCommandHandler(service: service)

        let result = await handler.handle(
            .init(
                kind: .add,
                draft: ShelbyReminderDraft(title: "Should fail")
            )
        )

        guard case .failure(command: .add, error: .permissionDenied) = result else {
            return XCTFail("Expected permission denied error")
        }
    }
}

private final class PermissionDeniedService: ShelbyReminderServiceProtocol {
    func refreshAuthorizationStatus() async -> ShelbyReminderAccessStatus {
        .denied
    }

    func requestAuthorization() async throws -> ShelbyReminderAccessStatus {
        throw ShelbyReminderServiceError.permissionDenied
    }

    func listReminderLists() async throws -> [ShelbyReminderList] {
        throw ShelbyReminderServiceError.permissionDenied
    }

    func fetchReminders(query: ShelbyReminderQuery) async throws -> [ShelbyReminderItem] {
        throw ShelbyReminderServiceError.permissionDenied
    }

    func createReminder(_ draft: ShelbyReminderDraft) async throws -> ShelbyReminderItem {
        throw ShelbyReminderServiceError.permissionDenied
    }

    func updateReminder(id: String, update: ShelbyReminderUpdate) async throws -> ShelbyReminderItem {
        throw ShelbyReminderServiceError.permissionDenied
    }

    func completeReminder(id: String) async throws -> ShelbyReminderItem {
        throw ShelbyReminderServiceError.permissionDenied
    }

    func deleteReminder(id: String) async throws {
        throw ShelbyReminderServiceError.permissionDenied
    }
}

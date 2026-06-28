import XCTest
@testable import AppleRemindersSync

final class ShelbyInMemoryReminderServiceTests: XCTestCase {
    func testCreateFetchUpdateDeleteWorkflow() async throws {
        let list = ShelbyReminderList(id: "work", title: "Work", isDefault: false)
        let service = ShelbyInMemoryReminderService(initialLists: [list])

        let monday = Date(timeIntervalSince1970: 1_715_000_000)
        let mondayReminder = ShelbyReminderDraft(
            title: "Prepare demo",
            notes: "Focus on reminders",
            listId: list.id,
            dueDate: monday,
            priority: 2
        )
        let openReminder = ShelbyReminderDraft(
            title: "Buy paper",
            dueDate: monday.addingTimeInterval(86_400),
            priority: 12
        )

        let createdWork = try await service.createReminder(mondayReminder)
        let createdOpen = try await service.createReminder(openReminder)

        let fetchedOpen = try await service.fetchReminders(query: .openList())
        XCTAssertEqual(Set(fetchedOpen.map(\.id)), Set([createdOpen.id, createdWork.id]))

        let search = try await service.fetchReminders(query: ShelbyReminderQuery(searchTerm: "demo"))
        XCTAssertEqual(search.map(\.id), [createdWork.id])

        let completed = try await service.completeReminder(id: createdOpen.id)
        XCTAssertTrue(completed.isCompleted)

        let afterCompletion = try await service.fetchReminders(query: .openList(includeCompleted: false))
        XCTAssertEqual(afterCompletion.map(\.id), [createdWork.id])

        let includeCompleted = try await service.fetchReminders(query: .openList(includeCompleted: true))
        XCTAssertEqual(Set(includeCompleted.map(\.id)), Set([createdWork.id, createdOpen.id]))

        let updated = try await service.updateReminder(
            id: createdWork.id,
            update: ShelbyReminderUpdate(title: "Prepare launch deck", priority: 9)
        )
        XCTAssertEqual(updated.title, "Prepare launch deck")
        XCTAssertEqual(updated.priority, 9)

        let updatedListQuery = try await service.fetchReminders(query: ShelbyReminderQuery(listId: list.id))
        XCTAssertEqual(updatedListQuery.map(\.id), [createdWork.id])

        try await service.deleteReminder(id: createdWork.id)
        let remaining = try await service.fetchReminders(query: .openList(includeCompleted: true))
        XCTAssertEqual(remaining.map(\.id), [createdOpen.id])
    }

    func testInvalidDraftTitleIsRejected() async {
        let service = ShelbyInMemoryReminderService()
        do {
            _ = try await service.createReminder(ShelbyReminderDraft(title: "  "))
            XCTFail("Expected error")
        } catch ShelbyReminderServiceError.invalidInput {
            // expected
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }

    func testAccessDeniedPreventsReadsAndWrites() async {
        let service = ShelbyInMemoryReminderService(accessStatus: .denied)
        do {
            _ = try await service.listReminderLists()
            XCTFail("Expected error")
        } catch ShelbyReminderServiceError.notAuthorized {
            // expected
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }
}

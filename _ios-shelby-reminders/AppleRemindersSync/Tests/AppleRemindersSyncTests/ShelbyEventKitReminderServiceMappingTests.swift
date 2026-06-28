#if canImport(EventKit)
import EventKit
import XCTest
@testable import AppleRemindersSync

final class ShelbyEventKitReminderServiceMappingTests: XCTestCase {
    func testMappingHelperTransformsEventKitReminderToDomain() {
        let service = ShelbyEventKitReminderService()
        let store = EKEventStore()
        let reminder = EKReminder(eventStore: store)
        let dueDate = Date(timeIntervalSince1970: 1_715_000_000)
        let alarmDate = dueDate.addingTimeInterval(3600)

        reminder.title = "Call mom"
        reminder.notes = "At home"
        reminder.priority = 12
        reminder.isCompleted = true
        reminder.completionDate = Date()
        reminder.dueDateComponents = service.mappedDateComponents(from: dueDate)
        reminder.alarms = service.mappedAlarms(from: alarmDate)

        let item = service.mapReminderItem(from: reminder)
        XCTAssertEqual(item.title, "Call mom")
        XCTAssertEqual(item.notes, "At home")
        XCTAssertEqual(item.priority, 9)
        XCTAssertEqual(item.isCompleted, true)
        XCTAssertNotNil(item.dueDate)
        XCTAssertNotNil(item.alarmDate)
        if let mappedDue = item.dueDate {
            XCTAssertEqual(mappedDue.timeIntervalSince1970, dueDate.timeIntervalSince1970, accuracy: 1)
        }
    }
}
#endif

import Foundation

public protocol ShelbyReminderServiceProtocol: AnyObject {
    func refreshAuthorizationStatus() async -> ShelbyReminderAccessStatus
    func requestAuthorization() async throws -> ShelbyReminderAccessStatus
    func listReminderLists() async throws -> [ShelbyReminderList]
    func fetchReminders(query: ShelbyReminderQuery) async throws -> [ShelbyReminderItem]
    func createReminder(_ draft: ShelbyReminderDraft) async throws -> ShelbyReminderItem
    func updateReminder(id: String, update: ShelbyReminderUpdate) async throws -> ShelbyReminderItem
    func completeReminder(id: String) async throws -> ShelbyReminderItem
    func deleteReminder(id: String) async throws
}

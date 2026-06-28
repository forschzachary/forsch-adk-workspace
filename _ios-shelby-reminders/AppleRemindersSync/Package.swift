// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "AppleRemindersSync",
    platforms: [
        .iOS(.v17),
    ],
    products: [
        .library(
            name: "AppleRemindersSync",
            targets: ["ShelbyRemindersCore"]
        ),
    ],
    targets: [
        .target(
            name: "AppleRemindersSync"
        ),
        .testTarget(
            name: "AppleRemindersSyncTests",
            dependencies: ["ShelbyRemindersCore"]
        ),
    ]
)

import CoreLocation
import Foundation

/// Tells the host where this device is, so sundown is computed for here.
///
/// Candle lighting moves by more than three hours across a year in one place,
/// and by hours again between places. A repeating event that skips Shabbat is
/// wrong the moment you travel — the boundary it avoids was computed somewhere
/// else, and nothing about the wrong answer looks wrong.
///
/// Deliberately modest about it: one reading when asked, never continuous
/// tracking, and the coordinates go to your own host and nowhere else. A
/// position is only sent when it has actually moved enough to change an answer.
@MainActor
final class DeviceLocation: NSObject, ObservableObject {
    static let shared = DeviceLocation()

    /// Below this, sundown does not move by even a minute, so reporting it
    /// would be noise. Roughly the width of a large city.
    private static let significantMetres: CLLocationDistance = 25_000

    @Published private(set) var lastSent: CLLocation?
    @Published private(set) var status: String = ""

    private let manager = CLLocationManager()
    private var api: APIClient?
    private var pending = false

    private override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyKilometer   // a city is plenty
    }

    /// Ask once. Safe to call on every launch; it does nothing without permission.
    func refresh(using api: APIClient) {
        self.api = api
        switch manager.authorizationStatus {
        case .notDetermined:
            manager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse, .authorizedAlways:
            pending = true
            manager.requestLocation()
        default:
            status = "Location is off, so sundown uses the place set on your host."
        }
    }

    private func send(_ location: CLLocation) {
        // Skip a position that cannot change any answer — most launches.
        if let last = lastSent, last.distance(from: location) < Self.significantMetres {
            return
        }
        lastSent = location
        let tz = TimeZone.current.identifier
        Task { [weak self] in
            do {
                try await self?.api?.setObservanceLocation(
                    latitude: location.coordinate.latitude,
                    longitude: location.coordinate.longitude,
                    timezone: tz)
                await MainActor.run { self?.status = "Sundown is computed for where you are." }
            } catch {
                // Never surfaced as a failure: the host has a configured place
                // to fall back on, and this is an improvement, not a dependency.
                await MainActor.run { self?.status = "" }
            }
        }
    }
}

extension DeviceLocation: CLLocationManagerDelegate {
    nonisolated func locationManager(_ m: CLLocationManager, didUpdateLocations locs: [CLLocation]) {
        guard let best = locs.last else { return }
        Task { @MainActor in
            guard self.pending else { return }
            self.pending = false
            self.send(best)
        }
    }

    nonisolated func locationManager(_ m: CLLocationManager, didFailWithError error: Error) {
        Task { @MainActor in
            self.pending = false
            self.status = ""
        }
    }

    nonisolated func locationManagerDidChangeAuthorization(_ m: CLLocationManager) {
        Task { @MainActor in
            if m.authorizationStatus == .authorizedWhenInUse || m.authorizationStatus == .authorizedAlways {
                self.pending = true
                m.requestLocation()
            }
        }
    }
}

# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-03-27

### Added
- **System Tray Integration**: Application now minimizes to the system tray (notification area) when the window is closed or minimized.
- **Close-to-Tray**: The 'X' button now hides the window instead of exiting, ensuring background tasks are not interrupted.
- **Improved Taskbar Icon**: Fixed Windows taskbar icon grouping issue using `AppUserModelID`.
- **Resolution Scaling**: Added a resolutions dropdown to downscale videos while preserving aspect ratios.
- **Custom Filename**: Added an entry field to specify a custom output filename.
- **Audio-Only Mode**: Improved handling of audio files with automatic switching to audio-specific codecs (MP3, FLAC, etc.) and containers.
- **Dynamic Exporting**: The export format list now dynamically updates based on the selected codec's compatibility.
- **Hardware Acceleration Probing**: Intelligent detection of available hardware encoders (NVENC, AMF, QSV, VAAPI).

### Changed
- **Main UI Layout**: Improved spacing and responsiveness using Qt layouts.
- **Progress Tracking**: Switched to time-based progress calculation for more accurate FFmpeg progress bars.
- **Requirements**: Updated dependencies to the latest stable versions.

### Fixed
- **Codec Compatibility**: Resolved issues where certain combinations of hardware encoders and containers would fail.
- **FFmpeg 2-Pass**: Fixed a bug where small output files were being generated during 2-pass CPU encoding.

## [0.9.0] - 2026-03-23

### Added
- Initial UI with Drag & Drop support.
- FFmpeg automatic downloader.
- Multi-file queue processing.
- Desktop notifications.
- Settings persistence.

---

*For more details, visit the [GitHub Repository](https://github.com/thedevil4k/THE-DRAGGY-ENCODER).*

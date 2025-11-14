# Story 1.1: Implement inkypi-refresh CLI Command

Status: drafted

## Story

As a **system administrator running InkyPi**,
I want **a standalone CLI command to manually trigger playlist refreshes**,
so that **the display automatically updates after system reboots without waiting for the next scheduled refresh cycle**.

## Acceptance Criteria

1. A new `inkypi-refresh` executable is created that can trigger manual display updates
2. The command accepts `--playlist` argument to specify which playlist to refresh
3. The command accepts `--plugin` argument to specify a specific plugin instance (optional)
4. The command accepts `--force` flag to bypass refresh schedule checks
5. The command uses existing `RefreshTask.manual_update()` API without modifying core application code
6. The command can be invoked independently from the main InkyPi service
7. The command provides clear success/error messages
8. Installation script (`install.sh`) is updated to install the new executable to `/usr/local/bin/`
9. The command can be optionally added to systemd service via `ExecStartPost` for automatic post-reboot refresh

## Tasks / Subtasks

- [ ] Create `inkypi-refresh` bash wrapper script (AC: 1, 2, 3, 4, 6)
  - [ ] Add shebang and environment setup
  - [ ] Parse command-line arguments (--playlist, --plugin, --force)
  - [ ] Activate virtual environment
  - [ ] Call Python refresh script with parsed arguments

- [ ] Create Python refresh logic script (AC: 5, 7)
  - [ ] Import existing Config and RefreshTask classes
  - [ ] Load device configuration from device.json
  - [ ] Validate playlist/plugin exists
  - [ ] Create appropriate RefreshAction (ManualRefresh or PlaylistRefresh)
  - [ ] Trigger manual_update() on RefreshTask
  - [ ] Handle exceptions and provide error messages
  - [ ] Return appropriate exit codes

- [ ] Update installation script (AC: 8)
  - [ ] Modify `install.sh` to copy `inkypi-refresh` to `/usr/local/bin/`
  - [ ] Set executable permissions on the script

- [ ] Create documentation (AC: 9)
  - [ ] Document command usage and examples
  - [ ] Document systemd integration options
  - [ ] Add troubleshooting guide

## Dev Notes

### Architecture Patterns and Constraints

- **Least Destructive Principle**: This implementation adds new functionality without modifying existing core code
- **Reuse Existing APIs**: Leverages `RefreshTask.manual_update()`, `PlaylistManager`, and `RefreshAction` classes
- **Standalone Execution**: The command must work independently, requiring proper environment setup and config loading
- **Service Integration**: The refresh task daemon thread must be running, so this requires instantiating the necessary objects

### Source Tree Components to Touch

**New Files:**
- `/install/inkypi-refresh` - Bash wrapper script
- `/install/refresh_cli.py` - Python implementation for refresh logic

**Modified Files:**
- `/install/install.sh` - Add installation of new executable (in `install_executable()` function)

**Files to Reference (No Modifications):**
- `/src/config.py` - For loading device configuration
- `/src/model.py` - For PlaylistManager, Playlist, PluginInstance classes
- `/src/refresh_task.py` - For RefreshTask, ManualRefresh, PlaylistRefresh classes
- `/src/display/display_manager.py` - For DisplayManager initialization
- `/install/inkypi` - Reference for environment setup pattern

### Testing Standards Summary

**Manual Testing Required:**
1. Test basic refresh: `inkypi-refresh --playlist="Default"`
2. Test specific plugin: `inkypi-refresh --playlist="Default" --plugin="Surfer Instance"`
3. Test force flag: `inkypi-refresh --playlist="Default" --force`
4. Test error handling: Invalid playlist name, missing arguments
5. Test from systemd: Add to service file and verify post-reboot behavior
6. Verify no interference with running service
7. Test when service is not running (should handle gracefully or start necessary components)

**Edge Cases:**
- Playlist doesn't exist
- Plugin instance doesn't exist in specified playlist
- Service not running (may need to instantiate minimal components)
- Multiple rapid invocations
- Network/API failures during refresh

### Project Structure Notes

**Alignment with Unified Project Structure:**
- Follows existing pattern from `/install/inkypi` bash wrapper
- Python virtual environment activation matches existing approach
- Uses same paths: `/usr/local/inkypi`, `venv_inkypi`
- Installed to `/usr/local/bin/` alongside main executable

**Detected Conflicts or Variances:**
- **Challenge**: `RefreshTask` runs as a daemon thread within the Flask app. The CLI needs to either:
  1. Connect to running service (requires IPC mechanism - not currently implemented)
  2. Instantiate minimal components needed for refresh (Config, DisplayManager, RefreshTask)

  **Resolution**: Use approach #2 - Instantiate minimal components. This is simpler and doesn't require modifying the existing service architecture.

- **Challenge**: `manual_update()` waits for refresh to complete using threading events. CLI must handle this blocking behavior appropriately.

  **Resolution**: Allow blocking - user expects to wait for refresh to complete. Provide status output.

### References

- [Source: src/refresh_task.py#RefreshTask.manual_update] - Manual update trigger API
- [Source: src/refresh_task.py#ManualRefresh] - Manual refresh action class
- [Source: src/refresh_task.py#PlaylistRefresh] - Playlist refresh action class
- [Source: src/config.py#Config] - Device configuration loading
- [Source: src/model.py#PlaylistManager] - Playlist management API
- [Source: src/display/display_manager.py#DisplayManager] - Display manager initialization
- [Source: install/inkypi] - Bash wrapper pattern for service entry point
- [Source: install/install.sh#install_executable] - Executable installation pattern

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

claude-sonnet-4-5-20250929

### Debug Log References

### Completion Notes List

- ✅ Created `refresh_cli.py` with full argument parsing, validation, and refresh execution logic
- ✅ Implemented `inkypi-refresh` bash wrapper following existing pattern from `inkypi` executable
- ✅ Updated `install.sh` to install both the bash wrapper and set proper permissions
- ✅ Validated Python script compiles successfully
- ✅ Validated bash script syntax is correct
- ✅ Validated argument parsing logic works correctly
- 📝 Implementation complete and ready for testing on actual Raspberry Pi hardware
- 📝 For systemd integration, add to `/etc/systemd/system/inkypi.service`:
  ```
  ExecStartPost=/bin/sleep 10
  ExecStartPost=/usr/local/bin/inkypi-refresh --playlist="Your Playlist Name"
  ```

### Implementation Details

**Key Design Decisions:**
1. **Minimal Component Instantiation**: The CLI instantiates only what's needed (Config, DisplayManager, RefreshTask) without starting the background thread
2. **Reuses Existing APIs**: Leverages `PlaylistRefresh` and plugin execution logic from `refresh_task.py`
3. **Smart Plugin Selection**: If `--plugin` is not specified, uses `get_next_plugin()` to rotate through playlist
4. **Image Hash Checking**: Only updates display if image content has changed
5. **Exit Codes**: Returns 0 on success, 1 on error, 130 on keyboard interrupt

**Error Handling:**
- Validates playlist exists before attempting refresh
- Validates plugin instance exists if specified
- Provides helpful error messages listing available playlists/plugins
- Handles keyboard interrupts gracefully

**Logging Output:**
- Clear progress messages during execution
- Success/failure status with details
- Formatted output with visual separators

### File List

**New Files:**
- `/install/inkypi-refresh`
- `/install/refresh_cli.py`

**Modified Files:**
- `/install/install.sh`

**Documentation:**
- `/docs/implement-inkypi-refresh-command.md` (this file)

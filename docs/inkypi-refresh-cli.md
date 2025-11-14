# InkyPi Refresh CLI

A command-line tool to manually trigger InkyPi display refreshes without waiting for the scheduled refresh cycle.

## Overview

The `inkypi-refresh` command allows you to immediately update your InkyPi display by triggering a refresh of any playlist or specific plugin instance. This is particularly useful after system reboots or when you want to force an immediate update.

## Installation

The `inkypi-refresh` command is automatically installed when you run the standard InkyPi installation script:

```bash
sudo ./install/install.sh
```

After installation, the command will be available at `/usr/local/bin/inkypi-refresh`.

## Usage

### Basic Syntax

```bash
inkypi-refresh --playlist="<playlist_name>" [--plugin="<instance_name>"] [--force]
```

### Arguments

- `--playlist` (required): Name of the playlist to refresh
- `--plugin` (optional): Name of specific plugin instance to refresh
- `--force` (optional): Force refresh regardless of the plugin's refresh schedule

### Examples

#### Refresh the next plugin in the Default playlist
```bash
inkypi-refresh --playlist="Default"
```

#### Refresh a specific plugin instance
```bash
inkypi-refresh --playlist="Default" --plugin="Surfer Instance"
```

#### Force refresh regardless of schedule
```bash
inkypi-refresh --playlist="Default" --force
```

## Use Cases

### 1. Automatic Refresh After Reboot

If your system reboots and you want the display to update immediately, add the refresh command to your systemd service file.

Edit `/etc/systemd/system/inkypi.service`:

```ini
[Unit]
Description=InkyPi App
After=network-online.target
Wants=network-online.target

[Service]
User=root
RuntimeDirectory=inkypi
WorkingDirectory=/run/inkypi
ExecStart=/usr/local/bin/inkypi -d
ExecStartPost=/bin/sleep 10
ExecStartPost=/usr/local/bin/inkypi-refresh --playlist="Default"
Restart=on-failure
RestartSec=60
KillSignal=SIGINT
StandardOutput=journal
StandardError=journal
CPUQuota=40%
MemoryMax=200M

[Install]
WantedBy=multi-user.target
```

After editing, reload systemd:
```bash
sudo systemctl daemon-reload
sudo systemctl restart inkypi
```

### 2. Manual Refresh

Simply run the command whenever you want to update the display:
```bash
sudo inkypi-refresh --playlist="Default"
```

### 3. Scheduled Refresh via Cron

Add a cron job to refresh at specific times:
```bash
# Edit crontab
sudo crontab -e

# Add line to refresh every day at 6 AM
0 6 * * * /usr/local/bin/inkypi-refresh --playlist="Default" --force
```

### 4. Refresh After Configuration Changes

After modifying plugin settings or playlist configurations:
```bash
sudo inkypi-refresh --playlist="Default" --force
```

## Output

The command provides clear feedback during execution:

```
InkyPi Refresh CLI
==================================================
Loading device configuration...
Playlist: Default
Plugin Instance: Surfer Instance (next in rotation)
==================================================
Executing refresh...
--------------------------------------------------
Image changed, updating display...
Display updated successfully!
--------------------------------------------------
Refresh completed successfully
Plugin: surfer
Instance: Surfer Instance
Time: 2025-11-14 15:30:45
==================================================
```

## Error Handling

### Playlist Not Found
```bash
$ inkypi-refresh --playlist="Invalid"
Error: Playlist 'Invalid' not found
Available playlists: Default, Morning, Evening
```

### Plugin Instance Not Found
```bash
$ inkypi-refresh --playlist="Default" --plugin="Invalid"
Error: Plugin instance 'Invalid' not found in playlist 'Default'
Available plugin instances: Surfer Instance (surfer), Clock (clock)
```

## Exit Codes

- `0`: Success
- `1`: Error (invalid arguments, plugin not found, execution failure)
- `130`: Cancelled by user (Ctrl+C)

## Troubleshooting

### Command Not Found

If you get "command not found", ensure:
1. InkyPi is properly installed
2. The command exists at `/usr/local/bin/inkypi-refresh`
3. The command is executable: `sudo chmod +x /usr/local/bin/inkypi-refresh`

### Virtual Environment Error

If you get errors about missing modules:
```bash
Error: Virtual environment not found at /usr/local/inkypi/venv_inkypi
```

Ensure InkyPi is properly installed by running the installation script again.

### Permission Denied

Run the command with `sudo`:
```bash
sudo inkypi-refresh --playlist="Default"
```

## Advanced Usage

### Integrating with Home Automation

You can call `inkypi-refresh` from Home Assistant, Node-RED, or other automation platforms via SSH:

```yaml
# Home Assistant example
shell_command:
  refresh_inkypi: "ssh pi@inkypi.local 'sudo /usr/local/bin/inkypi-refresh --playlist=Default --force'"
```

### Debugging

To see detailed logs, check the systemd journal:
```bash
sudo journalctl -u inkypi -f
```

Or run the underlying Python script directly for more verbose output:
```bash
cd /usr/local/inkypi
source venv_inkypi/bin/activate
python install/refresh_cli.py --playlist="Default"
```

## Related Documentation

- [Installation Guide](installation.md)
- [Building Plugins](building_plugins.md)
- [Troubleshooting](troubleshooting.md)
- [Implementation Story](implement-inkypi-refresh-command.md)

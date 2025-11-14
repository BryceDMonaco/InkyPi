#!/usr/bin/env python3
"""
InkyPi Refresh CLI - Manually trigger display refreshes for playlists and plugins

This script provides a command-line interface to trigger manual refreshes of
InkyPi display content without waiting for the scheduled refresh cycle.

Usage:
    python refresh_cli.py --playlist="Default" [--plugin="Instance Name"] [--force]

Arguments:
    --playlist    Name of the playlist to refresh (required)
    --plugin      Name of specific plugin instance to refresh (optional)
    --force       Force refresh regardless of schedule (optional)
"""

import sys
import os
import argparse
import logging
from datetime import datetime

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import Config
from display.display_manager import DisplayManager
from refresh_task import RefreshTask, ManualRefresh, PlaylistRefresh

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Manually trigger InkyPi display refresh',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Refresh the next plugin in the Default playlist
  %(prog)s --playlist="Default"

  # Refresh a specific plugin instance
  %(prog)s --playlist="Default" --plugin="Surfer Instance"

  # Force refresh regardless of schedule
  %(prog)s --playlist="Default" --force
        """
    )

    parser.add_argument(
        '--playlist',
        type=str,
        required=True,
        help='Name of the playlist to refresh'
    )

    parser.add_argument(
        '--plugin',
        type=str,
        help='Name of specific plugin instance to refresh (optional)'
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='Force refresh regardless of schedule'
    )

    return parser.parse_args()


def main():
    """Main entry point for the refresh CLI."""
    args = parse_arguments()

    logger.info("InkyPi Refresh CLI")
    logger.info("=" * 50)

    try:
        # Load device configuration
        logger.info("Loading device configuration...")
        device_config = Config()

        # Get playlist manager
        playlist_manager = device_config.get_playlist_manager()

        # Validate playlist exists
        playlist = playlist_manager.get_playlist(args.playlist)
        if not playlist:
            logger.error(f"Error: Playlist '{args.playlist}' not found")
            logger.info(f"Available playlists: {', '.join(playlist_manager.get_playlist_names())}")
            return 1

        logger.info(f"Playlist: {args.playlist}")

        # Validate plugin exists if specified
        plugin_instance = None
        if args.plugin:
            plugin_instance = playlist.find_plugin(None, args.plugin)
            if not plugin_instance:
                # Try searching by plugin_id across all plugins in playlist
                for p in playlist.plugins:
                    if p.name == args.plugin:
                        plugin_instance = p
                        break

                if not plugin_instance:
                    logger.error(f"Error: Plugin instance '{args.plugin}' not found in playlist '{args.playlist}'")
                    available_plugins = [f"{p.name} ({p.plugin_id})" for p in playlist.plugins]
                    logger.info(f"Available plugin instances: {', '.join(available_plugins)}")
                    return 1

            logger.info(f"Plugin Instance: {args.plugin}")
        else:
            # Get next plugin in rotation
            if not playlist.plugins:
                logger.error(f"Error: Playlist '{args.playlist}' has no plugins")
                return 1

            plugin_instance = playlist.get_next_plugin()
            logger.info(f"Plugin Instance: {plugin_instance.name} (next in rotation)")

        if args.force:
            logger.info("Force Mode: Enabled")

        # Initialize display manager
        logger.info("Initializing display manager...")
        display_manager = DisplayManager(device_config)

        # Initialize refresh task (but don't start background thread)
        refresh_task = RefreshTask(device_config, display_manager)
        refresh_task.running = True  # Set running flag without starting thread

        # Create refresh action
        logger.info("Creating refresh action...")
        refresh_action = PlaylistRefresh(
            playlist=playlist,
            plugin_instance=plugin_instance,
            force=args.force
        )

        # Get plugin config
        plugin_config = device_config.get_plugin(plugin_instance.plugin_id)
        if not plugin_config:
            logger.error(f"Error: Plugin config not found for '{plugin_instance.plugin_id}'")
            return 1

        # Import plugin
        from plugins.plugin_registry import get_plugin_instance
        plugin = get_plugin_instance(plugin_config)

        # Execute refresh
        logger.info("=" * 50)
        logger.info("Executing refresh...")
        logger.info("-" * 50)

        current_dt = refresh_task._get_current_datetime()

        # Execute the refresh action
        image = refresh_action.execute(plugin, device_config, current_dt)

        # Compute image hash
        from utils.image_utils import compute_image_hash
        image_hash = compute_image_hash(image)

        # Get refresh info
        refresh_info = refresh_action.get_refresh_info()
        refresh_info.update({
            "refresh_time": current_dt.isoformat(),
            "image_hash": image_hash
        })

        # Check if image is different from current
        latest_refresh = device_config.get_refresh_info()
        if image_hash != latest_refresh.image_hash:
            logger.info("Image changed, updating display...")
            display_manager.display_image(
                image,
                image_settings=plugin.config.get("image_settings", [])
            )
            logger.info("Display updated successfully!")
        else:
            logger.info("Image unchanged, skipping display update")

        # Update latest refresh data in the device config
        from model import RefreshInfo
        device_config.refresh_info = RefreshInfo(**refresh_info)
        device_config.write_config()

        logger.info("-" * 50)
        logger.info("Refresh completed successfully")
        logger.info(f"Plugin: {refresh_info['plugin_id']}")
        logger.info(f"Instance: {refresh_info.get('plugin_instance', 'N/A')}")
        logger.info(f"Time: {current_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 50)

        return 0

    except KeyboardInterrupt:
        logger.info("\nRefresh cancelled by user")
        return 130
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        logger.exception("Full traceback:")
        return 1


if __name__ == '__main__':
    sys.exit(main())

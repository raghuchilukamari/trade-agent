#!/usr/bin/env python3
# walter.py - Updated for daily pipeline

import json
import csv
from datetime import datetime
import os
from typing import List, Dict, Optional
import re
import argparse
import glob

# Symbols that appear as standalone Discord reactions/arrows with no informational content
_INVALID_DESC_RE = re.compile(
    r'^\s*[ -⟿︀-﻿■-◿←-⇿⬀-⯿↧▻↑↓→←↔▶◄▲▼◆◇●○□■▪▫\s]*$'
)

def _is_valid_description(text: str) -> bool:
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    if len(stripped) < 5:
        return False
    if _INVALID_DESC_RE.match(stripped):
        return False
    return any(c.isalpha() or c.isdigit() for c in stripped)


class DiscordMessageExtractor:
    """
    Extracts message data from Discord JSON exports and converts to CSV format
    """

    def __init__(self, input_file: str, output_file: str = None, append_mode: bool = True):
        """
        Initialize the extractor

        Args:
            input_file: Path to input JSON file
            output_file: Path to output CSV file
            append_mode: If True, append to existing CSV; if False, overwrite
        """
        self.input_file = input_file
        self.output_file = output_file or input_file.replace('.json', '_extracted.csv')
        self.append_mode = append_mode

    def parse_timestamp(self, timestamp_str: str) -> tuple:
        """
        Parse timestamp string to extract date and time

        Args:
            timestamp_str: ISO format timestamp with timezone

        Returns:
            Tuple of (date_str, time_str)
        """
        try:
            # Remove timezone offset for parsing
            if '+' in timestamp_str or timestamp_str.count('-') == 3:
                if '+' in timestamp_str:
                    dt_part = timestamp_str.rsplit('+', 1)[0]
                else:
                    dt_part = timestamp_str.rsplit('-', 1)[0]
            else:
                dt_part = timestamp_str

            # Parse the datetime
            if '.' in dt_part:
                dt = datetime.strptime(dt_part, "%Y-%m-%dT%H:%M:%S.%f")
            else:
                dt = datetime.strptime(dt_part, "%Y-%m-%dT%H:%M:%S")

            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M:%S")

            return date_str, time_str

        except Exception as e:
            print(f"Error parsing timestamp '{timestamp_str}': {e}")
            return "", ""

    def extract_description(self, message: Dict) -> str:
        """
        Extract description from message embeds

        Args:
            message: Dictionary containing message data

        Returns:
            Description text or empty string if not found
        """
        # Check if embeds exist and have content
        if 'embeds' in message and message['embeds']:
            for embed in message['embeds']:
                if 'description' in embed and embed['description']:
                    desc = embed['description']
                    # Replace commas with spaces for CSV compatibility
                    desc = desc.replace(",", " ")
                    desc = desc.replace("\n", " ")
                    # Replace pipes for pipe-delimited format
                    desc = desc.replace("|", " ")
                    return desc

        # Fallback to content if no embed description
        if 'content' in message and message['content']:
            content = message['content']
            # Remove markdown links
            content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', content)
            # Replace pipes for pipe-delimited format
            content = content.replace("|", " ")
            return content

        return ""

    def process_single_message(self, message: Dict) -> Optional[Dict]:
        """
        Process a single message and extract required fields

        Args:
            message: Dictionary containing message data

        Returns:
            Dictionary with extracted fields or None if processing fails
        """
        try:
            timestamp = message.get('timestamp', '')
            date, time = self.parse_timestamp(timestamp)
            description = self.extract_description(message)

            # Only return if we have meaningful data and a valid description
            if date and time and description and _is_valid_description(description):
                return {
                    'Date': date,
                    'Time': time,
                    'Description': description
                }

            return None

        except Exception as e:
            print(f"Error processing message: {e}")
            return None

    def load_json_file(self) -> List[Dict]:
        """
        Load JSON file and return messages list

        Returns:
            List of message dictionaries
        """
        try:
            with open(self.input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Handle different JSON structures
            if isinstance(data, dict):
                if 'messages' in data:
                    return data['messages']
                elif 'id' in data and 'timestamp' in data:
                    return [data]
                else:
                    print("Unexpected JSON structure")
                    return []
            elif isinstance(data, list):
                return data
            else:
                print(f"Unexpected data type: {type(data)}")
                return []

        except FileNotFoundError:
            print(f"File not found: {self.input_file}")
            return []
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            return []
        except Exception as e:
            print(f"Error loading file: {e}")
            return []

    def save_to_csv(self, extracted_data: List[Dict]):
        """
        Save extracted data to CSV file (pipe-delimited, append mode)

        Args:
            extracted_data: List of dictionaries with extracted fields
        """
        if not extracted_data:
            print("No data to save")
            return

        try:
            file_exists = os.path.isfile(self.output_file)
            mode = 'a' if self.append_mode else 'w'

            with open(self.output_file, mode, newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=['Date', 'Time', 'Description'],
                    delimiter='|'
                )

                # Write header only if file doesn't exist or not in append mode
                if not file_exists or not self.append_mode:
                    writer.writeheader()

                writer.writerows(extracted_data)

            action = "Appended" if self.append_mode and file_exists else "Saved"
            print(f"{action} {len(extracted_data)} records to {self.output_file}")

        except Exception as e:
            print(f"Error saving to CSV: {e}")
            raise

    def extract_and_save(self) -> int:
        """
        Main method to extract data from JSON and save to CSV

        Returns:
            Number of records extracted (0 if error)
        """
        print(f"Processing: {self.input_file}")

        # Load messages
        messages = self.load_json_file()

        if not messages:
            print("No messages found in the file")
            return 0

        print(f"Found {len(messages)} messages")

        # Process each message
        extracted_data = []
        skipped_count = 0

        for message in messages:
            result = self.process_single_message(message)
            if result:
                extracted_data.append(result)
            else:
                skipped_count += 1

        print(f"Extracted {len(extracted_data)} messages, skipped {skipped_count}")

        if not extracted_data:
            print("No valid data extracted")
            return 0

        # Save to CSV
        self.save_to_csv(extracted_data)

        return len(extracted_data)


def find_latest_json(raw_dir: str, channel_name: str) -> Optional[str]:
    """
    Find the most recent JSON file for a channel

    Args:
        raw_dir: Base directory containing raw JSON files
        channel_name: Name of the channel

    Returns:
        Path to latest JSON file or None if not found
    """
    pattern = os.path.join(raw_dir, channel_name, "*.json")
    files = glob.glob(pattern)

    if not files:
        print(f"No JSON files found matching: {pattern}")
        return None

    # Return the most recently modified file
    latest_file = max(files, key=os.path.getmtime)
    print(f"Found latest file: {latest_file}")
    return latest_file


def main():
    """
    Command-line interface for the extractor
    """
    parser = argparse.ArgumentParser(
        description='Extract Discord messages from JSON to pipe-delimited CSV'
    )
    parser.add_argument(
        '--channel',
        required=True,
        help='Channel name (e.g., unusual-flows)'
    )
    parser.add_argument(
        '--raw-dir',
        required=True,
        help='Directory containing raw JSON files'
    )
    parser.add_argument(
        '--output-dir',
        required=True,
        help='Directory for formatted CSV output'
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite CSV instead of appending (default: append)'
    )

    args = parser.parse_args()

    # Find latest JSON file for the channel
    json_file = find_latest_json(args.raw_dir, args.channel)

    if not json_file:
        print(f"ERROR: No JSON file found for channel '{args.channel}'")
        return 1

    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)

    # Output CSV file path
    output_file = os.path.join(args.output_dir, f"{args.channel}.csv")

    # Process the file
    extractor = DiscordMessageExtractor(
        input_file=json_file,
        output_file=output_file,
        append_mode=not args.overwrite
    )

    try:
        count = extractor.extract_and_save()
        if count > 0:
            print(f"✅ Success: {count} records processed")
            return 0
        else:
            print("⚠️  Warning: No records extracted")
            return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
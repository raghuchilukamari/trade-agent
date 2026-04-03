#!/usr/bin/env python3
# bullseye.py - Parser for bullseye channel

import json
import csv
from datetime import datetime
import os
from typing import List, Dict, Optional
import argparse
import glob


class BullseyeExtractor:
    """
    Extracts Bullseye trade ideas from Discord JSON exports and converts to CSV format
    """

    def __init__(self, input_file: str, output_file: str = None, append_mode: bool = True):
        self.input_file = input_file
        self.output_file = output_file or input_file.replace('.json', '_bullseye.csv')
        self.append_mode = append_mode

    def parse_timestamp(self, timestamp_str: str) -> tuple:
        """Parse timestamp to extract date and time"""
        try:
            if '+' in timestamp_str or timestamp_str.count('-') == 3:
                dt_part = timestamp_str.rsplit('+' if '+' in timestamp_str else '-', 1)[0]
            else:
                dt_part = timestamp_str

            if '.' in dt_part:
                dt = datetime.strptime(dt_part, "%Y-%m-%dT%H:%M:%S.%f")
            else:
                dt = datetime.strptime(dt_part, "%Y-%m-%dT%H:%M:%S")

            return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S")
        except Exception as e:
            print(f"Error parsing timestamp '{timestamp_str}': {e}")
            return "", ""

    def clean_field_value(self, value: str) -> str:
        """Clean field value by removing emojis and special characters"""
        if not value:
            return ""

        # Remove emoji codes
        value = value.replace(':rocket:', '')
        value = value.replace(':boom:', '')
        value = value.replace('🚀', '')
        value = value.replace('💥', '')

        # Remove pipe for CSV compatibility
        value = value.replace('|', ' ')

        return value.strip()

    def extract_field_value(self, fields: List[Dict], field_name: str) -> str:
        """Extract value from fields array by field name"""
        for field in fields:
            if field.get('name', '').lower() == field_name.lower():
                value = field.get('value', '')
                return self.clean_field_value(value)
        return ""

    def process_embed(self, embed: Dict) -> Optional[Dict]:
        """
        **UNIQUE EXTRACTION LOGIC FOR BULLSEYE**
        Process an embed and extract bullseye trade idea data
        """
        try:
            if 'fields' not in embed or not embed['fields']:
                return None

            # Check if it's a Bullseye trade idea
            author_name = embed.get('author', {}).get('name', '').lower()
            if 'bullseye' not in author_name:
                return None

            fields = embed['fields']

            # Extract all bullseye-specific fields
            symbol = self.extract_field_value(fields, 'Symbol')
            strike = self.extract_field_value(fields, 'Strike')
            expiration = self.extract_field_value(fields, 'Expiration')
            call_put = self.extract_field_value(fields, 'Call/Put')
            buy_sell = self.extract_field_value(fields, 'Buy/Sell')
            ai_confidence = self.extract_field_value(fields, 'AI Confidence')
            prems_spent = self.extract_field_value(fields, 'Prems Spent')
            volume = self.extract_field_value(fields, 'Volume')
            oi = self.extract_field_value(fields, 'OI')

            # Check if we have minimum required data
            if symbol and strike and expiration:
                return {
                    'Symbol': symbol.upper(),
                    'Strike': strike,
                    'Expiration': expiration,
                    'Call_Put': call_put,
                    'Buy_Sell': buy_sell,
                    'AI_Confidence': ai_confidence,
                    'Prems_Spent': prems_spent,
                    'Volume': volume,
                    'OI': oi,
                }

            return None
        except Exception as e:
            print(f"Error processing embed: {e}")
            return None

    def process_single_message(self, message: Dict) -> Optional[Dict]:
        """Process a single message"""
        try:
            timestamp = message.get('timestamp', '')
            date, time = self.parse_timestamp(timestamp)

            if not date or not time:
                return None

            embeds = message.get('embeds', [])

            for embed in embeds:
                bullseye_data = self.process_embed(embed)

                if bullseye_data:
                    bullseye_data['Date'] = date
                    bullseye_data['Time'] = time

                    return {
                        'Date': bullseye_data['Date'],
                        'Time': bullseye_data['Time'],
                        'Symbol': bullseye_data['Symbol'],
                        'Strike': bullseye_data['Strike'],
                        'Expiration': bullseye_data['Expiration'],
                        'Call_Put': bullseye_data['Call_Put'],
                        'Buy_Sell': bullseye_data['Buy_Sell'],
                        'AI_Confidence': bullseye_data['AI_Confidence'],
                        'Prems_Spent': bullseye_data['Prems_Spent'],
                        'Volume': bullseye_data['Volume'],
                        'OI': bullseye_data['OI'],
                    }

            return None
        except Exception as e:
            print(f"Error processing message: {e}")
            return None

    def load_json_file(self) -> List[Dict]:
        """Load JSON file and return messages list"""
        try:
            with open(self.input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, dict):
                if 'messages' in data:
                    return data['messages']
                elif 'id' in data and 'timestamp' in data:
                    return [data]
                else:
                    return []
            elif isinstance(data, list):
                return data
            else:
                return []
        except Exception as e:
            print(f"Error loading file: {e}")
            return []

    def save_to_csv(self, extracted_data: List[Dict]):
        """Save to pipe-delimited CSV with append mode"""
        if not extracted_data:
            print("No data to save")
            return

        try:
            file_exists = os.path.isfile(self.output_file)
            mode = 'a' if self.append_mode else 'w'

            with open(self.output_file, mode, newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        'Date', 'Time', 'Symbol', 'Strike', 'Expiration',
                        'Call_Put', 'Buy_Sell', 'AI_Confidence', 'Prems_Spent',
                        'Volume', 'OI'
                    ],
                    delimiter='|'
                )

                if not file_exists or not self.append_mode:
                    writer.writeheader()

                writer.writerows(extracted_data)

            action = "Appended" if self.append_mode and file_exists else "Saved"
            print(f"{action} {len(extracted_data)} records to {self.output_file}")
        except Exception as e:
            print(f"Error saving to CSV: {e}")
            raise

    def extract_and_save(self) -> int:
        """Main method to extract and save"""
        print(f"Processing: {self.input_file}")

        messages = self.load_json_file()

        if not messages:
            print("No messages found")
            return 0

        print(f"Found {len(messages)} messages")

        extracted_data = []
        skipped = 0

        for message in messages:
            result = self.process_single_message(message)
            if result:
                extracted_data.append(result)
            else:
                skipped += 1

        print(f"Extracted {len(extracted_data)} bullseye ideas, skipped {skipped}")

        if not extracted_data:
            print("No valid data extracted")
            return 0

        self.save_to_csv(extracted_data)
        return len(extracted_data)


def find_latest_json(raw_dir: str, channel_name: str) -> Optional[str]:
    """Find the most recent JSON file for a channel"""
    pattern = os.path.join(raw_dir, channel_name, "*.json")
    files = glob.glob(pattern)

    if not files:
        print(f"No JSON files found matching: {pattern}")
        return None

    latest_file = max(files, key=os.path.getmtime)
    print(f"Found latest file: {latest_file}")
    return latest_file


def main():
    parser = argparse.ArgumentParser(description='Extract bullseye trade ideas from JSON to pipe-delimited CSV')
    parser.add_argument('--channel', required=True, help='Channel name')
    parser.add_argument('--raw-dir', required=True, help='Directory containing raw JSON files')
    parser.add_argument('--output-dir', required=True, help='Directory for formatted CSV output')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite CSV instead of appending')

    args = parser.parse_args()

    json_file = find_latest_json(args.raw_dir, args.channel)

    if not json_file:
        print(f"ERROR: No JSON file found for channel '{args.channel}'")
        return 1

    os.makedirs(args.output_dir, exist_ok=True)

    output_file = os.path.join(args.output_dir, f"{args.channel}.csv")

    extractor = BullseyeExtractor(
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
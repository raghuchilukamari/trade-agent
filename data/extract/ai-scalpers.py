#!/usr/bin/env python3
# ai-scalpers.py - Parser for ai-scalpers channel

import json
import csv
from datetime import datetime
import os
from typing import List, Dict, Optional
import argparse
import glob
import re


class AIScalpersExtractor:
    """
    Extracts AI scalper trade alerts from Discord JSON exports and converts to CSV format
    """

    def __init__(self, input_file: str, output_file: str = None, append_mode: bool = True):
        self.input_file = input_file
        self.output_file = output_file or input_file.replace('.json', '_ai_scalpers.csv')
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
        value = value.replace(':star:', '')
        value = value.replace(':chart_with_upwards_trend:', '')
        value = value.replace(':chart_with_downwards_trend:', '')
        value = value.replace('🚀', '')
        value = value.replace('💥', '')
        value = value.replace('⭐', '')
        value = value.replace('📈', '')
        value = value.replace('📉', '')

        # Remove markdown formatting
        value = value.replace('**', '')
        value = value.replace('> ', '')

        # Remove pipe for CSV compatibility
        value = value.replace('|', ' ')

        # Remove newlines
        value = value.replace('\n', ' ')

        return ' '.join(value.split()).strip()

    def extract_field_value(self, fields: List[Dict], field_name: str) -> str:
        """Extract value from fields array by field name"""
        for field in fields:
            if field.get('name', '').lower() == field_name.lower():
                value = field.get('value', '')
                return self.clean_field_value(value)
        return ""

    def process_embed(self, embed: Dict) -> Optional[Dict]:
        """Process an embed and extract AI scalper trade data"""
        try:
            if 'fields' not in embed or not embed['fields']:
                description = embed.get('description', '')
                if description:
                    return self.parse_from_description(description, embed)
                return None

            fields = embed['fields']

            # Extract common scalper fields
            symbol = self.extract_field_value(fields, 'Symbol')
            direction = self.extract_field_value(fields, 'Direction')
            if not direction:
                direction = self.extract_field_value(fields, 'Side')
            if not direction:
                direction = self.extract_field_value(fields, 'Type')

            entry_price = self.extract_field_value(fields, 'Entry Price')
            if not entry_price:
                entry_price = self.extract_field_value(fields, 'Entry')

            target_price = self.extract_field_value(fields, 'Target Price')
            if not target_price:
                target_price = self.extract_field_value(fields, 'Target')
            if not target_price:
                target_price = self.extract_field_value(fields, 'TP')

            stop_loss = self.extract_field_value(fields, 'Stop Loss')
            if not stop_loss:
                stop_loss = self.extract_field_value(fields, 'SL')
            if not stop_loss:
                stop_loss = self.extract_field_value(fields, 'Stop')

            ai_confidence = self.extract_field_value(fields, 'AI Confidence')
            if not ai_confidence:
                ai_confidence = self.extract_field_value(fields, 'Confidence')

            timeframe = self.extract_field_value(fields, 'Timeframe')
            if not timeframe:
                timeframe = self.extract_field_value(fields, 'Time Frame')

            reason = self.extract_field_value(fields, 'Reason')
            if not reason:
                reason = self.extract_field_value(fields, 'Signal')

            desc = embed.get('description', '')
            desc = self.clean_field_value(desc)

            if not symbol and desc:
                symbol_match = re.search(r'\b([A-Z]{1,5})\b', desc)
                if symbol_match:
                    symbol = symbol_match.group(1)

            if symbol:
                return {
                    'Symbol': symbol.upper(),
                    'Direction': direction,
                    'Entry_Price': entry_price,
                    'Target_Price': target_price,
                    'Stop_Loss': stop_loss,
                    'AI_Confidence': ai_confidence,
                    'Timeframe': timeframe,
                    'Reason': reason,
                    'Description': desc
                }

            return None
        except Exception as e:
            print(f"Error processing embed: {e}")
            return None

    def parse_from_description(self, description: str, embed: Dict) -> Optional[Dict]:
        """Parse scalper data from description when fields are not available"""
        desc_clean = self.clean_field_value(description)

        symbol_match = re.search(r'\b([A-Z]{2,5})\b', desc_clean)
        symbol = symbol_match.group(1) if symbol_match else ''

        direction = ''
        if 'long' in desc_clean.lower():
            direction = 'LONG'
        elif 'short' in desc_clean.lower():
            direction = 'SHORT'
        elif 'buy' in desc_clean.lower():
            direction = 'LONG'
        elif 'sell' in desc_clean.lower():
            direction = 'SHORT'

        if symbol:
            return {
                'Symbol': symbol.upper(),
                'Direction': direction,
                'Entry_Price': '',
                'Target_Price': '',
                'Stop_Loss': '',
                'AI_Confidence': '',
                'Timeframe': '',
                'Reason': '',
                'Description': desc_clean
            }

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
                scalper_data = self.process_embed(embed)

                if scalper_data:
                    scalper_data['Date'] = date
                    scalper_data['Time'] = time

                    return {
                        'Date': scalper_data['Date'],
                        'Time': scalper_data['Time'],
                        'Symbol': scalper_data['Symbol'],
                        'Direction': scalper_data['Direction'],
                        'Entry_Price': scalper_data['Entry_Price'],
                        'Target_Price': scalper_data['Target_Price'],
                        'Stop_Loss': scalper_data['Stop_Loss'],
                        'AI_Confidence': scalper_data['AI_Confidence'],
                        'Timeframe': scalper_data['Timeframe'],
                        'Reason': scalper_data['Reason'],
                        'Description': scalper_data['Description']
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
                    messages = data['messages']
                    # Check if messages array is empty
                    if not messages:
                        print(f"ℹ️  Info: Channel has 0 messages (empty channel)")
                    return messages
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
                        'Date', 'Time', 'Symbol', 'Direction', 'Entry_Price',
                        'Target_Price', 'Stop_Loss', 'AI_Confidence', 'Timeframe',
                        'Reason', 'Description'
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
            print("⚠️  No messages found - channel is empty or file has no data")
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

        if not extracted_data:
            print(f"⚠️  No valid data extracted from {len(messages)} messages")
            print(f"   (Channel may not have AI scalper alerts yet)")
            return 0

        print(f"Extracted {len(extracted_data)} scalper alerts, skipped {skipped}")
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
    parser = argparse.ArgumentParser(description='Extract AI scalper alerts from JSON to pipe-delimited CSV')
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

    extractor = AIScalpersExtractor(
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
            print("ℹ️  No records to process (empty channel or no matching data)")
            return 0  # Return 0 (success) even with no data - this is expected for empty channels
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
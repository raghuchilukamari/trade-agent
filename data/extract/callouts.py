#!/usr/bin/env python3
# callouts-ideas.py - Parser for callouts-ideas channel

import json
import csv
from datetime import datetime
import os
from typing import List, Dict, Optional
import argparse
import glob
import re


class CalloutsExtractor:
    """
    Extracts callout/trade ideas from Discord JSON exports and converts to CSV format
    """

    def __init__(self, input_file: str, output_file: str = None, append_mode: bool = True):
        self.input_file = input_file
        self.output_file = output_file or input_file.replace('.json', '_callouts.csv')
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
        """Clean field value by removing markdown and special characters"""
        if not value:
            return ""

        # Remove markdown formatting
        value = value.replace('**', '')
        value = value.replace('*', '')

        # Remove pipe for CSV compatibility
        value = value.replace('|', ' ')

        # Clean up whitespace
        value = ' '.join(value.split()).strip()

        return value

    def parse_callout_content(self, content: str, author_name: str) -> Optional[Dict]:
        """
        Parse structured callout from message content

        Expected format:
        Ticker: SLV
        Contract: 65c Jan09
        Direction: Calls
        Thesis: PB LEVEL HOLD 64
        Invalidation: Cut under 62 on daily
        """
        if not content:
            return None

        # Skip pinned messages and system messages
        if content == "Pinned a message.":
            return None

        # Skip template messages (empty fields)
        if "Ticker: \nContract:\nDirection:\nThesis:\nInvalidation:" in content:
            return None

        # Check if this looks like a callout (has the key fields)
        if 'Ticker:' not in content:
            return None

        # Extract fields using regex
        ticker_match = re.search(r'Ticker:\s*([^\n]+)', content, re.IGNORECASE)
        contract_match = re.search(r'Contract:\s*([^\n]+)', content, re.IGNORECASE)
        direction_match = re.search(r'Direction:\s*([^\n]+)', content, re.IGNORECASE)
        thesis_match = re.search(r'Thesis:\s*([^\n]+)', content, re.IGNORECASE)
        invalidation_match = re.search(r'Invalidation:\s*([^\n]+)', content, re.IGNORECASE)

        # Extract values
        ticker = self.clean_field_value(ticker_match.group(1)) if ticker_match else ''
        contract = self.clean_field_value(contract_match.group(1)) if contract_match else ''
        direction = self.clean_field_value(direction_match.group(1)) if direction_match else ''
        thesis = self.clean_field_value(thesis_match.group(1)) if thesis_match else ''
        invalidation = self.clean_field_value(invalidation_match.group(1)) if invalidation_match else ''

        # Must at least have ticker
        if not ticker:
            return None

        # Parse contract to extract strike, type, and expiration
        strike, call_put, expiration = self.parse_contract(contract)

        return {
            'Ticker': ticker.upper(),
            'Contract': contract,
            'Strike': strike,
            'Call_Put': call_put,
            'Expiration': expiration,
            'Direction': direction.upper(),
            'Thesis': thesis,
            'Invalidation': invalidation,
            'Author': author_name
        }

    def parse_contract(self, contract: str) -> tuple:
        """
        Parse contract string to extract strike, type, and expiration
        Examples:
        - "65c Jan09" -> (65, CALL, Jan09)
        - "190C JAN09" -> (190, CALL, JAN09)
        - "115C JAN15" -> (115, CALL, JAN15)
        """
        if not contract:
            return '', '', ''

        contract = contract.strip()

        # Extract strike (number at beginning)
        strike_match = re.search(r'^(\d+(?:\.\d+)?)', contract)
        strike = strike_match.group(1) if strike_match else ''

        # Extract call/put
        call_put = ''
        if re.search(r'\bc\b', contract, re.IGNORECASE):
            call_put = 'CALL'
        elif re.search(r'\bp\b', contract, re.IGNORECASE):
            call_put = 'PUT'

        # Extract expiration (e.g., Jan09, JAN15)
        exp_match = re.search(r'([A-Za-z]{3}\d{2})', contract)
        expiration = exp_match.group(1).upper() if exp_match else ''

        return strike, call_put, expiration

    def process_single_message(self, message: Dict) -> Optional[Dict]:
        """Process a single message"""
        try:
            # Skip non-default message types
            if message.get('type') != 'Default':
                return None

            timestamp = message.get('timestamp', '')
            date, time = self.parse_timestamp(timestamp)

            if not date or not time:
                return None

            content = message.get('content', '')
            author = message.get('author', {})
            author_name = author.get('nickname') or author.get('name', 'Unknown')

            # Parse the callout content
            callout_data = self.parse_callout_content(content, author_name)

            if callout_data:
                callout_data['Date'] = date
                callout_data['Time'] = time

                return {
                    'Date': callout_data['Date'],
                    'Time': callout_data['Time'],
                    'Ticker': callout_data['Ticker'],
                    'Contract': callout_data['Contract'],
                    'Strike': callout_data['Strike'],
                    'Call_Put': callout_data['Call_Put'],
                    'Expiration': callout_data['Expiration'],
                    'Direction': callout_data['Direction'],
                    'Thesis': callout_data['Thesis'],
                    'Invalidation': callout_data['Invalidation'],
                    'Author': callout_data['Author']
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
                        'Date', 'Time', 'Ticker', 'Contract', 'Strike', 'Call_Put',
                        'Expiration', 'Direction', 'Thesis', 'Invalidation', 'Author'
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

        print(f"Extracted {len(extracted_data)} callouts, skipped {skipped}")

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
    parser = argparse.ArgumentParser(description='Extract callouts/ideas from JSON to pipe-delimited CSV')
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

    extractor = CalloutsExtractor(
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
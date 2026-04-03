#!/usr/bin/env python3
# sexy-flow-beta.py - Parser for sexy-flow-beta channel

import json
import csv
from datetime import datetime
import os
from typing import List, Dict, Optional
import argparse
import glob
import re


class SexyFlowExtractor:
    """
    Extracts Unusual Whales sexy flow alerts from Discord JSON exports and converts to CSV format
    """

    def __init__(self, input_file: str, output_file: str = None, append_mode: bool = True):
        self.input_file = input_file
        self.output_file = output_file or input_file.replace('.json', '_sexy_flow.csv')
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

        # Remove emoji codes and actual emojis
        value = value.replace(':rocket:', '')
        value = value.replace(':fire:', '')
        value = value.replace('🚀', '')
        value = value.replace('🔥', '')
        value = value.replace('🕑', '')

        # Remove markdown formatting
        value = value.replace('**', '')
        value = value.replace('>>> ', '')

        # Remove pipe for CSV compatibility
        value = value.replace('|', ' ')

        # Remove newlines
        value = value.replace('\n', ' ')

        return ' '.join(value.split()).strip()

    def extract_symbol_from_title(self, title: str) -> tuple:
        """
        Extract symbol, strike, call/put, expiration from UW title
        Examples:
        - "🚀 LEU 300.0 C 2/20/2026 (53D) - 🔥 Hot Contract - Ask Side (CUSTOM)"
        - "🚀 HUT 35.0 P 1/30/2026 (32D) - 🔥 Hot Contract - Ask Side (DEFAULT)"
        - "🕑 HUT 35.0 P 1/30/2026 (32D) - Interval (5 min) - Ask Side (DEFAULT)"
        """
        title = self.clean_field_value(title)

        # Split and parse
        parts = title.split()

        symbol = ''
        strike = ''
        call_put = ''
        expiration = ''
        alert_type = ''

        # Extract symbol (first alphabetic token)
        for part in parts:
            if part.isalpha() and len(part) <= 5:
                symbol = part
                break

        # Extract strike (number followed by C or P)
        strike_match = re.search(r'(\d+(?:\.\d+)?)\s*([CP])\s', title)
        if strike_match:
            strike = strike_match.group(1)
            call_put = 'CALL' if strike_match.group(2) == 'C' else 'PUT'

        # Extract expiration (date format M/D/YYYY)
        exp_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', title)
        if exp_match:
            expiration = exp_match.group(1)

        # Extract alert type
        if 'Hot Contract' in title:
            alert_type = 'Hot Contract'
        elif 'Interval' in title:
            # Extract interval time
            interval_match = re.search(r'Interval \(([^)]+)\)', title)
            if interval_match:
                alert_type = f"Interval ({interval_match.group(1)})"
            else:
                alert_type = 'Interval'
        elif 'Repeated Hits' in title:
            alert_type = 'Repeated Hits'

        # Extract side (Ask/Bid)
        side = ''
        if 'Ask Side' in title:
            side = 'Ask'
        elif 'Bid Side' in title:
            side = 'Bid'

        return symbol, strike, call_put, expiration, alert_type, side

    def parse_fields(self, fields: List[Dict]) -> Dict[str, str]:
        """Parse Unusual Whales field data"""
        result = {
            'Vol': '',
            'OI': '',
            'Vol_OI_Ratio': '',
            'Prem': '',
            'OTM_Pct': '',
            'Bid_Ask_Pct': '',
            'Avg_Fill': '',
            'Multileg_Vol': ''
        }

        for field in fields:
            value = self.clean_field_value(field.get('value', ''))

            # Extract volume
            vol_match = re.search(r'Vol:\s*([\d,]+)', value)
            if vol_match:
                result['Vol'] = vol_match.group(1).replace(',', '')

            # Extract OI
            oi_match = re.search(r'OI:\s*([\d,]+)', value)
            if oi_match:
                result['OI'] = oi_match.group(1).replace(',', '')

            # Extract Vol/OI ratio
            vol_oi_match = re.search(r'Vol/OI:\s*([\d.]+)', value)
            if vol_oi_match:
                result['Vol_OI_Ratio'] = vol_oi_match.group(1)

            # Extract premium
            prem_match = re.search(r'Prem:\s*\$?([\d.]+[KMB]?)', value)
            if prem_match:
                result['Prem'] = prem_match.group(1)

            # Extract % OTM
            otm_match = re.search(r'% OTM:\s*([\d]+)%', value)
            if otm_match:
                result['OTM_Pct'] = otm_match.group(1) + '%'

            # Extract Bid/Ask %
            bid_ask_match = re.search(r'Bid/Ask %:\s*([\d]+)/([\d]+)', value)
            if bid_ask_match:
                result['Bid_Ask_Pct'] = f"{bid_ask_match.group(1)}/{bid_ask_match.group(2)}"

            # Extract Avg Fill
            avg_fill_match = re.search(r'Avg Fill:\s*\$?([\d.]+)', value)
            if avg_fill_match:
                result['Avg_Fill'] = avg_fill_match.group(1)

            # Extract Multileg Vol
            multileg_match = re.search(r'Multileg Vol:\s*([\d]+)%', value)
            if multileg_match:
                result['Multileg_Vol'] = multileg_match.group(1) + '%'

        return result

    def process_embed(self, embed: Dict) -> Optional[Dict]:
        """Process Unusual Whales embed"""
        try:
            title = embed.get('title', '')
            if not title:
                return None

            # Extract data from title
            symbol, strike, call_put, expiration, alert_type, side = self.extract_symbol_from_title(title)

            # Parse fields
            field_data = self.parse_fields(embed.get('fields', []))

            # Get description
            description = embed.get('description', '')
            description = self.clean_field_value(description)

            if symbol:
                return {
                    'Symbol': symbol.upper(),
                    'Strike': strike,
                    'Call_Put': call_put,
                    'Expiration': expiration,
                    'Alert_Type': alert_type,
                    'Side': side,
                    'Vol': field_data['Vol'],
                    'OI': field_data['OI'],
                    'Vol_OI_Ratio': field_data['Vol_OI_Ratio'],
                    'Premium': field_data['Prem'],
                    'OTM_Pct': field_data['OTM_Pct'],
                    'Bid_Ask_Pct': field_data['Bid_Ask_Pct'],
                    'Avg_Fill': field_data['Avg_Fill'],
                    'Multileg_Vol': field_data['Multileg_Vol'],
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
                flow_data = self.process_embed(embed)

                if flow_data:
                    flow_data['Date'] = date
                    flow_data['Time'] = time

                    return {
                        'Date': flow_data['Date'],
                        'Time': flow_data['Time'],
                        'Symbol': flow_data['Symbol'],
                        'Strike': flow_data['Strike'],
                        'Call_Put': flow_data['Call_Put'],
                        'Expiration': flow_data['Expiration'],
                        'Alert_Type': flow_data['Alert_Type'],
                        'Side': flow_data['Side'],
                        'Vol': flow_data['Vol'],
                        'OI': flow_data['OI'],
                        'Vol_OI_Ratio': flow_data['Vol_OI_Ratio'],
                        'Premium': flow_data['Premium'],
                        'OTM_Pct': flow_data['OTM_Pct'],
                        'Bid_Ask_Pct': flow_data['Bid_Ask_Pct'],
                        'Avg_Fill': flow_data['Avg_Fill'],
                        'Multileg_Vol': flow_data['Multileg_Vol'],
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
                        'Date', 'Time', 'Symbol', 'Strike', 'Call_Put', 'Expiration',
                        'Alert_Type', 'Side', 'Vol', 'OI', 'Vol_OI_Ratio', 'Premium',
                        'OTM_Pct', 'Bid_Ask_Pct', 'Avg_Fill', 'Multileg_Vol',
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

        print(f"Extracted {len(extracted_data)} flow alerts, skipped {skipped}")

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
    parser = argparse.ArgumentParser(description='Extract sexy-flow alerts from JSON to pipe-delimited CSV')
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

    extractor = SexyFlowExtractor(
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
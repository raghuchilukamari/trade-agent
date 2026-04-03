#!/usr/bin/env python3
# golden-sweeps.py - Parser for golden-sweeps channel

import json
import csv
from datetime import datetime
import os
from typing import List, Dict, Optional
import argparse
import glob
import re


class OptionsSweepExtractor:
    """
    Extracts options sweep data from Discord JSON exports and converts to CSV format
    """

    def __init__(self, input_file: str, output_file: str = None, append_mode: bool = True):
        self.input_file = input_file
        self.output_file = output_file or input_file.replace('.json', '_options_sweeps.csv')
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


    def _looks_like_uw_custom_alert(self, embed: Dict) -> bool:
        """Heuristic to identify Unusual Whales 'UW Custom Alerts' embeds."""
        title = (embed.get('title') or '').lower()
        footer_text = ((embed.get('footer') or {}).get('text') or '').lower()
        url = (embed.get('url') or '').lower()

        # Common markers observed in UW Custom Alerts embeds
        if 'unusualwhales.com' in url:
            return True
        if 'happy hunting' in footer_text:
            return True
        if 'sweepers!' in title:
            return True

        return False

    def _parse_uw_title(self, title: str) -> Optional[Dict]:
        """
        Parse UW title strings like:
          '🔔 BILI 32.0 C 7/17/2026 (184D) - Sweepers!'
          '🔔 BE 180.0 C 2/20/2026 (37D) - Sweepers!'
        Returns dict with Symbol, Strike, Expiration when possible.
        """
        if not title:
            return None

        # Strip leading emoji / non-alphanumerics without altering core text
        t = title.strip()

        # Ticker + strike + (C/P) + expiry
        m = re.search(r'\b([A-Z]{1,10})\s+([0-9]+(?:\.[0-9]+)?)\s+([CP])\s+(\d{1,2}/\d{1,2}/\d{4})\b', t)
        if not m:
            return None

        symbol, strike, _cp, expiration = m.group(1), m.group(2), m.group(3), m.group(4)
        return {
            'Symbol': symbol.upper(),
            'Strike': strike,
            'Expiration': expiration,
            'call_put': _cp
        }

    def _extract_total_prem_from_text(self, text: str) -> str:
        """Extract 'Total Prem' from UW field blobs. Returns cleaned premium string or ''."""
        if not text:
            return ""

        # Examples: '**Total Prem:** $899K' or 'Total Prem: $1.23M'
        m = re.search(r'Total\s+Prem\s*:\s*\*{0,3}\s*\$?\s*([0-9\.,]+\s*[KMB]?)', text, flags=re.IGNORECASE)
        if not m:
            return ""

        prem = m.group(1).replace(' ', '')
        return self.clean_field_value(prem)

    def process_uw_custom_alert_embed(self, embed: Dict) -> Optional[Dict]:
        """Extract options data from UW Custom Alerts embeds (Unusual Whales)."""
        try:
            if not self._looks_like_uw_custom_alert(embed):
                return None

            title = embed.get('title', '') or ''
            parsed = self._parse_uw_title(title)
            if not parsed:
                return None

            # UW embeds often store key metrics inside field 'value' blocks with markdown
            fields = embed.get('fields', []) or []
            combined_field_text = "\n".join([(f.get('value') or '') for f in fields if isinstance(f, dict)])

            premiums = self._extract_total_prem_from_text(combined_field_text)
            if not premiums:
                # Fallback: sometimes 'Total Prem' can appear in description/footer
                premiums = self._extract_total_prem_from_text(embed.get('description', '') or '')
                if not premiums:
                    premiums = self._extract_total_prem_from_text(((embed.get('footer') or {}).get('text') or ''))

            #description = (embed.get('description', '') or '').lower()
            description = 'call golden sweep' if 'C' in parsed['call_put'] else 'put golden sweep'

            return {
                'Symbol': parsed['Symbol'],
                'Strike': parsed['Strike'],
                'Expiration': parsed['Expiration'],
                'Premiums': premiums,
                'Description': description,
            }
        except Exception as e:
            print(f"Error processing UW Custom Alert embed: {e}")
            return None

    def process_embed(self, embed: Dict) -> Optional[Dict]:
        """
        **UNIQUE EXTRACTION LOGIC FOR GOLDEN-SWEEPS**
        Process an embed and extract options data
        """
        try:
            if 'fields' not in embed or not embed['fields']:
                return None

            description = embed.get('description', '').lower()
            if not any(keyword in description for keyword in ['sweep', 'flow', 'option']):
                pass  # Still try to extract

            fields = embed['fields']

            symbol = self.extract_field_value(fields, 'Symbol')
            strike = self.extract_field_value(fields, 'Strike')
            expiration = self.extract_field_value(fields, 'Expiration')
            premiums = self.extract_field_value(fields, 'Premiums')

            if not premiums:
                premiums = self.extract_field_value(fields, 'Premium')
                if not premiums:
                    premiums = self.extract_field_value(fields, 'Prems')
                    if not premiums:
                        premiums = self.extract_field_value(fields, 'Value')

            if symbol and strike and expiration:
                return {
                    'Symbol': symbol.upper(),
                    'Strike': strike,
                    'Expiration': expiration,
                    'Premiums': premiums,
                    'Description': description,
                }


            # --- UW Custom Alerts support (added, non-breaking) ---
            uw_data = self.process_uw_custom_alert_embed(embed)
            if uw_data:
                return uw_data

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
                options_data = self.process_embed(embed)

                if options_data:
                    options_data['Date'] = date
                    options_data['Time'] = time

                    return {
                        'Date': options_data['Date'],
                        'Symbol': options_data['Symbol'],
                        'Strike': options_data['Strike'],
                        'Expiration': options_data['Expiration'],
                        'Premiums': options_data['Premiums'],
                        'Description': options_data['Description'],
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
                    fieldnames=['Date', 'Time', 'Symbol', 'Strike', 'Expiration', 'Premiums', 'Description'],
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

        print(f"Extracted {len(extracted_data)} sweeps, skipped {skipped}")

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
    parser = argparse.ArgumentParser(description='Extract golden-sweeps from JSON to pipe-delimited CSV')
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

    extractor = OptionsSweepExtractor(
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
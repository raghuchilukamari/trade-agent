#!/usr/bin/env python3
# trady-flow.py - Parser for trady-flow channel

import json
import csv
from datetime import datetime
import os
from typing import List, Dict, Optional
import argparse
import glob
import re


class TradyFlowExtractor:
    """
    Extracts Trady Flow and Unusual Whales alerts from Discord JSON exports and converts to CSV format
    """

    def __init__(self, input_file: str, output_file: str = None, append_mode: bool = True):
        self.input_file = input_file
        self.output_file = output_file or input_file.replace('.json', '_tradyflow.csv')
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
        value = value.replace('🚀', '')
        value = value.replace('💥', '')
        value = value.replace('⭐', '')
        value = value.replace('🔔', '')

        # Remove markdown formatting
        value = value.replace('**', '')
        value = value.replace('> ', '')
        value = value.replace('>>>', '')

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

    def parse_contract_details(self, contract_details: str) -> Dict[str, str]:
        """
        Parse the multi-line Contract Details field from Trady Flow
        Example:
        > **Strike:** 30.0
        > **Expiration:** 2/18/2026
        > **Total Prems:** 1.51M :star:
        > **Total Vol:** 18.34K
        > **Strike Stock Diff(%):** 59.0%
        > **Strike Stock Diff($):** 11.13
        """
        result = {
            'Strike': '',
            'Expiration': '',
            'Total_Prems': '',
            'Total_Vol': '',
            'Strike_Diff_Pct': '',
            'Strike_Diff_Dollar': ''
        }

        # Clean the text first
        contract_details = self.clean_field_value(contract_details)

        # Extract values using regex
        strike_match = re.search(r'Strike:\s*([\d.]+)', contract_details)
        if strike_match:
            result['Strike'] = strike_match.group(1)

        exp_match = re.search(r'Expiration:\s*([\d/]+)', contract_details)
        if exp_match:
            result['Expiration'] = exp_match.group(1)

        prems_match = re.search(r'Total Prems:\s*([\d.]+[KMB]?)', contract_details)
        if prems_match:
            result['Total_Prems'] = prems_match.group(1)

        vol_match = re.search(r'Total Vol:\s*([\d.]+[KMB]?)', contract_details)
        if vol_match:
            result['Total_Vol'] = vol_match.group(1)

        diff_pct_match = re.search(r'Strike Stock Diff\(%\):\s*([\d.]+)%', contract_details)
        if diff_pct_match:
            result['Strike_Diff_Pct'] = diff_pct_match.group(1) + '%'

        diff_dollar_match = re.search(r'Strike Stock Diff\(\$\):\s*([\d.]+)', contract_details)
        if diff_dollar_match:
            result['Strike_Diff_Dollar'] = diff_dollar_match.group(1)

        return result

    def parse_uw_alert_fields(self, fields: List[Dict]) -> Dict[str, str]:
        """Parse Unusual Whales alert fields (different structure)"""
        result = {
            'Price': '',
            'Total_Prem': '',
            'OTM_Pct': '',
            'Vol': '',
            'OI': '',
            'Vol_OI_Ratio': ''
        }

        # UW alerts have unnamed fields with combined values
        for field in fields:
            value = self.clean_field_value(field.get('value', ''))

            # Extract from first field (Price, Total Prem, etc.)
            price_match = re.search(r'Price:\s*\$?([\d.]+)', value)
            if price_match:
                result['Price'] = price_match.group(1)

            prem_match = re.search(r'Total Prem:\s*\$?([\d.]+[KMB]?)', value)
            if prem_match:
                result['Total_Prem'] = prem_match.group(1)

            otm_match = re.search(r'% OTM:\s*([\d.]+)%', value)
            if otm_match:
                result['OTM_Pct'] = otm_match.group(1) + '%'

            # Extract from second field (Vol, OI, etc.)
            vol_match = re.search(r'Vol:\s*([\d,]+)', value)
            if vol_match:
                result['Vol'] = vol_match.group(1).replace(',', '')

            oi_match = re.search(r'OI:\s*([\d,]+)', value)
            if oi_match:
                result['OI'] = oi_match.group(1).replace(',', '')

            vol_oi_match = re.search(r'Vol/OI:\s*([\d.]+)', value)
            if vol_oi_match:
                result['Vol_OI_Ratio'] = vol_oi_match.group(1)

        return result

    def extract_symbol_from_title(self, title: str) -> tuple:
        """Extract symbol, strike, call/put, expiration from UW title"""
        # Example: "🔔 DAL 72.0 C 1/16/2026 (18D) - Repeated Hits"
        title = self.clean_field_value(title)

        parts = title.split()
        symbol = parts[0] if parts else ''
        strike = parts[1] if len(parts) > 1 else ''
        call_put = 'CALL' if len(parts) > 2 and parts[2] == 'C' else 'PUT' if len(parts) > 2 and parts[2] == 'P' else ''
        expiration = parts[3] if len(parts) > 3 else ''

        return symbol, strike, call_put, expiration

    def process_tradytics_embed(self, embed: Dict) -> Optional[Dict]:
        """Process Tradytics Trady Flow embed"""
        try:
            author_name = embed.get('author', {}).get('name', '').lower()
            if 'trady flow' not in author_name:
                return None

            fields = embed['fields']

            symbol = self.extract_field_value(fields, 'Symbol')
            orders_today = self.extract_field_value(fields, 'Orders Today')
            call_put = self.extract_field_value(fields, 'Call/Put')
            contract_details_raw = self.extract_field_value(fields, 'Contract Details')

            # Parse contract details
            contract_data = self.parse_contract_details(contract_details_raw)

            # Get description (may have :star: or :rocket:)
            description = embed.get('description', '')
            description = self.clean_field_value(description)

            if symbol:
                return {
                    'Source': 'Tradytics',
                    'Symbol': symbol.upper(),
                    'Strike': contract_data['Strike'],
                    'Expiration': contract_data['Expiration'],
                    'Call_Put': call_put.upper(),
                    'Orders_Today': orders_today,
                    'Total_Prems': contract_data['Total_Prems'],
                    'Total_Vol': contract_data['Total_Vol'],
                    'Strike_Diff_Pct': contract_data['Strike_Diff_Pct'],
                    'Strike_Diff_Dollar': contract_data['Strike_Diff_Dollar'],
                    'Price': '',
                    'OTM_Pct': '',
                    'OI': '',
                    'Vol_OI_Ratio': '',
                }

            return None
        except Exception as e:
            print(f"Error processing Tradytics embed: {e}")
            return None

    def process_uw_embed(self, embed: Dict) -> Optional[Dict]:
        """Process Unusual Whales alert embed"""
        try:
            title = embed.get('title', '')
            if not title:
                return None

            symbol, strike, call_put, expiration = self.extract_symbol_from_title(title)

            # Parse fields
            uw_data = self.parse_uw_alert_fields(embed.get('fields', []))

            description = embed.get('description', '')
            description = self.clean_field_value(description)

            if symbol:
                return {
                    'Source': 'UnusualWhales',
                    'Symbol': symbol.upper(),
                    'Strike': strike,
                    'Expiration': expiration,
                    'Call_Put': call_put.upper(),
                    'Orders_Today': '',
                    'Total_Prems': uw_data['Total_Prem'],
                    'Total_Vol': uw_data['Vol'],
                    'Strike_Diff_Pct': '',
                    'Strike_Diff_Dollar': '',
                    'Price': uw_data['Price'],
                    'OTM_Pct': uw_data['OTM_Pct'],
                    'OI': uw_data['OI'],
                    'Vol_OI_Ratio': uw_data['Vol_OI_Ratio'],
                }

            return None
        except Exception as e:
            print(f"Error processing UW embed: {e}")
            return None

    def process_embed(self, embed: Dict) -> Optional[Dict]:
        """Route to appropriate processor based on embed type"""
        author_name = embed.get('author', {}).get('name', '').lower()

        if 'trady flow' in author_name:
            return self.process_tradytics_embed(embed)
        else:
            # Try UW format
            return self.process_uw_embed(embed)

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
                        'Source': flow_data['Source'],
                        'Symbol': flow_data['Symbol'],
                        'Strike': flow_data['Strike'],
                        'Expiration': flow_data['Expiration'],
                        'Call_Put': flow_data['Call_Put'],
                        'Orders_Today': flow_data['Orders_Today'],
                        'Total_Prems': flow_data['Total_Prems'],
                        'Total_Vol': flow_data['Total_Vol'],
                        'Price': flow_data['Price'],
                        'OTM_Pct': flow_data['OTM_Pct'],
                        'OI': flow_data['OI'],
                        'Vol_OI_Ratio': flow_data['Vol_OI_Ratio'],
                        'Strike_Diff_Pct': flow_data['Strike_Diff_Pct'],
                        'Strike_Diff_Dollar': flow_data['Strike_Diff_Dollar'],
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
                        'Date', 'Time', 'Source', 'Symbol', 'Strike', 'Expiration',
                        'Call_Put', 'Orders_Today', 'Total_Prems', 'Total_Vol',
                        'Price', 'OTM_Pct', 'OI', 'Vol_OI_Ratio',
                        'Strike_Diff_Pct', 'Strike_Diff_Dollar'
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
    parser = argparse.ArgumentParser(description='Extract trady-flow alerts from JSON to pipe-delimited CSV')
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

    extractor = TradyFlowExtractor(
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
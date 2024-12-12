import json
import hashlib
import requests
import hmac
import os
from typing import Dict, Optional

CRMUS_DATA_FILE = '/etc/hysteria/crmus_data.json'

class CryptomusHandler:
    def __init__(self):
        self.merchant_id = None
        self.payment_key = None
        self.load_credentials()
        self.base_url = "https://api.cryptomus.com/v1"
        
    def load_credentials(self) -> None:
        """Load Cryptomus credentials from JSON file"""
        if os.path.exists(CRMUS_DATA_FILE):
            try:
                with open(CRMUS_DATA_FILE, 'r') as f:
                    data = json.load(f)
                    self.merchant_id = data.get('merchant_id')
                    self.payment_key = data.get('payment_key')
            except Exception as e:
                print(f"Error loading Cryptomus credentials: {e}")

    def save_credentials(self, merchant_id: str, payment_key: str) -> bool:
        """Save Cryptomus credentials to JSON file"""
        try:
            data = {
                'merchant_id': merchant_id,
                'payment_key': payment_key,
                'transactions': {}
            }
            os.makedirs(os.path.dirname(CRMUS_DATA_FILE), exist_ok=True)
            with open(CRMUS_DATA_FILE, 'w') as f:
                json.dump(data, f, indent=4)
            self.merchant_id = merchant_id
            self.payment_key = payment_key
            return True
        except Exception as e:
            print(f"Error saving Cryptomus credentials: {e}")
            return False

    def is_configured(self) -> bool:
        """Check if Cryptomus is configured with valid credentials"""
        return bool(self.merchant_id and self.payment_key)

    def _sign_request(self, payload: dict) -> Dict[str, str]:
        """Create signed headers for Cryptomus API request"""
        if not self.is_configured():
            raise ValueError("Cryptomus credentials not configured")

        payload_str = json.dumps(payload, separators=(',', ':'))
        sign = hmac.new(
            self.payment_key.encode(),
            payload_str.encode(),
            hashlib.sha512
        ).hexdigest()

        return {
            'merchant': self.merchant_id,
            'sign': sign,
            'Content-Type': 'application/json'
        }

    def create_payment(self, amount: float, order_id: str, currency: str = "USD") -> Optional[Dict]:
        """Create a new payment"""
        if not self.is_configured():
            return None

        payload = {
            "amount": str(amount),
            "currency": currency,
            "order_id": order_id,
            "url_callback": "https://your-callback-url.com",  # Replace with actual callback URL
        }

        try:
            response = requests.post(
                f"{self.base_url}/payment",
                headers=self._sign_request(payload),
                json=payload
            )
            if response.status_code == 200:
                result = response.json()
                self._save_transaction(order_id, result['result'])
                return result['result']
            return None
        except Exception as e:
            print(f"Error creating payment: {e}")
            return None

    def check_payment(self, order_id: str) -> Optional[Dict]:
        """Check payment status"""
        if not self.is_configured():
            return None

        payload = {"order_id": order_id}

        try:
            response = requests.post(
                f"{self.base_url}/payment/info",
                headers=self._sign_request(payload),
                json=payload
            )
            if response.status_code == 200:
                return response.json()['result']
            return None
        except Exception as e:
            print(f"Error checking payment: {e}")
            return None

    def _save_transaction(self, order_id: str, transaction_data: Dict) -> None:
        """Save transaction data to JSON file"""
        try:
            if os.path.exists(CRMUS_DATA_FILE):
                with open(CRMUS_DATA_FILE, 'r') as f:
                    data = json.load(f)
            else:
                data = {'transactions': {}}

            data['transactions'][order_id] = transaction_data

            with open(CRMUS_DATA_FILE, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving transaction: {e}")

    def get_transaction(self, order_id: str) -> Optional[Dict]:
        """Get transaction data from JSON file"""
        try:
            if os.path.exists(CRMUS_DATA_FILE):
                with open(CRMUS_DATA_FILE, 'r') as f:
                    data = json.load(f)
                    return data.get('transactions', {}).get(order_id)
            return None
        except Exception as e:
            print(f"Error getting transaction: {e}")
            return None
